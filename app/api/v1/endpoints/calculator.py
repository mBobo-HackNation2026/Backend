from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.calculator.engine import calculate_benefit, compare_parental_leave_variants
from app.calculator.schemas import (
    CalculatedAmount,
    ParentalLeaveCompareRequest,
    ParentalLeaveCompareResponse,
)
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.eligibility.registry import ELIGIBILITY_EVALUATORS
from app.eligibility.rules_repository import get_current_rule
from app.eligibility.schemas import MaternityLeaveEligibilityRequest
from app.rules.seed import PARENTAL_LEAVE_BENEFIT_CODE

router = APIRouter(prefix="/benefits", tags=["calculator"])


@router.post(
    "/calculate/{benefit_code}",
    response_model=CalculatedAmount,
    summary="Wylicz kwotę i okres świadczenia (niezależnie od potwierdzonych uprawnień)",
)
async def calculate(
    benefit_code: str, payload: MaternityLeaveEligibilityRequest, db: Session = Depends(get_db)
) -> CalculatedAmount:
    if benefit_code not in ELIGIBILITY_EVALUATORS:
        raise NotFoundError(f"Nieznany kod świadczenia: '{benefit_code}'")
    rule = get_current_rule(db, benefit_code)
    return calculate_benefit(benefit_code, rule, payload)


@router.post(
    "/compare/urlop-rodzicielski",
    response_model=ParentalLeaveCompareResponse,
    summary="Porównaj warianty podziału urlopu rodzicielskiego między rodzicami",
)
async def compare_parental_leave(
    payload: ParentalLeaveCompareRequest, db: Session = Depends(get_db)
) -> ParentalLeaveCompareResponse:
    rule = get_current_rule(db, PARENTAL_LEAVE_BENEFIT_CODE)
    return compare_parental_leave_variants(rule, payload)
