import pytest

from app.core.exceptions import NotFoundError
from app.db.session import SessionLocal
from app.eligibility.engine import BENEFIT_CODE
from app.eligibility.rules_repository import get_current_rule


def test_get_current_rule_returns_seeded_rule() -> None:
    db = SessionLocal()
    try:
        rule = get_current_rule(db, BENEFIT_CODE)
        assert rule.is_current is True
    finally:
        db.close()


def test_get_current_rule_raises_not_found_for_unknown_code() -> None:
    db = SessionLocal()
    try:
        with pytest.raises(NotFoundError):
            get_current_rule(db, "nieistniejace_swiadczenie")
    finally:
        db.close()
