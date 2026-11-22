"""eBobo Legal Intelligence, Etap 2 (Faza A): przyjmowanie zgłoszeń wątpliwości co do
wyniku oceny silnika uprawnień. Analiza AI i panel administratora (Faza B) są
świadomie poza zakresem tej fazy - zob. pamięć projektu
`project-ebobo-legal-feedback`.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, RateLimitedError
from app.db.models.legal_feedback import LegalFeedback, LegalFeedbackStatus
from app.db.models.request_log import RequestLogEntry
from app.legal_feedback.schemas import LegalFeedbackCreateRequest

# Proste liczenie w bazie, bez dodatkowej biblioteki - wystarczające przy jednym
# procesie/SQLite i niskim wolumenie tego endpointu.
_RATE_LIMIT_MAX_PER_HOUR = 10
_RATE_LIMIT_WINDOW = timedelta(hours=1)


def _check_rate_limit(db: Session, user_id: str) -> None:
    window_start = datetime.now(UTC) - _RATE_LIMIT_WINDOW
    recent_count = (
        db.query(LegalFeedback)
        .filter(LegalFeedback.user_id == user_id, LegalFeedback.created_at >= window_start)
        .count()
    )
    if recent_count >= _RATE_LIMIT_MAX_PER_HOUR:
        raise RateLimitedError(
            "Zbyt wiele zgłoszeń w ciągu ostatniej godziny - spróbuj ponownie później."
        )


def submit_feedback(
    db: Session, user_id: str, payload: LegalFeedbackCreateRequest
) -> LegalFeedback:
    entry = (
        db.query(RequestLogEntry)
        .filter(RequestLogEntry.id == payload.request_log_entry_id)
        .one_or_none()
    )
    # 404 zarówno gdy wpis nie istnieje, jak i gdy należy do innej sesji - nigdy nie
    # potwierdzamy cudzej sesji istnienia konkretnego wpisu (IDOR).
    if entry is None or entry.user_id is None or entry.user_id != user_id:
        raise NotFoundError(
            f"Nie znaleziono oceny o id={payload.request_log_entry_id} dla tej sesji"
        )

    _check_rate_limit(db, user_id)

    rules_version = None
    if isinstance(entry.response_payload, dict):
        rules_version = entry.response_payload.get("rules_version")

    feedback = LegalFeedback(
        request_log_entry_id=entry.id,
        user_id=user_id,
        benefit_code=entry.benefit_code,
        feedback_type=payload.feedback_type,
        user_comment=payload.user_comment,
        expected_result=payload.expected_result.value if payload.expected_result else None,
        status=LegalFeedbackStatus.new,
        rules_version=rules_version,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
