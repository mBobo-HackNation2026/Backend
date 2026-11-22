from collections.abc import Generator
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.db import models  # noqa: F401  (registers models on Base.metadata)
from app.rules.seed import ensure_seeded

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Schemat jest teraz zarządzany wyłącznie przez Alembic (alembic/versions/), nigdy
# przez Base.metadata.create_all() - to był root cause dzisiejszego
# "no such column: request_log_entries.user_id": zmiana modelu bez odpowiadającej
# migracji nigdy nie trafia do już istniejącego pliku bazy. "alembic upgrade head"
# tutaj działa identycznie dla świeżej bazy (uruchamia migracje od zera) i dla
# istniejącej starszej bazy (dogania tylko brakujące migracje, zachowując dane).
_ALEMBIC_INI_PATH = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
# Jedyna tabela, której istnienie jednoznacznie świadczy, że ta baza była już
# utworzona (jakimkolwiek sposobem) przed wprowadzeniem Alembic.
_LEGACY_MARKER_TABLE = "benefit_types"


def upgrade_or_stamp_legacy(target_engine, alembic_cfg: Config) -> None:
    """Shared by app startup and tests/test_db_migrations.py - never duplicate this
    logic, it's the one place deciding "fresh db -> run every migration" vs. "db
    already existed before Alembic -> stamp, don't replay CREATE TABLE"."""
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())

    if _LEGACY_MARKER_TABLE in existing_tables and "alembic_version" not in existing_tables:
        # Baza istniała już przed wprowadzeniem Alembic (utworzona przez stare
        # Base.metadata.create_all(), jak app.db z tej sesji przed dzisiejszą
        # zmianą) - jej schemat już odpowiada aktualnym modelom (to one zasilały
        # create_all), więc tylko oznaczamy ją jako "head", bez ponownego
        # wykonywania CREATE TABLE/ALTER TABLE, które by się nie powiodły na
        # już istniejących obiektach. Jednorazowy krok przejścia - każda baza
        # utworzona OD TERAZ przechodzi normalnie przez "upgrade" od zera.
        command.stamp(alembic_cfg, "head")
        return

    command.upgrade(alembic_cfg, "head")


def _run_migrations() -> None:
    alembic_cfg = Config(str(_ALEMBIC_INI_PATH))
    upgrade_or_stamp_legacy(engine, alembic_cfg)


_run_migrations()

with SessionLocal() as _seed_session:
    ensure_seeded(_seed_session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
