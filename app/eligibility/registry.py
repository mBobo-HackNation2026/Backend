"""Rejestr dostępnych świadczeń: mapowanie kodu świadczenia na funkcję oceny.

Rozszerzenie silnika o nowe świadczenie (kolejne części Fazy 2) = dodanie wpisu tutaj,
po zaimplementowaniu funkcji oceny w ``app/eligibility/engine.py`` i zasileniu reguły w
``app/rules/seed.py``. Każdy zarejestrowany kod musi mieć odpowiadającą, aktualną wersję
reguły w bazie (patrz ``app/eligibility/rules_repository.py``) - w przeciwnym razie
``get_current_rule`` zgłosi ``NotFoundError`` mimo zarejestrowanego kodu.
"""

from collections.abc import Callable

from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.engine import (
    ADOPTION_LEAVE_BENEFIT_CODE,
    ALTERNATIVE_BENEFIT_CODE,
    BENEFIT_CODE,
    PARENTAL_LEAVE_BENEFIT_CODE,
    PATERNITY_LEAVE_BENEFIT_CODE,
    REHABILITATION_BENEFIT_CODE,
    SICKNESS_DURING_PREGNANCY_BENEFIT_CODE,
    STILLBIRTH_FUNERAL_BENEFIT_CODE,
    SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
    evaluate_adoption_leave_eligibility,
    evaluate_alternative_maternity_benefit_eligibility,
    evaluate_maternity_leave_eligibility,
    evaluate_parental_leave_eligibility,
    evaluate_paternity_leave_eligibility,
    evaluate_rehabilitation_benefit_eligibility,
    evaluate_sickness_benefit_during_pregnancy_eligibility,
    evaluate_stillbirth_funeral_benefit_eligibility,
    evaluate_supplementary_maternity_leave_eligibility,
)
from app.eligibility.schemas import EligibilityResult, MaternityLeaveEligibilityRequest

EligibilityEvaluator = Callable[
    [MaternityLeaveEligibilityRequest, BenefitRuleVersion], EligibilityResult
]

ELIGIBILITY_EVALUATORS: dict[str, EligibilityEvaluator] = {
    BENEFIT_CODE: evaluate_maternity_leave_eligibility,
    ALTERNATIVE_BENEFIT_CODE: evaluate_alternative_maternity_benefit_eligibility,
    PATERNITY_LEAVE_BENEFIT_CODE: evaluate_paternity_leave_eligibility,
    PARENTAL_LEAVE_BENEFIT_CODE: evaluate_parental_leave_eligibility,
    SICKNESS_DURING_PREGNANCY_BENEFIT_CODE: evaluate_sickness_benefit_during_pregnancy_eligibility,
    REHABILITATION_BENEFIT_CODE: evaluate_rehabilitation_benefit_eligibility,
    # Stubs (Faza 2, not yet implemented - see app/eligibility/engine.py's
    # "STUB BENEFITS" note and project memory `project-ebobo-stub-benefits-debt`):
    SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE: evaluate_supplementary_maternity_leave_eligibility,
    ADOPTION_LEAVE_BENEFIT_CODE: evaluate_adoption_leave_eligibility,
    STILLBIRTH_FUNERAL_BENEFIT_CODE: evaluate_stillbirth_funeral_benefit_eligibility,
}
