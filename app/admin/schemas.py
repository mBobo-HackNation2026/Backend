from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
