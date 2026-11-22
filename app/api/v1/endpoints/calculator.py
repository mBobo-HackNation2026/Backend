from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.admin.request_log import log_request
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
    result = calculate_benefit(benefit_code, rule, payload)
    log_request(
        db,
        endpoint="calculate",
        benefit_code=benefit_code,
        status_code=200,
        request_payload=payload.model_dump(mode="json"),
        response_payload=result.model_dump(mode="json"),
    )
    return result


@router.post(
    "/compare/urlop-rodzicielski",
    response_model=ParentalLeaveCompareResponse,
    summary="Porównaj warianty podziału urlopu rodzicielskiego między rodzicami",
)
async def compare_parental_leave(
    payload: ParentalLeaveCompareRequest, db: Session = Depends(get_db)
) -> ParentalLeaveCompareResponse:
    rule = get_current_rule(db, PARENTAL_LEAVE_BENEFIT_CODE)
    result = compare_parental_leave_variants(rule, payload)
    log_request(
        db,
        endpoint="compare_parental_leave",
        benefit_code=PARENTAL_LEAVE_BENEFIT_CODE,
        status_code=200,
        request_payload=payload.model_dump(mode="json"),
        response_payload=result.model_dump(mode="json"),
    )
    return result
