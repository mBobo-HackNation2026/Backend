from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.schemas import MobywatelLoginRequest, SessionResponse, UserProfile
from app.auth.security import create_user_token, get_current_user, get_user_for_refresh
from app.db.models.user import AuthStatus, User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

# Symulowana tożsamość zwracana po "zalogowaniu przez mObywatel" - nie ma
# żadnego realnego połączenia z mObywatel/PUE, to tylko przykładowe dane
# demonstracyjne (patrz brief: logowanie ma być wyłącznie zasymulowane).
_MOCK_MOBYWATEL_FIRST_NAME = "Jan"
_MOCK_MOBYWATEL_LAST_NAME = "Kowalski"
_MOCK_MOBYWATEL_PESEL = "90010112345"


@router.post(
    "/session",
    response_model=SessionResponse,
    summary="Utwórz anonimową sesję (wywoływane przy pierwszym otwarciu aplikacji)",
)
async def create_session(db: Session = Depends(get_db)) -> SessionResponse:
    user = User(status=AuthStatus.anonymous)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_user_token(user.id, user.status, user.token_version)
    return SessionResponse(access_token=token, user_id=user.id, status=user.status)


@router.post(
    "/mobywatel/login",
    response_model=SessionResponse,
    summary="Symulowane logowanie przez mObywatel (podnosi istniejącą sesję do 'authenticated')",
)
async def mobywatel_login(
    payload: MobywatelLoginRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionResponse:
    user.status = AuthStatus.authenticated
    user.first_name = _MOCK_MOBYWATEL_FIRST_NAME
    user.last_name = _MOCK_MOBYWATEL_LAST_NAME
    user.pesel = payload.pesel or _MOCK_MOBYWATEL_PESEL
    user.authenticated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)

    token = create_user_token(user.id, user.status, user.token_version)
    return SessionResponse(access_token=token, user_id=user.id, status=user.status)


@router.get("/me", response_model=UserProfile, summary="Dane bieżącego użytkownika")
async def me(user: User = Depends(get_current_user)) -> UserProfile:
    return UserProfile(
        user_id=user.id,
        status=user.status,
        first_name=user.first_name,
        last_name=user.last_name,
        pesel=user.pesel,
    )


@router.post(
    "/refresh",
    response_model=SessionResponse,
    summary="Odśwież sesję (działa nawet gdy token już wygasł), zachowując ten sam user_id",
)
async def refresh_session(
    user: User = Depends(get_user_for_refresh), db: Session = Depends(get_db)
) -> SessionResponse:
    token = create_user_token(user.id, user.status, user.token_version)
    return SessionResponse(access_token=token, user_id=user.id, status=user.status)


@router.post(
    "/logout",
    response_model=SessionResponse,
    summary="Wyloguj (unieważnia bieżącą sesję) i wróć do nowej sesji anonimowej",
)
async def logout(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SessionResponse:
    # Bump token_version so every token issued for this user (access tokens already
    # handed out, and anything that could still be silently refreshed via
    # /auth/refresh) stops validating from this point on.
    user.token_version += 1
    db.commit()

    new_user = User(status=AuthStatus.anonymous)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_user_token(new_user.id, new_user.status, new_user.token_version)
    return SessionResponse(access_token=token, user_id=new_user.id, status=new_user.status)
