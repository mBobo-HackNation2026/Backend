from pydantic import BaseModel

from app.db.models.user import AuthStatus


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    status: AuthStatus


class MobywatelLoginRequest(BaseModel):
    """Dane logowania są w pełni symulowane - nie łączymy się z prawdziwym mObywatel."""

    pesel: str | None = None


class UserProfile(BaseModel):
    user_id: str
    status: AuthStatus
    first_name: str | None = None
    last_name: str | None = None
    pesel: str | None = None
