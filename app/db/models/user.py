import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthStatus(enum.StrEnum):
    anonymous = "anonymous"
    authenticated = "authenticated"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    status: Mapped[AuthStatus] = mapped_column(
        Enum(AuthStatus, native_enum=False, length=20), default=AuthStatus.anonymous
    )

    # Bumped by POST /auth/logout to invalidate every token issued before the bump
    # (embedded in each JWT as "tv" and checked in get_current_user/get_user_for_refresh)
    # - this is the only revocation mechanism available for an otherwise-stateless JWT.
    token_version: Mapped[int] = mapped_column(Integer, default=0)

    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pesel: Mapped[str | None] = mapped_column(String(11), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    authenticated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
