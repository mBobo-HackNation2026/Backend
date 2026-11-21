from datetime import date
from decimal import Decimal

from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.engine import evaluate_maternity_leave_eligibility
from app.eligibility.schemas import (
    EligibilityStatus,
    EmploymentEndedReason,
    InsuranceTitle,
    MaternityLeaveEligibilityRequest,
    SolutionType,
)


def _make_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count={"1": 20, "2": 31, "3": 33, "4": 35, "5+": 37},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        legal_basis=["ustawa zasiłkowa art. 29"],
        required_documents=[{"code": "x", "name": "Wniosek", "when": "przed urlopem"}],
    )


def test_insured_mother_one_child_is_likely_eligible() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=True)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks == 20
    assert result.plan.rate_percentage == Decimal("100.00")
    assert not result.unmet_conditions
    assert not result.missing_data


def test_insured_mother_twins_gets_31_weeks() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=2, insured_at_birth=True)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.plan is not None
    assert result.plan.weeks == 31


def test_not_insured_with_no_special_reason_is_not_eligible() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=False)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None
    assert any(s.type == SolutionType.limitation for s in result.possible_solutions)


def test_not_insured_due_to_employer_liquidation_requires_verification() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.upadlosc_likwidacja_smierc_pracodawcy,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert any(
        s.type == SolutionType.alternative_benefit and "art. 30" in (s.legal_basis or "")
        for s in result.possible_solutions
    )


def test_unknown_insurance_status_requires_verification_with_missing_data() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=None)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.missing_data


def test_self_employed_with_debt_over_threshold_is_not_eligible() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        debt_amount_zl=Decimal("100.00"),
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert any(s.type == SolutionType.corrective_action for s in result.possible_solutions)


def test_self_employed_with_debt_under_threshold_is_eligible() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        debt_amount_zl=Decimal("10.00"),
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible


def test_self_employed_missing_debt_info_requires_verification() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        debt_amount_zl=None,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.missing_data
