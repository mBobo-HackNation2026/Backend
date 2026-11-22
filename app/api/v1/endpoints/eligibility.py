from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.admin.request_log import log_request
from app.auth.security import get_current_user_optional
from app.core.exceptions import NotFoundError
from app.db.models.engine_quality import EngineQualitySignalType
from app.db.models.user import User
from app.db.session import get_db
from app.eligibility.registry import ELIGIBILITY_EVALUATORS
from app.eligibility.rules_repository import get_current_rule
from app.eligibility.schemas import EligibilityResult, MaternityLeaveEligibilityRequest
from app.engine_quality.service import record_signal_safely

router = APIRouter(prefix="/eligibility", tags=["eligibility"])


@router.post(
    "/check/{benefit_code}",
    response_model=EligibilityResult,
    summary="Oceń uprawnienie do wskazanego świadczenia",
)
async def check_eligibility(
    benefit_code: str,
    payload: MaternityLeaveEligibilityRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> EligibilityResult:
    evaluate = ELIGIBILITY_EVALUATORS.get(benefit_code)
    if evaluate is None:
        # Etap 3: silnik jawnie wskazuje nieobsługiwany przypadek - kod świadczenia nie
        # ma żadnego evaluatora w rejestrze. record_signal_safely nigdy nie rzuca -
        # awaria monitoringu nie może przesłonić poprawnego 404 (Etap 3.1 §5).
        record_signal_safely(
            db,
            signal_type=EngineQualitySignalType.unsupported_case,
            benefit_code=benefit_code,
            reason=f"Nieznany kod świadczenia w rejestrze: '{benefit_code}'",
        )
        raise NotFoundError(f"Nieznany kod świadczenia: '{benefit_code}'")
    rule = get_current_rule(db, benefit_code)
    result = evaluate(payload, rule)
    log_entry = log_request(
        db,
        endpoint="eligibility_check",
        benefit_code=benefit_code,
        status_code=200,
        request_payload=payload.model_dump(mode="json"),
        response_payload=result.model_dump(mode="json"),
        user_id=current_user.id if current_user else None,
    )

    # Etap 3.1: ustrukturyzowane markery jawnie nieobsługiwanych przypadków prawnych,
    # faktycznie wykryte przez ten evaluator (nigdy nie zmieniają status/plan powyżej).
    for marker in result.legal_limitation_markers:
        record_signal_safely(
            db,
            signal_type=EngineQualitySignalType.unsupported_case,
            benefit_code=benefit_code,
            rules_version=rule.version,
            problem_id=marker.rule_id,
            request_log_entry_id=log_entry.id,
            reason=marker.reason,
        )

    return result
