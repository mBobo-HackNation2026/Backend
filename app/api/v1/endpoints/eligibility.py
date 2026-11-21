from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.eligibility.registry import ELIGIBILITY_EVALUATORS
from app.eligibility.rules_repository import get_current_rule
from app.eligibility.schemas import EligibilityResult, MaternityLeaveEligibilityRequest

router = APIRouter(prefix="/eligibility", tags=["eligibility"])


@router.post(
    "/check/{benefit_code}",
    response_model=EligibilityResult,
    summary="Oceń uprawnienie do wskazanego świadczenia",
)
async def check_eligibility(
    benefit_code: str, payload: MaternityLeaveEligibilityRequest, db: Session = Depends(get_db)
) -> EligibilityResult:
    evaluate = ELIGIBILITY_EVALUATORS.get(benefit_code)
    if evaluate is None:
        raise NotFoundError(f"Nieznany kod świadczenia: '{benefit_code}'")
    rule = get_current_rule(db, benefit_code)
    return evaluate(payload, rule)
