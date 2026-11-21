from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType
from app.db.session import SessionLocal
from app.rules.seed import MATERNITY_LEAVE_BENEFIT_CODE, ensure_seeded


def test_ensure_seeded_creates_exactly_one_current_rule() -> None:
    db = SessionLocal()
    try:
        ensure_seeded(db)
        ensure_seeded(db)  # must be idempotent

        count = (
            db.query(BenefitRuleVersion)
            .join(BenefitType)
            .filter(
                BenefitType.code == MATERNITY_LEAVE_BENEFIT_CODE,
                BenefitRuleVersion.is_current.is_(True),
            )
            .count()
        )
        assert count == 1
    finally:
        db.close()
