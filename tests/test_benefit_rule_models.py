from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType
from app.db.session import SessionLocal


def test_create_and_query_benefit_rule_version() -> None:
    db = SessionLocal()
    try:
        benefit_type = BenefitType(
            code="test_benefit_type_roundtrip",
            name="Testowe świadczenie",
        )
        db.add(benefit_type)
        db.flush()

        rule = BenefitRuleVersion(
            benefit_type_id=benefit_type.id,
            version=1,
            is_current=True,
            effective_from=date(2026, 1, 1),
            rate_percentage=Decimal("100.00"),
            weeks_by_child_count={"1": 20},
            debt_threshold_percent_of_min_wage=Decimal("1.00"),
            min_wage_reference_zl=Decimal("4806.00"),
            legal_basis=["test"],
            required_documents=[{"code": "x", "name": "y", "when": "z"}],
        )
        db.add(rule)
        db.flush()

        fetched = (
            db.query(BenefitRuleVersion)
            .filter_by(benefit_type_id=benefit_type.id)
            .one()
        )
        assert fetched.weeks_by_child_count == {"1": 20}
        assert fetched.rate_percentage == Decimal("100.00")
        assert fetched.legal_basis == ["test"]
    finally:
        db.rollback()
        db.close()


def _rule(benefit_type_id: int, version: int, is_current: bool) -> BenefitRuleVersion:
    return BenefitRuleVersion(
        benefit_type_id=benefit_type_id,
        version=version,
        is_current=is_current,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count={"1": 20},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        legal_basis=["test"],
        required_documents=[],
    )


def test_rejects_second_current_version_for_same_benefit_type() -> None:
    db = SessionLocal()
    try:
        benefit_type = BenefitType(code="test_benefit_type_current_unique", name="Test")
        db.add(benefit_type)
        db.flush()
        db.add(_rule(benefit_type.id, 1, is_current=True))
        db.flush()
        db.add(_rule(benefit_type.id, 2, is_current=True))
        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_rejects_duplicate_version_for_same_benefit_type() -> None:
    db = SessionLocal()
    try:
        benefit_type = BenefitType(code="test_benefit_type_version_unique", name="Test")
        db.add(benefit_type)
        db.flush()
        db.add(_rule(benefit_type.id, 1, is_current=False))
        db.flush()
        db.add(_rule(benefit_type.id, 1, is_current=False))
        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_allows_non_current_versions_alongside_one_current() -> None:
    db = SessionLocal()
    try:
        benefit_type = BenefitType(code="test_benefit_type_many_old", name="Test")
        db.add(benefit_type)
        db.flush()
        db.add(_rule(benefit_type.id, 1, is_current=False))
        db.add(_rule(benefit_type.id, 2, is_current=False))
        db.add(_rule(benefit_type.id, 3, is_current=True))
        db.flush()
    finally:
        db.rollback()
        db.close()
