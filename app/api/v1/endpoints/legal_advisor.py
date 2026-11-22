from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.security import get_current_user_optional
from app.db.models.user import User
from app.db.session import get_db
from app.eligibility.schemas import MaternityLeaveEligibilityRequest
from app.legal_advisor.schemas import LegalAdvisorExplainResponse
from app.legal_advisor.service import explain_eligibility_result

router = APIRouter(prefix="/legal-advisor", tags=["legal-advisor"])


@router.post(
    "/explain/{benefit_code}",
    response_model=LegalAdvisorExplainResponse,
    summary="Wyjaśnij w prostym języku wynik oceny uprawnień (AI, podparty wynikiem silnika)",
)
async def explain_eligibility(
    benefit_code: str,
    payload: MaternityLeaveEligibilityRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> LegalAdvisorExplainResponse:
    return explain_eligibility_result(
        db, benefit_code, payload, user_id=current_user.id if current_user else None
    )
