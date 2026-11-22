import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.admin.request_log import get_request_log_entry, list_request_log_entries
from app.admin.schemas import (
    AdminInfo,
    AdminLoginRequest,
    AdminTokenResponse,
    RequestLogEntryDetail,
    RequestLogEntrySummary,
)
from app.admin.security import create_admin_access_token, get_current_admin
from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/login",
    response_model=AdminTokenResponse,
    summary="Logowanie do panelu administracyjnego",
)
async def login(
    payload: AdminLoginRequest, settings: Settings = Depends(get_settings)
) -> AdminTokenResponse:
    valid_username = secrets.compare_digest(payload.username, settings.admin_username)
    valid_password = secrets.compare_digest(payload.password, settings.admin_password)
    if not (valid_username and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy login lub hasło",
        )

    token = create_admin_access_token(subject=payload.username)
    return AdminTokenResponse(access_token=token)


@router.get("/me", response_model=AdminInfo, summary="Dane zalogowanego administratora")
async def me(current_admin: str = Depends(get_current_admin)) -> AdminInfo:
    return AdminInfo(username=current_admin)


@router.get("/dashboard", summary="Podsumowanie panelu administracyjnego (placeholder)")
async def dashboard(current_admin: str = Depends(get_current_admin)) -> dict:
    return {
        "message": "Panel administracyjny eBobo - funkcjonalności w budowie",
        "modules": [
            {"key": "rules", "label": "Parametry świadczeń", "status": "planned"},
            {"key": "submissions", "label": "Wnioski użytkowników", "status": "available"},
            {"key": "documents", "label": "Przesłane dokumenty PDF", "status": "planned"},
            {"key": "integrations", "label": "Integracje ZUS / mObywatel", "status": "planned"},
        ],
    }


@router.get(
    "/request-log",
    response_model=list[RequestLogEntrySummary],
    summary="Lista zarejestrowanych wniosków (zapytań do silnika uprawnień/kalkulatora)",
)
async def list_request_log(
    benefit_code: str | None = None,
    limit: int = 50,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[RequestLogEntrySummary]:
    return list_request_log_entries(db, benefit_code=benefit_code, limit=limit)


@router.get(
    "/request-log/{entry_id}",
    response_model=RequestLogEntryDetail,
    summary="Szczegóły pojedynczego wniosku - pełny request i response (tylko do odczytu)",
)
async def get_request_log_detail(
    entry_id: int,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> RequestLogEntryDetail:
    entry = get_request_log_entry(db, entry_id)
    if entry is None:
        raise NotFoundError(f"Nie znaleziono wpisu o id={entry_id}")
    return entry
