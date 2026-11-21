from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType


def get_current_rule(db: Session, benefit_code: str) -> BenefitRuleVersion:
    rule = (
        db.query(BenefitRuleVersion)
        .join(BenefitType)
        .filter(BenefitType.code == benefit_code, BenefitRuleVersion.is_current.is_(True))
        .one_or_none()
    )
    if rule is None:
        raise NotFoundError(f"Brak aktualnych reguł dla świadczenia '{benefit_code}'")
    return rule
