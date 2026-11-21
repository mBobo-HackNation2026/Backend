import secrets

from fastapi import APIRouter, Depends, HTTPException, status

from app.admin.schemas import AdminInfo, AdminLoginRequest, AdminTokenResponse
from app.admin.security import create_admin_access_token, get_current_admin
from app.core.config import Settings, get_settings

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
            {"key": "submissions", "label": "Wnioski użytkowników", "status": "planned"},
            {"key": "documents", "label": "Przesłane dokumenty PDF", "status": "planned"},
            {"key": "integrations", "label": "Integracje ZUS / mObywatel", "status": "planned"},
        ],
    }
