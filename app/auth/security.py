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


def create_user_token(user_id: str, status_: AuthStatus) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.user_access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "status": status_.value,
        "exp": expire,
        "type": _TOKEN_TYPE,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Brak sesji - wywołaj najpierw POST /auth/session",
        )

    settings = get_settings()
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowa lub wygasła sesja",
        ) from exc

    if payload.get("type") != _TOKEN_TYPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy token")

    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Użytkownik nie istnieje"
        )

    return user


def require_authenticated_user(user: User = Depends(get_current_user)) -> User:
    if user.status != AuthStatus.authenticated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ta funkcja wymaga zalogowania (symulowane mObywatel)",
        )
    return user
