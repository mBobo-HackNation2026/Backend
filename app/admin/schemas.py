from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.legal_feedback import (
    LegalFeedbackAnalysisClassification,
    LegalFeedbackAnalysisStatus,
    LegalFeedbackStatus,
    LegalFeedbackType,
)
from app.eligibility.schemas import EligibilityStatus


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminInfo(BaseModel):
    username: str


class RequestLogEntrySummary(BaseModel):
    """Wiersz listy w widoku 'Wnioski' - bez pełnej treści request/response (to w
    szczegółach), żeby lista ładowała się szybko."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    endpoint: str
    benefit_code: str | None
    status_code: int


class RequestLogEntryDetail(RequestLogEntrySummary):
    request_payload: dict
    response_payload: dict


class LegalFeedbackAnalysisResponse(BaseModel):
    """Jeden, niezmienny wynik uruchomienia analizy AI - zob. docstring
    ``LegalFeedbackAnalysis`` dla pełnego opisu pól."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    legal_feedback_id: int
    analysis_status: LegalFeedbackAnalysisStatus
    classification: LegalFeedbackAnalysisClassification | None
    summary: str | None
    potential_issue: str | None
    required_information: list[str]
    verified_source_ids: list[str]
    recommended_admin_action: str | None
    requires_human_review: bool
    model_id: str | None
    error_message: str | None = Field(
        default=None,
        description="Bezpieczny komunikat diagnostyczny - tylko gdy analysis_status='failed'.",
    )
    created_at: datetime


class LegalFeedbackStatusHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    old_status: LegalFeedbackStatus
    new_status: LegalFeedbackStatus
    changed_by: str
    reason: str | None
    changed_at: datetime


class OriginalEvaluationSummary(BaseModel):
    """Oryginalny, niezmieniany wpis request_log, którego dotyczy zgłoszenie."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint: str
    benefit_code: str | None
    status_code: int
    request_payload: dict
    response_payload: dict
    created_at: datetime


class LegalFeedbackAdminSummary(BaseModel):
    """Wiersz listy w GET /admin/legal-feedback."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    request_log_entry_id: int
    user_id: str
    benefit_code: str | None
    feedback_type: LegalFeedbackType
    status: LegalFeedbackStatus
    rules_version: int | None
    created_at: datetime


class LegalFeedbackAdminDetail(LegalFeedbackAdminSummary):
    user_comment: str
    expected_result: EligibilityStatus | None
    original_evaluation: OriginalEvaluationSummary
    analyses: list[LegalFeedbackAnalysisResponse] = Field(
        description="Historia wszystkich uruchomień analizy AI, najnowsze pierwsze."
    )
    status_history: list[LegalFeedbackStatusHistoryEntry] = Field(
        description="Historia zmian statusu, najnowsze pierwsze."
    )


class LegalFeedbackStatusUpdateRequest(BaseModel):
    status: LegalFeedbackStatus
    reason: str | None = Field(
        default=None, max_length=2000, description="Uzasadnienie decyzji administratora."
    )
