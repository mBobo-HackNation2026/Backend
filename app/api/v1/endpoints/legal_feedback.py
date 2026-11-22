from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.legal_feedback.schemas import LegalFeedbackCreateRequest, LegalFeedbackResponse
from app.legal_feedback.service import submit_feedback

router = APIRouter(prefix="/legal-feedback", tags=["legal-feedback"])


@router.post(
    "",
    response_model=LegalFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Zgłoś wątpliwość co do wyniku oceny uprawnień (wymaga sesji)",
)
async def create_legal_feedback(
    payload: LegalFeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LegalFeedbackResponse:
    return submit_feedback(db, current_user.id, payload)
