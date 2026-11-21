from datetime import date
from decimal import Decimal

from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.engine import (
    ALTERNATIVE_BENEFIT_CODE,
    BENEFIT_CODE,
    evaluate_alternative_maternity_benefit_eligibility,
    evaluate_maternity_leave_eligibility,
    evaluate_paternity_leave_eligibility,
)
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
        institution=(
            "Pracodawca (jeśli zgłasza powyżej 20 ubezpieczonych do ubezpieczenia "
            "chorobowego) albo ZUS"
        ),
        deadlines=[
            "Wniosek o urlop macierzyński - przed rozpoczęciem korzystania z urlopu (lub "
            "łącznie z wnioskiem o urlop rodzicielski)",
        ],
        legal_basis=["ustawa zasiłkowa art. 29"],
        required_documents=[
            {"code": "x", "name": "Wniosek", "when": "przed urlopem", "applies_to": None},
            {"code": "z3", "name": "Zaświadczenie Z-3", "when": "...", "applies_to": "standard"},
        ],
    )


def _make_alternative_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count=None,
        duration_until_birth=True,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        legal_basis=["ustawa zasiłkowa art. 30"],
        deadlines=["Jak najszybciej po ustaniu ubezpieczenia"],
        required_documents=[
            {"code": "wniosek_zam", "name": "Wniosek ZAM", "when": "...", "applies_to": None},
        ],
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
    # The confirmed unmet condition means the *standard* plan (20-week post-birth
    # leave) no longer applies - the art. 30 alternative has no plan of its own yet,
    # so possible_solutions is the only place it is described.
    assert result.plan is None


def test_confirmed_no_basis_with_unrelated_missing_data_has_no_plan() -> None:
    """unmet_conditions is non-empty (confirmed: no basis for the standard benefit),
    but an unrelated missing field (debt info) still bumps status to
    requires_verification. The plan must stay None - we must not show the standard
    plan once the standard condition has failed."""
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.unmet_conditions
    assert result.plan is None


def test_unknown_insurance_status_requires_verification_with_missing_data() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=None)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.missing_data
    # Nothing has been confirmed as failed yet (unmet_conditions is empty) - the
    # standard path is still fully open, so the plan should still be shown.
    assert result.plan is not None


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


def test_plan_documents_use_z3_for_umowa_o_prace() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        insurance_title=InsuranceTitle.umowa_o_prace,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    codes = {doc.code for doc in result.plan.required_documents}
    assert "z3" in codes
    assert "z3a" not in codes


def test_plan_documents_use_z3_for_unknown_insurance_title() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=True)

    result = evaluate_maternity_leave_eligibility(request, rule)

    codes = {doc.code for doc in result.plan.required_documents}
    assert "z3" in codes
    assert "z3a" not in codes


def test_plan_documents_omit_z3_for_self_employed() -> None:
    """Self-employed-like titles get no zaświadczenie płatnika document at all: Z-3
    doesn't apply (no employer), and Z-3b (what they used to file) was abolished
    2026-10-24 with no documented replacement - we must not invent one."""
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        debt_amount_zl=Decimal("10.00"),
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    codes = {doc.code for doc in result.plan.required_documents}
    assert "z3" not in codes
    assert codes == {"x"}


def test_self_employed_gets_z3b_replacement_warning() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        debt_amount_zl=Decimal("10.00"),
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert any("Z-3b" in w for w in result.warnings)


def test_non_self_employed_has_no_z3b_warning() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=True)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.warnings == []


def test_plan_institution_and_deadlines_come_from_the_rule_not_a_literal() -> None:
    rule = _make_rule()
    rule.institution = "Testowa instytucja"
    rule.deadlines = ["Testowy termin"]
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=True)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.plan.institution == "Testowa instytucja"
    assert result.plan.deadlines == ["Testowy termin"]


def test_alternative_benefit_eligible_when_no_other_employment_secured() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.upadlosc_likwidacja_smierc_pracodawcy,
        other_employment_secured=False,
    )

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks is None
    assert result.plan.duration_description == "do dnia porodu"
    assert result.warnings == []


def test_alternative_benefit_requires_verification_when_other_employment_unknown() -> None:
    """Without other_employment_secured, the engine must not guess - this used to
    silently return likely_eligible with a disclaimer warning; it must now hold off
    with requires_verification and an explicit missing_data entry instead."""
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.upadlosc_likwidacja_smierc_pracodawcy,
    )

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert any("inne zatrudnienie" in m for m in result.missing_data)
    assert result.plan is None


def test_alternative_benefit_not_eligible_when_other_employment_secured() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.upadlosc_likwidacja_smierc_pracodawcy,
        other_employment_secured=True,
    )

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert any("zapewniono inne zatrudnienie" in m for m in result.unmet_conditions)
    assert result.plan is None


def test_alternative_benefit_not_applicable_for_unlawful_dismissal() -> None:
    """art. 30 ust. 3 (this benefit) does not list unlawful-termination-by-court-ruling as a
    trigger - only art. 30 ust. 1 pkt 2 does, which grants the *standard* benefit instead."""
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.naruszenie_prawa_wyrokiem_sadu,
    )

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.plan is None
    assert any(
        s.related_benefit_code == BENEFIT_CODE and s.type == SolutionType.alternative_benefit
        for s in result.possible_solutions
    )


def test_alternative_benefit_requires_verification_when_insured_status_unknown() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=None)

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.missing_data
    assert result.plan is None


def test_alternative_benefit_requires_verification_when_reason_unknown() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1, insured_at_birth=False, employment_ended_reason=None
    )

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.missing_data
    assert result.plan is None


def test_alternative_benefit_points_back_to_standard_benefit_when_still_insured() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=True)

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.plan is None
    assert any(
        s.related_benefit_code == BENEFIT_CODE and s.type == SolutionType.alternative_benefit
        for s in result.possible_solutions
    )


def test_employer_liquidation_solution_points_at_alternative_benefit_code() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.upadlosc_likwidacja_smierc_pracodawcy,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    solution = next(
        s for s in result.possible_solutions if s.type == SolutionType.alternative_benefit
    )
    assert solution.related_benefit_code == ALTERNATIVE_BENEFIT_CODE


def test_unlawful_dismissal_solution_does_not_point_at_alternative_benefit_code() -> None:
    """art. 30 ust. 1 pkt 2 (unlawful dismissal) grants the standard benefit itself, not the
    separate "do dnia porodu" benefit - its solution must not link to that other benefit's
    code, and must no longer claim that other benefit is what applies."""
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.naruszenie_prawa_wyrokiem_sadu,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    solution = next(
        s for s in result.possible_solutions if s.type == SolutionType.alternative_benefit
    )
    assert solution.related_benefit_code is None
    assert "zasiłku macierzyńskiego za okres urlopu macierzyńskiego" in solution.description
    assert ALTERNATIVE_BENEFIT_CODE not in solution.description


def _make_paternity_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count={"1": 2, "2": 2, "3": 2, "4": 2, "5+": 2},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="Pracodawca albo ZUS",
        legal_basis=["Kodeks pracy (urlop ojcowski)"],
        deadlines=["Do ukończenia przez dziecko 12. miesiąca życia"],
        required_documents=[
            {
                "code": "wniosek_urlop_ojcowski",
                "name": "Wniosek",
                "when": "...",
                "applies_to": None,
            },
        ],
    )


def test_paternity_leave_eligible_when_insured_and_within_deadline() -> None:
    rule = _make_paternity_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1, father_insured=True, child_age_months=3
    )

    result = evaluate_paternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks == 2


def test_paternity_leave_requires_verification_when_insurance_status_missing() -> None:
    rule = _make_paternity_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, child_age_months=3)

    result = evaluate_paternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert any("ubezpieczenia chorobowego ojca" in m for m in result.missing_data)
    assert result.plan is None


def test_paternity_leave_requires_verification_when_child_age_missing() -> None:
    rule = _make_paternity_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, father_insured=True)

    result = evaluate_paternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert any("wiek dziecka" in m for m in result.missing_data)
    assert result.plan is None


def test_paternity_leave_not_eligible_when_father_not_insured() -> None:
    rule = _make_paternity_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1, father_insured=False, child_age_months=3
    )

    result = evaluate_paternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_paternity_leave_not_eligible_when_deadline_passed() -> None:
    rule = _make_paternity_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1, father_insured=True, child_age_months=12
    )

    result = evaluate_paternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None
