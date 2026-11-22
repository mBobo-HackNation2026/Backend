import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.admin.request_log import get_request_log_entry, list_request_log_entries
from app.admin.schemas import (
    AdminInfo,
    AdminLoginRequest,
    AdminTokenResponse,
    LegalFeedbackAdminDetail,
    LegalFeedbackAdminSummary,
    LegalFeedbackAnalysisResponse,
    LegalFeedbackStatusUpdateRequest,
    RequestLogEntryDetail,
    RequestLogEntrySummary,
)
from app.admin.security import create_admin_access_token, get_current_admin
from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.engine_quality import service as engine_quality_service
from app.engine_quality.schemas import (
    EngineQualityCaseAnalysisResponse,
    EngineQualityCaseDetail,
    EngineQualityCasePriorityUpdateRequest,
    EngineQualityCaseStatusUpdateRequest,
    EngineQualityCaseSummary,
)
from app.legal_feedback.admin_service import (
    get_feedback_detail,
    list_feedback,
    run_analysis,
    update_status,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/login",
    response_model=AdminTokenResponse,
    summary="Logowanie do panelu administracyjnego",
)
async def login(
    payload: AdminLoginRequest, settings: Settings = Depends(get_settings)
) -> AdminTokenResponse:
    valid_username = secrets.compare_digest(payload.username, settings.admin_username)
    valid_password = secrets.compare_digest(payload.password, settings.admin_password)
    if not (valid_username and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy login lub hasło",
        )

    token = create_admin_access_token(subject=payload.username)
    return AdminTokenResponse(access_token=token)


@router.get("/me", response_model=AdminInfo, summary="Dane zalogowanego administratora")
async def me(current_admin: str = Depends(get_current_admin)) -> AdminInfo:
    return AdminInfo(username=current_admin)


@router.get("/dashboard", summary="Podsumowanie panelu administracyjnego (placeholder)")
async def dashboard(current_admin: str = Depends(get_current_admin)) -> dict:
    return {
        "message": "Panel administracyjny eBobo - funkcjonalności w budowie",
        "modules": [
            {"key": "rules", "label": "Parametry świadczeń", "status": "planned"},
            {"key": "submissions", "label": "Wnioski użytkowników", "status": "available"},
            {"key": "documents", "label": "Przesłane dokumenty PDF", "status": "planned"},
            {"key": "integrations", "label": "Integracje ZUS / mObywatel", "status": "planned"},
        ],
    }


@router.get(
    "/request-log",
    response_model=list[RequestLogEntrySummary],
    summary="Lista zarejestrowanych wniosków (zapytań do silnika uprawnień/kalkulatora)",
)
async def list_request_log(
    benefit_code: str | None = None,
    limit: int = 50,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[RequestLogEntrySummary]:
    return list_request_log_entries(db, benefit_code=benefit_code, limit=limit)


@router.get(
    "/request-log/{entry_id}",
    response_model=RequestLogEntryDetail,
    summary="Szczegóły pojedynczego wniosku - pełny request i response (tylko do odczytu)",
)
async def get_request_log_detail(
    entry_id: int,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> RequestLogEntryDetail:
    entry = get_request_log_entry(db, entry_id)
    if entry is None:
        raise NotFoundError(f"Nie znaleziono wpisu o id={entry_id}")
    return entry


def _build_admin_detail(
    feedback, original_entry, analyses, status_history
) -> LegalFeedbackAdminDetail:
    return LegalFeedbackAdminDetail(
        id=feedback.id,
        request_log_entry_id=feedback.request_log_entry_id,
        user_id=feedback.user_id,
        benefit_code=feedback.benefit_code,
        feedback_type=feedback.feedback_type,
        status=feedback.status,
        rules_version=feedback.rules_version,
        created_at=feedback.created_at,
        user_comment=feedback.user_comment,
        expected_result=feedback.expected_result,
        original_evaluation=original_entry,
        analyses=analyses,
        status_history=status_history,
    )


@router.get(
    "/legal-feedback",
    response_model=list[LegalFeedbackAdminSummary],
    summary="Lista zgłoszeń wątpliwości co do oceny uprawnień (eBobo Legal Intelligence, Etap 2)",
)
async def list_legal_feedback(
    benefit_code: str | None = None,
    feedback_type: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order: str = "desc",
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[LegalFeedbackAdminSummary]:
    return list_feedback(
        db,
        benefit_code=benefit_code,
        feedback_type=feedback_type,
        status=status_filter,
        limit=limit,
        offset=offset,
        order=order,
    )


@router.get(
    "/legal-feedback/{feedback_id}",
    response_model=LegalFeedbackAdminDetail,
    summary="Szczegóły zgłoszenia: oryginalna ocena, historia analiz AI i historia statusów",
)
async def get_legal_feedback_detail(
    feedback_id: int,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> LegalFeedbackAdminDetail:
    feedback, original_entry, analyses, status_history = get_feedback_detail(db, feedback_id)
    return _build_admin_detail(feedback, original_entry, analyses, status_history)


@router.post(
    "/legal-feedback/{feedback_id}/analyze",
    response_model=LegalFeedbackAnalysisResponse,
    summary="Uruchom analizę prawną zgłoszenia przez OpenRouter (hipoteza, nie potwierdzony błąd)",
)
async def analyze_legal_feedback(
    feedback_id: int,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> LegalFeedbackAnalysisResponse:
    return run_analysis(db, feedback_id)


@router.patch(
    "/legal-feedback/{feedback_id}/status",
    response_model=LegalFeedbackAdminDetail,
    summary="Zmień status zgłoszenia (decyzja administratora, zapisywana w historii)",
)
async def update_legal_feedback_status(
    feedback_id: int,
    payload: LegalFeedbackStatusUpdateRequest,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> LegalFeedbackAdminDetail:
    update_status(db, feedback_id, payload.status, payload.reason, current_admin)
    feedback, original_entry, analyses, status_history = get_feedback_detail(db, feedback_id)
    return _build_admin_detail(feedback, original_entry, analyses, status_history)


def _build_engine_quality_detail(case, history, analyses) -> EngineQualityCaseDetail:
    return EngineQualityCaseDetail(
        id=case.id,
        signal_type=case.signal_type,
        benefit_code=case.benefit_code,
        rules_version=case.rules_version,
        problem_id=case.problem_id,
        request_log_entry_id=case.request_log_entry_id,
        legal_feedback_id=case.legal_feedback_id,
        reason=case.reason,
        group_key=case.group_key,
        occurrence_count=case.occurrence_count,
        priority=case.priority,
        status=case.status,
        detected_at=case.detected_at,
        updated_at=case.updated_at,
        history=history,
        analyses=analyses,
    )


@router.get(
    "/engine-quality/cases",
    response_model=list[EngineQualityCaseSummary],
    summary="Lista spraw w wewnętrznej kolejce monitoringu jakości silnika (Etap 3)",
)
async def list_engine_quality_cases(
    signal_type: str | None = None,
    benefit_code: str | None = None,
    status_filter: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order: str = "desc",
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[EngineQualityCaseSummary]:
    return engine_quality_service.list_cases(
        db,
        signal_type=signal_type,
        benefit_code=benefit_code,
        status=status_filter,
        priority=priority,
        limit=limit,
        offset=offset,
        order=order,
    )


@router.get(
    "/engine-quality/cases/{case_id}",
    response_model=EngineQualityCaseDetail,
    summary="Szczegóły sprawy: historia zmian statusu/priorytetu i historia analiz AI",
)
async def get_engine_quality_case_detail(
    case_id: int,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> EngineQualityCaseDetail:
    case, history, analyses = engine_quality_service.get_case_detail(db, case_id)
    return _build_engine_quality_detail(case, history, analyses)


@router.patch(
    "/engine-quality/cases/{case_id}/status",
    response_model=EngineQualityCaseDetail,
    summary="Zmień status sprawy (decyzja administratora, zapisywana w historii)",
)
async def update_engine_quality_case_status(
    case_id: int,
    payload: EngineQualityCaseStatusUpdateRequest,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> EngineQualityCaseDetail:
    engine_quality_service.update_status(db, case_id, payload.status, payload.reason, current_admin)
    case, history, analyses = engine_quality_service.get_case_detail(db, case_id)
    return _build_engine_quality_detail(case, history, analyses)


@router.patch(
    "/engine-quality/cases/{case_id}/priority",
    response_model=EngineQualityCaseDetail,
    summary="Zmień priorytet sprawy (decyzja administratora, zapisywana w historii)",
)
async def update_engine_quality_case_priority(
    case_id: int,
    payload: EngineQualityCasePriorityUpdateRequest,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> EngineQualityCaseDetail:
    engine_quality_service.update_priority(
        db, case_id, payload.priority, payload.reason, current_admin
    )
    case, history, analyses = engine_quality_service.get_case_detail(db, case_id)
    return _build_engine_quality_detail(case, history, analyses)


@router.post(
    "/engine-quality/cases/{case_id}/analyze",
    response_model=EngineQualityCaseAnalysisResponse,
    summary="Uruchom analizę prawną sprawy przez OpenRouter (hipoteza, nie potwierdzony błąd)",
)
async def analyze_engine_quality_case(
    case_id: int,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> EngineQualityCaseAnalysisResponse:
    return engine_quality_service.run_case_analysis(db, case_id)
