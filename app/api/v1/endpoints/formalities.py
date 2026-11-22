from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.eligibility.registry import ELIGIBILITY_EVALUATORS
from app.eligibility.rules_repository import get_current_rule
from app.eligibility.schemas import RequiredDocument
from app.formalities.content import (
    CHARITABLE_SUPPORT_NOTE,
    DIFFICULT_SITUATION_BENEFIT_CODES,
    EMPLOYMENT_PROTECTION_NOTE,
    GENERAL_RISKS,
    HOW_BENEFITS_ARE_PAID,
    build_next_steps,
)
from app.formalities.schemas import FormalitiesGuide, GeneralFormalitiesGuide

router = APIRouter(prefix="/formalities", tags=["formalities"])


@router.get(
    "/general",
    response_model=GeneralFormalitiesGuide,
    summary="Ogólny przewodnik po formalnościach (niezależny od konkretnego świadczenia)",
)
async def get_general_guide() -> GeneralFormalitiesGuide:
    return GeneralFormalitiesGuide(
        how_benefits_are_paid=HOW_BENEFITS_ARE_PAID,
        general_risks=GENERAL_RISKS,
        employment_protection_note=EMPLOYMENT_PROTECTION_NOTE,
        charitable_support_note=CHARITABLE_SUPPORT_NOTE,
        difficult_situation_benefit_codes=DIFFICULT_SITUATION_BENEFIT_CODES,
    )


@router.get(
    "/{benefit_code}",
    response_model=FormalitiesGuide,
    summary="Przewodnik po formalnościach dla wskazanego świadczenia",
)
async def get_benefit_guide(benefit_code: str, db: Session = Depends(get_db)) -> FormalitiesGuide:
    if benefit_code not in ELIGIBILITY_EVALUATORS:
        raise NotFoundError(f"Nieznany kod świadczenia: '{benefit_code}'")
    rule = get_current_rule(db, benefit_code)
    required_documents = [
        RequiredDocument(code=doc["code"], name=doc["name"], when=doc["when"])
        for doc in rule.required_documents
    ]
    return FormalitiesGuide(
        benefit_code=benefit_code,
        benefit_name=rule.benefit_type.name,
        institution=rule.institution,
        required_documents=required_documents,
        deadlines=list(rule.deadlines),
        legal_basis=list(rule.legal_basis),
        general_risks=GENERAL_RISKS,
        employment_protection_note=EMPLOYMENT_PROTECTION_NOTE,
        next_steps=build_next_steps(benefit_code, rule.institution),
        rules_version=rule.version,
    )
