from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.eligibility.engine import BENEFIT_CODE, evaluate_maternity_leave_eligibility
from app.eligibility.rules_repository import get_current_rule
from app.eligibility.schemas import EligibilityResult, MaternityLeaveEligibilityRequest

router = APIRouter(prefix="/eligibility", tags=["eligibility"])


@router.post(
    "/check",
    response_model=EligibilityResult,
    summary="Oceń uprawnienie do zasiłku macierzyńskiego za okres urlopu macierzyńskiego",
)
async def check_eligibility(
    payload: MaternityLeaveEligibilityRequest, db: Session = Depends(get_db)
) -> EligibilityResult:
    rule = get_current_rule(db, BENEFIT_CODE)
    return evaluate_maternity_leave_eligibility(payload, rule)
