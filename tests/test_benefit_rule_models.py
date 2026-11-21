from datetime import date
from decimal import Decimal

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
