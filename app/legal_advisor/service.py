"""eBobo Legal Intelligence - Funkcja 1: wyjaśnianie wyników oceny uprawnień,
rozbudowana o "minimalny RAG bez bazy wektorowej" (brief, rozbudowa Funkcji 1).

Zasady bezpieczeństwa (z briefu użytkownika, nieprzejednane):
- Silnik deterministyczny ma zawsze pierwszeństwo przed AI. Ten moduł nigdy nie pyta
  AI o status/kwotę - oba pochodzą wyłącznie z ``app.eligibility`` i ``app.calculator``.
- AI dostaje WYŁĄCZNIE zminimalizowane dane: już-wygenerowane przez silnik opisy
  warunków (met/unmet/missing_data/warnings) i FAKTYCZNĄ TREŚĆ (nie tylko etykiety)
  fragmentów prawnych z ``app.legal_knowledge`` - nigdy surowego payloadu użytkownika
  (dochody, dane zdrowotne dziecka itd.).
- Samo istnienie zacytowanego przepisu to za mało - każda rekomendacja AI musi być
  powiązana z konkretnym fragmentem źródłowym z dostarczonego zbioru; rekomendacje
  powołujące się na fragment spoza tego zbioru są w całości odrzucane (nie pokazywane
  jako niepewne - po prostu nie pokazywane).
- Brak fragmentów wiedzy prawnej dla danego świadczenia (luka w bazie, a nie błąd AI)
  jest sygnalizowany wprost - backend nie woła wtedy AI "na pusto", tylko zwraca
  deterministyczny wynik z jawnym zaznaczeniem wymaganej weryfikacji.
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
from app.legal_knowledge.repository import get_fragments_for_benefit
from app.legal_knowledge.schemas import LegalFragment, display_label

_CONTACT_ZUS_OR_SPECIALIST_STEP = (
    "Skontaktuj się z ZUS lub doradcą/prawnikiem, jeśli sytuacja jest złożona albo "
    "dotyczy więcej niż jednego świadczenia."
)

_SYSTEM_PROMPT = """Jesteś asystentem wyjaśniającym w prostym języku wyniki oceny \
uprawnień do polskich świadczeń ZUS związanych z rodzicielstwem (zasiłek macierzyński, \
rodzicielski, ojcowski itd.). Dostajesz WYŁĄCZNIE wynik już podjętej, deterministycznej \
oceny oraz zbiór fragmentów wiedzy prawnej (FRAGMENTS) z ich faktyczną treścią - nigdy \
nie ustalasz ani nie zmieniasz statusu uprawnienia, nigdy nie wyliczasz kwot świadczeń, \
nigdy nie przyznajesz uprawnienia samodzielnie.

Odpowiadasz WYŁĄCZNIE w formacie JSON, dokładnie w tym kształcie:
{
  "explanation": "wyjaśnienie wyniku w prostym języku, 2-5 zdań",
  "missing_data_explained": ["wyjaśnienie brakujących danych/dokumentów, jeśli dotyczy"],
  "suggested_next_steps": [
    {"text": "konkretna propozycja dalszego postępowania",
     "supporting_fragment_ids": ["id fragmentu z FRAGMENTS, jeśli ta propozycja opiera "
                                  "się na konkretnym przepisie - inaczej pusta lista"]}
  ],
  "other_benefits_to_check": ["kody innych świadczeń warte sprawdzenia osobno, jeśli dotyczy"],
  "cited_fragment_ids": ["id fragmentów z FRAGMENTS, na których oparto \"explanation\""],
  "requires_additional_verification": true/false
}

KRYTYCZNE ZASADY:
- "cited_fragment_ids" i każde "supporting_fragment_ids" mogą zawierać WYŁĄCZNIE id \
dosłownie wzięte z listy FRAGMENTS podanej w danych wejściowych. Nigdy nie wymyślaj \
nowych id, terminów, wyjątków, warunków ani dokumentów spoza tego, co dostałeś.
- Jeśli nie masz wystarczającej podstawy w FRAGMENTS dla jakiejś tezy, pomiń ją albo \
zostaw "supporting_fragment_ids" puste i ustaw "requires_additional_verification": true.
- Nigdy nie podawaj konkretnej kwoty świadczenia.
- Nigdy nie twierdź, że przyznajesz albo zmieniasz uprawnienie - jedynie wyjaśniasz \
już podjętą ocenę."""


def _collect_candidate_fragments(
    benefit_code: str, result: EligibilityResult
) -> list[LegalFragment]:
    fragments = {f.id: f for f in get_fragments_for_benefit(benefit_code)}
    for solution in result.possible_solutions:
        if solution.related_benefit_code:
            for fragment in get_fragments_for_benefit(solution.related_benefit_code):
                fragments.setdefault(fragment.id, fragment)
    return list(fragments.values())


def _build_user_prompt(
    benefit_code: str,
    benefit_name: str,
    result: EligibilityResult,
    candidate_fragments: list[LegalFragment],
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
        "FRAGMENTS": [
            {
                "id": fragment.id,
                "source": fragment.source,
                "citation": fragment.citation,
                "content": fragment.content,
            }
            for fragment in candidate_fragments
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def _fallback_response(
    benefit_code: str,
    result: EligibilityResult,
    candidate_fragments: list[LegalFragment],
    rules_version: int,
    *,
    extra_note: str | None = None,
) -> LegalAdvisorExplainResponse:
    explanation_parts = []
    if extra_note:
        explanation_parts.append(extra_note)
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

    next_steps = [s.description for s in result.possible_solutions]
    next_steps.append(_CONTACT_ZUS_OR_SPECIALIST_STEP)

    return LegalAdvisorExplainResponse(
        benefit_code=benefit_code,
        status=result.status,
        explanation=" ".join(explanation_parts),
        missing_data_explained=list(result.missing_data),
        suggested_next_steps=next_steps,
        other_benefits_to_check=[
            s.related_benefit_code for s in result.possible_solutions if s.related_benefit_code
        ],
        verified_legal_basis=[display_label(f) for f in candidate_fragments],
        requires_additional_verification=True,
        rules_version=rules_version,
        ai_available=False,
        source="fallback",
    )


def explain_eligibility_result(
    db: Session,
    benefit_code: str,
    payload: MaternityLeaveEligibilityRequest,
    *,
    user_id: str | None = None,
) -> LegalAdvisorExplainResponse:
    evaluate = ELIGIBILITY_EVALUATORS.get(benefit_code)
    if evaluate is None:
        raise NotFoundError(f"Nieznany kod świadczenia: '{benefit_code}'")

    rule = get_current_rule(db, benefit_code)
    # Ponowne wywołanie silnika - AI nigdy nie dostaje wyniku zadeklarowanego przez
    # frontend, tylko ten policzony właśnie teraz, tutaj.
    result = evaluate(payload, rule)

    candidate_fragments = _collect_candidate_fragments(benefit_code, result)
    fragment_ids = {f.id for f in candidate_fragments}

    if not candidate_fragments:
        # Luka w lokalnej bazie wiedzy prawnej, nie awaria AI - nie ma sensu pytać
        # modelu bez żadnego groundingu, więc nie wołamy go wcale.
        response = _fallback_response(
            benefit_code,
            result,
            candidate_fragments,
            rule.version,
            extra_note=(
                "Brak fragmentów wiedzy prawnej dla tego świadczenia w lokalnej bazie - "
                "poniższe wyjaśnienie opiera się wyłącznie na wyniku silnika."
            ),
        )
    else:
        try:
            user_prompt = _build_user_prompt(
                benefit_code, rule.benefit_type.name, result, candidate_fragments
            )
            raw = request_json_completion(_SYSTEM_PROMPT, user_prompt)
            parsed = AIExplanationRaw.model_validate(raw)
        except (AIProviderUnavailableError, AIProviderInvalidResponseError, ValidationError):
            response = _fallback_response(benefit_code, result, candidate_fragments, rule.version)
        else:
            verified_fragment_ids = [
                fid for fid in parsed.cited_fragment_ids if fid in fragment_ids
            ]
            citations_were_dropped = len(verified_fragment_ids) < len(parsed.cited_fragment_ids)

            valid_steps: list[str] = []
            recommendations_were_dropped = False
            for recommendation in parsed.suggested_next_steps:
                if all(fid in fragment_ids for fid in recommendation.supporting_fragment_ids):
                    valid_steps.append(recommendation.text)
                else:
                    recommendations_were_dropped = True

            known_benefit_codes = set(ELIGIBILITY_EVALUATORS)
            valid_other_benefits = [
                code for code in parsed.other_benefits_to_check if code in known_benefit_codes
            ]

            requires_verification = (
                parsed.requires_additional_verification
                or citations_were_dropped
                or recommendations_were_dropped
            )
            if requires_verification:
                valid_steps.append(_CONTACT_ZUS_OR_SPECIALIST_STEP)

            response = LegalAdvisorExplainResponse(
                benefit_code=benefit_code,
                status=result.status,
                explanation=parsed.explanation,
                missing_data_explained=parsed.missing_data_explained,
                suggested_next_steps=valid_steps,
                other_benefits_to_check=valid_other_benefits,
                verified_legal_basis=[
                    display_label(f) for f in candidate_fragments if f.id in verified_fragment_ids
                ],
                requires_additional_verification=requires_verification,
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
        user_id=user_id,
    )
    response.request_log_entry_id = log_entry.id
    return response
