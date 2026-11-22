"""eBobo Legal Intelligence, Etap 3: wykrywanie sygnałów jakościowych silnika,
wewnętrzna kolejka przypadków i (opcjonalna, uruchamiana ręcznie przez administratora)
analiza AI - reużywa dokładnie ten sam klient OpenRouter i tę samą bazę wiedzy prawnej
co Legal Advisor (Funkcja 1) i Legal Feedback (Etap 2 Faza B), żadnej nowej integracji
LLM.

Zasady (z briefu, nieprzejednane):
- Zwykły brak danych w ankiecie (``missing_data``/``missing_fields``) NIGDY nie tworzy
  tu sprawy - tylko wyraźnie wymienione sygnały (patrz ``EngineQualitySignalType``).
- Powtarzające się wystąpienia tego samego sygnału (ten sam ``group_key``) nigdy nie
  tworzą nowych wierszy - inkrementują ``occurrence_count`` na już istniejącym,
  otwartym przypadku. Żadne dane osobowe nie wchodzą w skład ``group_key``.
- Analiza AI nigdy nie zmienia ``status``/``priority`` sprawy - to wyłącznie hipoteza,
  decyzję zawsze podejmuje administrator przez PATCH .../status lub .../priority.
- Problemy techniczne (dostawca AI niedostępny) są odróżniane od sygnałów
  merytorycznych - awaria OpenRouter przy POST .../analyze nigdy nie tworzy ani nie
  modyfikuje sama z siebie żadnego ``EngineQualityCase``, tylko zapisuje
  ``analysis_status="failed"`` na tej jednej próbie analizy.
"""

import json
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai_provider.client import (
    AIProviderInvalidResponseError,
    AIProviderUnavailableError,
    request_json_completion,
)
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.models.engine_quality import (
    EngineQualityCase,
    EngineQualityCaseAnalysis,
    EngineQualityCaseHistory,
    EngineQualityCasePriority,
    EngineQualityCaseStatus,
    EngineQualitySignalType,
)
from app.db.models.legal_feedback import LegalFeedback
from app.db.models.request_log import RequestLogEntry
from app.engine_quality.schemas import AIEngineQualityAnalysisRaw
from app.legal_knowledge.repository import get_fragments_for_benefit
from app.legal_knowledge.schemas import LegalFragment

_MAX_LIST_LIMIT = 200
# Próg, po którym powtarzający się sygnał (ten sam group_key) automatycznie podnosi
# priorytet sprawy - realizacja EngineQualitySignalType.repeated_unresolved_case jako
# eskalacji istniejącego przypadku, nie jako osobno wyzwalanego sygnału (zob. docstring
# tego typu w app/db/models/engine_quality.py).
_REPEATED_CASE_PRIORITY_ESCALATION_THRESHOLD = 3

_SYSTEM_PROMPT = """Jesteś asystentem analizującym - na prośbę upoważnionego pracownika - \
przypadki wykryte przez wewnętrzny monitoring jakości silnika oceny uprawnień do polskich \
świadczeń ZUS związanych z rodzicielstwem. Dostajesz: typ wykrytego sygnału, powód skierowania \
sprawy do przeglądu, bezpieczny kontekst (nigdy pełne dane osobowe/zdrowotne rodzica), oraz \
zbiór fragmentów wiedzy prawnej (FRAGMENTS) faktycznie dotyczących tego świadczenia.

Twoim zadaniem jest zaproponować pracownikowi HIPOTEZĘ możliwej przyczyny problemu - NIGDY nie \
zmieniasz żadnej aktywnej reguły, nie ustalasz że reguła jest błędna w sposób ostateczny, nie \
wyliczasz kwot świadczeń.

Odpowiadasz WYŁĄCZNIE w formacie JSON, dokładnie w tym kształcie:
{
  "classification": "missing_user_data" | "possible_rule_gap" | "possible_rule_error" |
                     "outdated_legal_source" | "possible_user_misunderstanding" |
                     "insufficient_evidence",
  "summary": "krótkie wyjaśnienie, 2-4 zdania",
  "potential_issue": "opis potencjalnej luki, błędu albo przyczyny sygnału",
  "required_information": ["jakich informacji brakuje do rozstrzygnięcia, jeśli dotyczy"],
  "cited_fragment_ids": ["WYŁĄCZNIE id dosłownie wzięte z FRAGMENTS poniżej"],
  "recommended_admin_action": "konkretna, krótka sugestia dla pracownika"
}

KRYTYCZNE ZASADY:
- "cited_fragment_ids" może zawierać WYŁĄCZNIE id dosłownie wzięte z listy FRAGMENTS - nigdy \
nie wymyślaj nowych id ani przepisów.
- Jeśli pokrycie prawne w FRAGMENTS jest niewystarczające, ustaw \
"classification": "insufficient_evidence" zamiast zgadywać.
- To jest HIPOTEZA do weryfikacji przez pracownika, NIGDY potwierdzony błąd prawny."""


def _compute_group_key(
    signal_type: EngineQualitySignalType, benefit_code: str | None, rules_version: int | None
) -> str:
    version_part = rules_version if rules_version is not None else "none"
    return f"{signal_type.value}:{benefit_code or 'none'}:{version_part}"


def record_signal(
    db: Session,
    *,
    signal_type: EngineQualitySignalType,
    benefit_code: str | None,
    reason: str,
    rules_version: int | None = None,
    request_log_entry_id: int | None = None,
    legal_feedback_id: int | None = None,
) -> EngineQualityCase:
    """Zgłasza wykryty sygnał jakościowy - dedupikuje po ``group_key`` (ten sam typ
    sygnału + świadczenie + wersja reguły) względem przypadków jeszcze nie zamkniętych
    (``not_an_issue``/``closed`` zaczynają nową grupę, jeśli sygnał pojawi się ponownie
    - stara decyzja administratora zostaje nienaruszona)."""
    group_key = _compute_group_key(signal_type, benefit_code, rules_version)
    existing = (
        db.query(EngineQualityCase)
        .filter(EngineQualityCase.group_key == group_key)
        .filter(
            EngineQualityCase.status.notin_(
                [EngineQualityCaseStatus.not_an_issue, EngineQualityCaseStatus.closed]
            )
        )
        .order_by(EngineQualityCase.detected_at.desc())
        .first()
    )

    if existing is not None:
        existing.occurrence_count += 1
        existing.reason = reason
        existing.updated_at = datetime.now(UTC)
        if request_log_entry_id is not None:
            existing.request_log_entry_id = request_log_entry_id
        if legal_feedback_id is not None:
            existing.legal_feedback_id = legal_feedback_id
        if (
            existing.occurrence_count >= _REPEATED_CASE_PRIORITY_ESCALATION_THRESHOLD
            and existing.priority != EngineQualityCasePriority.high
        ):
            old_priority = existing.priority
            existing.priority = EngineQualityCasePriority.high
            db.add(
                EngineQualityCaseHistory(
                    case_id=existing.id,
                    field_changed="priority",
                    old_value=old_priority.value,
                    new_value=EngineQualityCasePriority.high.value,
                    changed_by="system",
                    reason=(
                        f"Automatyczna eskalacja - sygnał wystąpił już "
                        f"{existing.occurrence_count} razy "
                        f"({EngineQualitySignalType.repeated_unresolved_case.value})"
                    ),
                )
            )
        db.commit()
        db.refresh(existing)
        return existing

    case = EngineQualityCase(
        signal_type=signal_type,
        benefit_code=benefit_code,
        rules_version=rules_version,
        request_log_entry_id=request_log_entry_id,
        legal_feedback_id=legal_feedback_id,
        reason=reason,
        group_key=group_key,
        occurrence_count=1,
        priority=EngineQualityCasePriority.medium,
        status=EngineQualityCaseStatus.new,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def list_cases(
    db: Session,
    *,
    signal_type: str | None = None,
    benefit_code: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order: str = "desc",
) -> list[EngineQualityCase]:
    query = db.query(EngineQualityCase)
    if signal_type is not None:
        query = query.filter(EngineQualityCase.signal_type == signal_type)
    if benefit_code is not None:
        query = query.filter(EngineQualityCase.benefit_code == benefit_code)
    if status is not None:
        query = query.filter(EngineQualityCase.status == status)
    if priority is not None:
        query = query.filter(EngineQualityCase.priority == priority)

    sort_column = EngineQualityCase.detected_at
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())

    return query.offset(max(offset, 0)).limit(min(limit, _MAX_LIST_LIMIT)).all()


def _get_case_or_404(db: Session, case_id: int) -> EngineQualityCase:
    case = db.get(EngineQualityCase, case_id)
    if case is None:
        raise NotFoundError(f"Nie znaleziono sprawy o id={case_id}")
    return case


def get_case_detail(
    db: Session, case_id: int
) -> tuple[EngineQualityCase, list[EngineQualityCaseHistory], list[EngineQualityCaseAnalysis]]:
    case = _get_case_or_404(db, case_id)
    history = (
        db.query(EngineQualityCaseHistory)
        .filter(EngineQualityCaseHistory.case_id == case_id)
        .order_by(EngineQualityCaseHistory.changed_at.desc())
        .all()
    )
    analyses = (
        db.query(EngineQualityCaseAnalysis)
        .filter(EngineQualityCaseAnalysis.engine_quality_case_id == case_id)
        .order_by(EngineQualityCaseAnalysis.created_at.desc())
        .all()
    )
    return case, history, analyses


def update_status(
    db: Session,
    case_id: int,
    new_status: EngineQualityCaseStatus,
    reason: str | None,
    changed_by: str,
) -> EngineQualityCase:
    case = _get_case_or_404(db, case_id)
    old_status = case.status
    case.status = new_status
    case.updated_at = datetime.now(UTC)
    db.add(
        EngineQualityCaseHistory(
            case_id=case.id,
            field_changed="status",
            old_value=old_status.value,
            new_value=new_status.value,
            changed_by=changed_by,
            reason=reason,
        )
    )
    db.commit()
    db.refresh(case)
    return case


def update_priority(
    db: Session,
    case_id: int,
    new_priority: EngineQualityCasePriority,
    reason: str | None,
    changed_by: str,
) -> EngineQualityCase:
    case = _get_case_or_404(db, case_id)
    old_priority = case.priority
    case.priority = new_priority
    case.updated_at = datetime.now(UTC)
    db.add(
        EngineQualityCaseHistory(
            case_id=case.id,
            field_changed="priority",
            old_value=old_priority.value,
            new_value=new_priority.value,
            changed_by=changed_by,
            reason=reason,
        )
    )
    db.commit()
    db.refresh(case)
    return case


def _safe_case_context(db: Session, case: EngineQualityCase) -> dict:
    """Zminimalizowany, bezpieczny kontekst sprawy - nigdy surowy request_payload
    użytkownika (dochody, dane zdrowotne dziecka itd.)."""
    context: dict = {
        "signal_type": case.signal_type.value,
        "reason": case.reason,
        "benefit_code": case.benefit_code,
        "occurrence_count": case.occurrence_count,
    }
    if case.request_log_entry_id is not None:
        entry = db.get(RequestLogEntry, case.request_log_entry_id)
        if entry is not None and isinstance(entry.response_payload, dict):
            payload = entry.response_payload
            context["original_evaluation"] = {
                "endpoint": entry.endpoint,
                **{
                    key: payload[key]
                    for key in (
                        "status",
                        "met_conditions",
                        "unmet_conditions",
                        "missing_data",
                        "warnings",
                    )
                    if key in payload
                },
            }
    if case.legal_feedback_id is not None:
        feedback = db.get(LegalFeedback, case.legal_feedback_id)
        if feedback is not None:
            context["user_reported_discrepancy_untrusted_data"] = {
                "feedback_type": feedback.feedback_type.value,
                "user_comment": feedback.user_comment,
                "expected_result_opinion_only": feedback.expected_result,
            }
    return context


def run_case_analysis(db: Session, case_id: int) -> EngineQualityCaseAnalysis:
    case, _, _ = get_case_detail(db, case_id)

    candidate_fragments: list[LegalFragment] = (
        get_fragments_for_benefit(case.benefit_code) if case.benefit_code else []
    )
    fragment_ids = {f.id for f in candidate_fragments}

    user_prompt_data = {
        **_safe_case_context(db, case),
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

    try:
        user_prompt = json.dumps(user_prompt_data, ensure_ascii=False)
        raw = request_json_completion(_SYSTEM_PROMPT, user_prompt)
        parsed = AIEngineQualityAnalysisRaw.model_validate(raw)
    except (AIProviderUnavailableError, AIProviderInvalidResponseError, ValidationError) as exc:
        analysis = EngineQualityCaseAnalysis(
            engine_quality_case_id=case.id,
            analysis_status="failed",
            required_information=[],
            verified_source_ids=[],
            requires_human_review=True,
            model_id=None,
            error_message=f"Analiza nieudana: {type(exc).__name__}",
            created_at=datetime.now(UTC),
        )
    else:
        verified_source_ids = [fid for fid in parsed.cited_fragment_ids if fid in fragment_ids]
        analysis = EngineQualityCaseAnalysis(
            engine_quality_case_id=case.id,
            analysis_status="completed",
            classification=parsed.classification.value,
            summary=parsed.summary,
            potential_issue=parsed.potential_issue,
            required_information=parsed.required_information,
            verified_source_ids=verified_source_ids,
            recommended_admin_action=parsed.recommended_admin_action,
            requires_human_review=True,
            model_id=get_settings().openrouter_model,
            created_at=datetime.now(UTC),
        )

    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis
