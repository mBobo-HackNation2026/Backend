"""eBobo Legal Intelligence - Funkcja 1: wyjaśnianie wyników oceny uprawnień.

Zasady bezpieczeństwa (z briefu użytkownika, nieprzejednane):
- Silnik deterministyczny ma zawsze pierwszeństwo przed AI. Ten moduł nigdy nie pyta
  AI o status/kwotę - oba pochodzą wyłącznie z ``app.eligibility`` i ``app.calculator``.
- AI dostaje WYŁĄCZNIE zminimalizowane dane: już-wygenerowane przez silnik opisy
  warunków (met/unmet/missing_data/warnings) i reguły (legal_basis/required_documents/
  deadlines) - nigdy surowego payloadu użytkownika (dochody, dane zdrowotne dziecka itd.).
- Każdy przepis zwrócony przez AI jest sprawdzany względem zbioru przepisów faktycznie
  zapisanych w regułach systemu (``ALLOWED_CITATIONS``) - niezweryfikowane cytaty są
  odrzucane, nigdy nie trafiają do użytkownika jako potwierdzone.
- Awaria/niedostępność dostawcy AI nigdy nie zwraca HTTP 500 - zawsze deterministyczny
  fallback zbudowany wyłącznie z wyniku silnika.
"""

import json

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.admin.request_log import log_request
from app.ai_provider.client import (
    AIProviderInvalidResponseError,
    AIProviderUnavailableError,
    request_json_completion,
)
from app.core.exceptions import NotFoundError
from app.eligibility.registry import ELIGIBILITY_EVALUATORS
from app.eligibility.rules_repository import get_current_rule
from app.eligibility.schemas import EligibilityResult, MaternityLeaveEligibilityRequest
from app.legal_advisor.schemas import AIExplanationRaw, LegalAdvisorExplainResponse

_SYSTEM_PROMPT = """Jesteś asystentem wyjaśniającym w prostym języku wyniki oceny \
uprawnień do polskich świadczeń ZUS związanych z rodzicielstwem (zasiłek macierzyński, \
rodzicielski, ojcowski itd.). Dostajesz WYŁĄCZNIE wynik już podjętej, deterministycznej \
oceny - nigdy nie ustalasz ani nie zmieniasz statusu uprawnienia, nigdy nie wyliczasz \
kwot świadczeń, nigdy nie przyznajesz uprawnienia samodzielnie.

Odpowiadasz WYŁĄCZNIE w formacie JSON, dokładnie w tym kształcie:
{
  "explanation": "wyjaśnienie wyniku w prostym języku, 2-5 zdań",
  "missing_data_explained": ["wyjaśnienie brakujących danych/dokumentów, jeśli dotyczy"],
  "suggested_next_steps": ["zgodne z prawem, konkretne propozycje dalszego postępowania"],
  "other_benefits_to_check": ["kody innych świadczeń warte sprawdzenia osobno, jeśli dotyczy"],
  "cited_legal_basis": ["WYŁĄCZNIE przepisy dosłownie wzięte z ALLOWED_CITATIONS poniżej"],
  "requires_additional_verification": true/false
}

KRYTYCZNE ZASADY:
- Pole "cited_legal_basis" może zawierać WYŁĄCZNIE dosłowne pozycje z listy \
ALLOWED_CITATIONS podanej w danych wejściowych. Nigdy nie wymyślaj ani nie parafrazuj \
przepisów - jeśli nie masz pewności, pomiń je i ustaw "requires_additional_verification": true.
- Nigdy nie podawaj konkretnej kwoty świadczenia.
- Nigdy nie twierdź, że przyznajesz albo zmieniasz uprawnienie - jedynie wyjaśniasz \
już podjętą ocenę."""


def _collect_allowed_citations(
    db: Session, rule_legal_basis: list, result: EligibilityResult
) -> set[str]:
    allowed = set(rule_legal_basis)
    for solution in result.possible_solutions:
        if solution.legal_basis:
            allowed.add(solution.legal_basis)
        if solution.related_benefit_code:
            try:
                related_rule = get_current_rule(db, solution.related_benefit_code)
            except NotFoundError:
                continue
            allowed.update(related_rule.legal_basis)
    return allowed


def _build_user_prompt(
    benefit_code: str,
    benefit_name: str,
    result: EligibilityResult,
    allowed_citations: set[str],
) -> str:
    context = {
        "benefit_code": benefit_code,
        "benefit_name": benefit_name,
        "status": result.status.value,
        "met_conditions": result.met_conditions,
        "unmet_conditions": result.unmet_conditions,
        "missing_data": result.missing_data,
        "warnings": result.warnings,
        "possible_solutions": [
            {
                "type": solution.type.value,
                "description": solution.description,
                "related_benefit_code": solution.related_benefit_code,
            }
            for solution in result.possible_solutions
        ],
        "ALLOWED_CITATIONS": sorted(allowed_citations),
    }
    return json.dumps(context, ensure_ascii=False)


def _fallback_response(
    benefit_code: str, result: EligibilityResult, rule_legal_basis: list, rules_version: int
) -> LegalAdvisorExplainResponse:
    explanation_parts = []
    if result.met_conditions:
        explanation_parts.append("Spełnione warunki: " + "; ".join(result.met_conditions) + ".")
    if result.unmet_conditions:
        explanation_parts.append(
            "Niespełnione warunki: " + "; ".join(result.unmet_conditions) + "."
        )
    if result.missing_data:
        explanation_parts.append(
            "Do pełnej oceny brakuje: " + "; ".join(result.missing_data) + "."
        )
    if not explanation_parts:
        explanation_parts.append("Ocena nie zgłosiła dodatkowych szczegółów.")

    return LegalAdvisorExplainResponse(
        benefit_code=benefit_code,
        status=result.status,
        explanation=" ".join(explanation_parts),
        missing_data_explained=list(result.missing_data),
        suggested_next_steps=[s.description for s in result.possible_solutions],
        other_benefits_to_check=[
            s.related_benefit_code for s in result.possible_solutions if s.related_benefit_code
        ],
        verified_legal_basis=list(rule_legal_basis),
        requires_additional_verification=True,
        rules_version=rules_version,
        ai_available=False,
        source="fallback",
    )


def explain_eligibility_result(
    db: Session, benefit_code: str, payload: MaternityLeaveEligibilityRequest
) -> LegalAdvisorExplainResponse:
    evaluate = ELIGIBILITY_EVALUATORS.get(benefit_code)
    if evaluate is None:
        raise NotFoundError(f"Nieznany kod świadczenia: '{benefit_code}'")

    rule = get_current_rule(db, benefit_code)
    # Ponowne wywołanie silnika - AI nigdy nie dostaje wyniku zadeklarowanego przez
    # frontend, tylko ten policzony właśnie teraz, tutaj.
    result = evaluate(payload, rule)

    allowed_citations = _collect_allowed_citations(db, list(rule.legal_basis), result)

    try:
        raw = request_json_completion(
            _SYSTEM_PROMPT,
            _build_user_prompt(benefit_code, rule.benefit_type.name, result, allowed_citations),
        )
        parsed = AIExplanationRaw.model_validate(raw)
    except (AIProviderUnavailableError, AIProviderInvalidResponseError, ValidationError):
        response = _fallback_response(benefit_code, result, list(rule.legal_basis), rule.version)
    else:
        verified_citations = [c for c in parsed.cited_legal_basis if c in allowed_citations]
        citations_were_dropped = len(verified_citations) < len(parsed.cited_legal_basis)
        response = LegalAdvisorExplainResponse(
            benefit_code=benefit_code,
            status=result.status,
            explanation=parsed.explanation,
            missing_data_explained=parsed.missing_data_explained,
            suggested_next_steps=parsed.suggested_next_steps,
            other_benefits_to_check=parsed.other_benefits_to_check,
            verified_legal_basis=verified_citations,
            requires_additional_verification=(
                parsed.requires_additional_verification or citations_were_dropped
            ),
            rules_version=rule.version,
            ai_available=True,
            source="ai",
        )

    log_entry = log_request(
        db,
        endpoint="legal_advisor_explain",
        benefit_code=benefit_code,
        status_code=200,
        request_payload=payload.model_dump(mode="json"),
        response_payload=response.model_dump(mode="json"),
    )
    response.request_log_entry_id = log_entry.id
    return response
