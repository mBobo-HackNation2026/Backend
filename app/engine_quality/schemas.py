from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.engine_quality import (
    EngineQualityCasePriority,
    EngineQualityCaseStatus,
    EngineQualitySignalType,
)
from app.legal_feedback.schemas import AIFeedbackAnalysisRaw

# Ta sama struktura co AIFeedbackAnalysisRaw (Etap 2 Faza B) - ten sam kształt
# odpowiedzi AI, ta sama walidacja. Osobny alias (nie dziedziczenie), żeby każdy moduł
# mógł ewoluować niezależnie, gdyby kiedyś potrzeby się rozjechały.
AIEngineQualityAnalysisRaw = AIFeedbackAnalysisRaw


class EngineQualityCaseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    signal_type: EngineQualitySignalType
    benefit_code: str | None
    rules_version: int | None
    problem_id: str | None
    request_log_entry_id: int | None
    legal_feedback_id: int | None
    reason: str
    group_key: str
    occurrence_count: int
    priority: EngineQualityCasePriority
    status: EngineQualityCaseStatus
    detected_at: datetime
    updated_at: datetime


class EngineQualityCaseHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    field_changed: str
    old_value: str
    new_value: str
    changed_by: str
    reason: str | None
    changed_at: datetime


class EngineQualityCaseAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    engine_quality_case_id: int
    analysis_status: str
    classification: str | None
    summary: str | None
    potential_issue: str | None
    required_information: list[str]
    verified_source_ids: list[str]
    recommended_admin_action: str | None
    requires_human_review: bool
    model_id: str | None
    error_message: str | None
    created_at: datetime


class EngineQualityCaseDetail(EngineQualityCaseSummary):
    history: list[EngineQualityCaseHistoryEntry] = Field(
        description="Historia zmian statusu/priorytetu, najnowsze pierwsze."
    )
    analyses: list[EngineQualityCaseAnalysisResponse] = Field(
        description="Historia uruchomień analizy AI, najnowsze pierwsze."
    )


class EngineQualityCaseStatusUpdateRequest(BaseModel):
    status: EngineQualityCaseStatus
    reason: str | None = Field(default=None, max_length=2000)


class EngineQualityCasePriorityUpdateRequest(BaseModel):
    priority: EngineQualityCasePriority
    reason: str | None = Field(default=None, max_length=2000)
