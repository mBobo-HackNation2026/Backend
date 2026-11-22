from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.legal_feedback import (
    LegalFeedbackAnalysisClassification,
    LegalFeedbackStatus,
    LegalFeedbackType,
)
from app.eligibility.schemas import EligibilityStatus

_MAX_COMMENT_LENGTH = 2000


class LegalFeedbackCreateRequest(BaseModel):
    request_log_entry_id: int = Field(
        description=(
            "Id wpisu w request_log (np. request_log_entry_id z odpowiedzi "
            "/legal-advisor/explain), którego dotyczy zgłoszenie. Musi należeć do "
            "tej samej sesji co zgłaszający, inaczej 404."
        )
    )
    feedback_type: LegalFeedbackType
    user_comment: str = Field(
        min_length=1,
        max_length=_MAX_COMMENT_LENGTH,
        description="Opis zgłaszanego problemu w wolnym tekście.",
    )
    expected_result: EligibilityStatus | None = Field(
        default=None,
        description=(
            "Wyłącznie opinia zgłaszającego o tym, jaki wynik powinien był zapaść - "
            "nigdy nowa ocena uprawnienia i nigdy nie zmienia zapisanego wyniku."
        ),
    )


class LegalFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_log_entry_id: int
    benefit_code: str | None
    feedback_type: LegalFeedbackType
    user_comment: str
    expected_result: EligibilityStatus | None = Field(
        default=None,
        description="Jak w request - opinia zgłaszającego, nie ocena silnika.",
    )
    status: LegalFeedbackStatus
    rules_version: int | None = Field(
        description="Wersja reguł zastosowana przy ORYGINALNEJ ocenie, nie przy zgłoszeniu."
    )
    created_at: datetime


class AIFeedbackAnalysisRaw(BaseModel):
    """Oczekiwany kształt odpowiedzi modelu AI dla analizy zgłoszenia - pierwsza linia
    walidacji (brief Etap 2 Faza B: "Zweryfikuj strukturę odpowiedzi"). Celowo nie ma
    tu pola na zmianę statusu/reguł/kwoty - administrator decyduje o tym osobno, przez
    PATCH .../status, nigdy automatycznie na podstawie tej analizy."""

    classification: LegalFeedbackAnalysisClassification
    summary: str
    potential_issue: str
    required_information: list[str] = Field(default_factory=list)
    cited_fragment_ids: list[str] = Field(default_factory=list)
    recommended_admin_action: str
