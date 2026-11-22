"""Testy migracji Alembic (eBobo Legal Intelligence Etap 2 Faza B, wymaganie P0:
"stabilne migracje bazy"). Każdy test działa na osobnym, jednorazowym pliku SQLite w
tmp_path - nigdy na app.db ani na conftest.py's per-test in-memory DB."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.config import get_settings
from app.db.session import _ALEMBIC_INI_PATH, upgrade_or_stamp_legacy

_BASELINE_REVISION = "4e7573eced51"
_HEAD_REVISION = "8d4d310a1b3f"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _alembic_config_for(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    return Config(str(_ALEMBIC_INI_PATH))


def test_fresh_database_runs_every_migration_from_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db_path}")
    cfg = _alembic_config_for(db_path, monkeypatch)

    upgrade_or_stamp_legacy(engine, cfg)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "benefit_types",
        "benefit_rule_versions",
        "users",
        "request_log_entries",
        "legal_feedback",
        "legal_feedback_analyses",
        "legal_feedback_status_history",
        "alembic_version",
    } <= tables

    with engine.connect() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert current == _HEAD_REVISION

    # Schema is actually usable, not just present.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO request_log_entries "
                "(created_at, endpoint, benefit_code, status_code, request_payload, "
                "response_payload, user_id) "
                "VALUES (:created_at, 'eligibility_check', 'x', 200, '{}', '{}', NULL)"
            ),
            {"created_at": "2026-11-22 00:00:00"},
        )


def test_older_tracked_database_upgrades_preserving_existing_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The literal regression scenario this P0 requirement exists for: a database
    already tracked by Alembic at an older revision (missing request_log_entries.user_id
    and the legal_feedback table) must upgrade to head without losing its existing
    request_log_entries rows, and the new column must come back NULL for them - never
    silently dropped, never guessed."""
    db_path = tmp_path / "older.db"
    engine = create_engine(f"sqlite:///{db_path}")
    cfg = _alembic_config_for(db_path, monkeypatch)

    # Bring it only as far as the pre-user_id baseline.
    command.upgrade(cfg, _BASELINE_REVISION)

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO request_log_entries "
                "(created_at, endpoint, benefit_code, status_code, request_payload, "
                "response_payload) "
                "VALUES (:created_at, 'eligibility_check', "
                "'zasilek_macierzynski_urlop_macierzynski', 200, "
                "'{\"children_count\": 1}', '{\"status\": \"likely_eligible\"}')"
            ),
            {"created_at": "2026-11-20 10:00:00"},
        )

    upgrade_or_stamp_legacy(engine, cfg)

    with engine.connect() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert current == _HEAD_REVISION

        row = conn.execute(
            text("SELECT endpoint, benefit_code, user_id FROM request_log_entries")
        ).one()
        assert row.endpoint == "eligibility_check"
        assert row.benefit_code == "zasilek_macierzynski_urlop_macierzynski"
        assert row.user_id is None  # new column, old row - never guessed/backfilled

        tables = set(inspect(engine).get_table_names())
        assert "legal_feedback" in tables


def test_legacy_pre_alembic_database_is_stamped_not_recreated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Today's real incident: a database created by the old Base.metadata.create_all()
    (before Alembic existed in this project) already has every current table but no
    alembic_version tracking. upgrade_or_stamp_legacy must stamp it at head instead of
    replaying CREATE TABLE against already-existing objects."""
    db_path = tmp_path / "legacy.db"
    cfg = _alembic_config_for(db_path, monkeypatch)
    # Build it to head first (simulating "already fully up to date"), then drop the
    # tracking table only - exactly what a pre-Alembic create_all()-built app.db looks
    # like: full current schema, zero knowledge of Alembic.
    engine = create_engine(f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO request_log_entries "
                "(created_at, endpoint, benefit_code, status_code, request_payload, "
                "response_payload, user_id) "
                "VALUES ('2026-11-21 09:00:00', 'calculate', 'urlop_ojcowski', 200, "
                "'{}', '{}', NULL)"
            )
        )
        conn.execute(text("DROP TABLE alembic_version"))

    upgrade_or_stamp_legacy(engine, cfg)

    with engine.connect() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert current == _HEAD_REVISION
        row = conn.execute(text("SELECT endpoint FROM request_log_entries")).one()
        assert row.endpoint == "calculate"
