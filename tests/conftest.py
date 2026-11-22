import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.rules.seed import ensure_seeded


@pytest.fixture
def client() -> TestClient:
    """Each test gets its own fresh, in-memory SQLite database - never the real,
    on-disk app.db. Without this, request-log writes (eligibility/calculate/compare/
    legal-advisor) accumulate across test runs and pollute each other's assertions -
    the same class of bug as the shared-dev-db incident, just on the test side."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with testing_session_local() as seed_session:
        ensure_seeded(seed_session)

    def _override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
