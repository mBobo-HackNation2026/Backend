from decimal import Decimal

from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType
from app.db.session import SessionLocal
from app.rules.seed import (
    ALTERNATIVE_BENEFIT_CODE,
    MATERNITY_LEAVE_BENEFIT_CODE,
    PATERNITY_LEAVE_BENEFIT_CODE,
    ensure_seeded,
)


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


def test_seeded_rule_has_z3_for_standard_and_none_for_self_employed() -> None:
    """Z-3 is tagged "standard" (non-self-employed titles only). Self-employed-like
    titles historically filed Z-3b, abolished 2026-10-24 with no documented
    replacement - per the project's "never fabricate" rule, no document is seeded
    for them; the engine surfaces a warning instead (see test_eligibility_engine.py)."""
    db = SessionLocal()
    try:
        ensure_seeded(db)

        rule = (
            db.query(BenefitRuleVersion)
            .join(BenefitType)
            .filter(
                BenefitType.code == MATERNITY_LEAVE_BENEFIT_CODE,
                BenefitRuleVersion.is_current.is_(True),
            )
            .one()
        )
        docs_by_code = {doc["code"]: doc for doc in rule.required_documents}

        assert docs_by_code["zaswiadczenie_z3"]["applies_to"] == "standard"
        assert "zaswiadczenie_z3a" not in docs_by_code
    finally:
        db.close()


def test_seeded_maternity_leave_rule_has_institution_and_deadlines() -> None:
    db = SessionLocal()
    try:
        ensure_seeded(db)

        rule = (
            db.query(BenefitRuleVersion)
            .join(BenefitType)
            .filter(
                BenefitType.code == MATERNITY_LEAVE_BENEFIT_CODE,
                BenefitRuleVersion.is_current.is_(True),
            )
            .one()
        )

        assert "Pracodawca" in rule.institution
        assert rule.deadlines
        assert rule.duration_until_birth is False
    finally:
        db.close()


def test_ensure_seeded_creates_alternative_benefit_rule() -> None:
    db = SessionLocal()
    try:
        ensure_seeded(db)
        ensure_seeded(db)  # must be idempotent, same as the maternity-leave rule

        rule = (
            db.query(BenefitRuleVersion)
            .join(BenefitType)
            .filter(
                BenefitType.code == ALTERNATIVE_BENEFIT_CODE,
                BenefitRuleVersion.is_current.is_(True),
            )
            .one()
        )

        assert rule.duration_until_birth is True
        assert rule.weeks_by_child_count is None
        assert rule.institution == "ZUS"
        assert rule.rate_percentage == Decimal("100.00")
        doc_codes = {doc["code"] for doc in rule.required_documents}
        assert "zaswiadczenie_z3" not in doc_codes
        assert "zaswiadczenie_z3a" not in doc_codes
    finally:
        db.close()


def test_ensure_seeded_creates_paternity_leave_rule() -> None:
    db = SessionLocal()
    try:
        ensure_seeded(db)
        ensure_seeded(db)  # must be idempotent

        rule = (
            db.query(BenefitRuleVersion)
            .join(BenefitType)
            .filter(
                BenefitType.code == PATERNITY_LEAVE_BENEFIT_CODE,
                BenefitRuleVersion.is_current.is_(True),
            )
            .one()
        )

        assert rule.rate_percentage == Decimal("100.00")
        assert rule.weeks_by_child_count == {"1": 2, "2": 2, "3": 2, "4": 2, "5+": 2}
        assert rule.duration_until_birth is False
    finally:
        db.close()
