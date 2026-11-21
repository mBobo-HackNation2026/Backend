from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.user import AuthStatus, User
from app.db.session import get_db

_bearer_scheme = HTTPBearer(auto_error=False)

_ALGORITHM = "HS256"
_TOKEN_TYPE = "user"


def create_user_token(user_id: str, status_: AuthStatus, token_version: int) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.user_access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "status": status_.value,
        "exp": expire,
        "type": _TOKEN_TYPE,
        "tv": token_version,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def _decode_user_token(
    credentials: HTTPAuthorizationCredentials | None, *, verify_exp: bool
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Brak sesji - wywołaj najpierw POST /auth/session",
        )

    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[_ALGORITHM],
            options={"verify_exp": verify_exp},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowa lub wygasła sesja",
        ) from exc

    if payload.get("type") != _TOKEN_TYPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy token")

    return payload


def _load_user_for_token(payload: dict, db: Session) -> User:
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Użytkownik nie istnieje"
        )
    if payload.get("tv") != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesja została unieważniona (wylogowano) - utwórz nową sesję przez "
            "POST /auth/session",
        )
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = _decode_user_token(credentials, verify_exp=True)
    return _load_user_for_token(payload, db)


def get_user_for_refresh(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Like ``get_current_user``, but accepts an already-expired token - the whole point
    of /auth/refresh is to renew a session *after* its token expired. Revocation via
    ``token_version`` (bumped by /auth/logout) still applies, so a logged-out session
    cannot be refreshed back to life just because its token hasn't expired yet either.
    """
    payload = _decode_user_token(credentials, verify_exp=False)
    return _load_user_for_token(payload, db)


def require_authenticated_user(user: User = Depends(get_current_user)) -> User:
    if user.status != AuthStatus.authenticated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ta funkcja wymaga zalogowania (symulowane mObywatel)",
        )
    return user
