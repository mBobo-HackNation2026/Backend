from datetime import date
from decimal import Decimal

from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.engine import (
    ALTERNATIVE_BENEFIT_CODE,
    BENEFIT_CODE,
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
from app.eligibility.schemas import (
    EligibilityStatus,
    EmploymentEndedReason,
    FosterCareType,
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


def _make_parental_leave_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("70.00"),
        weeks_by_child_count={"1": 41, "2": 43, "3": 43, "4": 43, "5+": 43},
        weeks_by_child_count_za_zyciem={"1": 65, "2": 67, "3": 67, "4": 67, "5+": 67},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="Pracodawca albo ZUS",
        legal_basis=["Kodeks pracy art. 1821 i nast."],
        deadlines=["W ciągu 21 dni po porodzie dla stawki 81,5%"],
        required_documents=[
            {
                "code": "wniosek_urlop_rodzicielski",
                "name": "Wniosek",
                "when": "...",
                "applies_to": None,
            },
            {
                "code": "zaswiadczenie_za_zyciem",
                "name": "Zaświadczenie Za życiem",
                "when": "...",
                "applies_to": "za_zyciem",
            },
        ],
    )


def test_parental_leave_likely_eligible_standard_rate() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        za_zyciem_certificate=False,
        other_parent_used_parental_leave_weeks=0,
        full_dose_claimed_within_21_days=False,
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks == 41 - 9
    assert result.plan.rate_percentage == Decimal("70.00")


def test_parental_leave_full_dose_within_21_days_gets_81_5_percent() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        za_zyciem_certificate=False,
        other_parent_used_parental_leave_weeks=0,
        full_dose_claimed_within_21_days=True,
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    assert result.plan.rate_percentage == Decimal("81.50")


def test_parental_leave_za_zyciem_extends_pool_to_65_weeks() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        za_zyciem_certificate=True,
        other_parent_used_parental_leave_weeks=0,
        full_dose_claimed_within_21_days=False,
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    assert result.plan.weeks == 65 - 9


def test_parental_leave_twins_uses_43_week_pool() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=2,
        insured_at_birth=True,
        za_zyciem_certificate=False,
        other_parent_used_parental_leave_weeks=0,
        full_dose_claimed_within_21_days=False,
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    assert result.plan.weeks == 43 - 9


def test_parental_leave_other_parent_using_more_than_9_weeks_reduces_applicant_share() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        za_zyciem_certificate=False,
        other_parent_used_parental_leave_weeks=20,
        full_dose_claimed_within_21_days=False,
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    assert result.plan.weeks == 41 - 20


def test_parental_leave_pool_exhausted_by_other_parent_is_not_eligible() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        za_zyciem_certificate=False,
        other_parent_used_parental_leave_weeks=41,
        full_dose_claimed_within_21_days=False,
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_parental_leave_part_time_combination_extends_weeks_proportionally() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        za_zyciem_certificate=False,
        other_parent_used_parental_leave_weeks=0,
        full_dose_claimed_within_21_days=False,
        part_time_fraction_during_parental_leave=Decimal("0.5"),
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    # 32 weeks at half-time stretches to double the calendar duration.
    assert result.plan.weeks == 64
    assert any("wydłużenie kalendarzowe" in w for w in result.warnings)


def test_parental_leave_part_time_fraction_above_half_is_clamped() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        za_zyciem_certificate=False,
        other_parent_used_parental_leave_weeks=0,
        full_dose_claimed_within_21_days=False,
        part_time_fraction_during_parental_leave=Decimal("0.8"),
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    assert result.plan.weeks == 64
    assert any("ograniczona do tego limitu" in w for w in result.warnings)


def test_parental_leave_not_eligible_when_not_insured() -> None:
    """Confirmed unmet (not insured) with no other missing data lands on
    not_eligible - same convention as the other real evaluators."""
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        za_zyciem_certificate=False,
        other_parent_used_parental_leave_weeks=0,
        full_dose_claimed_within_21_days=False,
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_parental_leave_requires_verification_when_za_zyciem_unknown() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=True)

    result = evaluate_parental_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert any("Za życiem" in m for m in result.missing_data)
    assert result.plan is None


def test_parental_leave_documents_include_za_zyciem_certificate_only_when_applicable() -> None:
    rule = _make_parental_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        za_zyciem_certificate=True,
        other_parent_used_parental_leave_weeks=0,
        full_dose_claimed_within_21_days=False,
    )

    result = evaluate_parental_leave_eligibility(request, rule)

    codes = {doc.code for doc in result.plan.required_documents}
    assert "zaswiadczenie_za_zyciem" in codes

    request_without = request.model_copy(update={"za_zyciem_certificate": False})
    result_without = evaluate_parental_leave_eligibility(request_without, rule)
    codes_without = {doc.code for doc in result_without.plan.required_documents}
    assert "zaswiadczenie_za_zyciem" not in codes_without


def _make_sickness_during_pregnancy_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count=None,
        duration_until_birth=False,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        legal_basis=["ustawa zasiłkowa art. 8 ust. 1"],
        deadlines=["Niezwłocznie po e-ZLA"],
        required_documents=[
            {"code": "ezla", "name": "e-ZLA", "when": "...", "applies_to": None},
            {"code": "z3", "name": "Z-3", "when": "...", "applies_to": "standard"},
        ],
    )


def test_sickness_during_pregnancy_likely_eligible_with_enough_waiting_days() -> None:
    rule = _make_sickness_during_pregnancy_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_pregnant=True,
        insurance_title=InsuranceTitle.umowa_o_prace,
        insured_days_continuous=30,
    )

    result = evaluate_sickness_benefit_during_pregnancy_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks is None
    assert result.plan.duration_description == "do 270 dni niezdolności do pracy w okresie ciąży"
    assert result.plan.rate_percentage == Decimal("100.00")


def test_sickness_during_pregnancy_not_eligible_when_not_pregnant() -> None:
    rule = _make_sickness_during_pregnancy_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_pregnant=False,
        insurance_title=InsuranceTitle.umowa_o_prace,
        insured_days_continuous=30,
    )

    result = evaluate_sickness_benefit_during_pregnancy_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_sickness_during_pregnancy_requires_90_days_for_zlecenie() -> None:
    rule = _make_sickness_during_pregnancy_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_pregnant=True,
        insurance_title=InsuranceTitle.zlecenie,
        insured_days_continuous=45,
    )

    result = evaluate_sickness_benefit_during_pregnancy_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert any("90 dni" in c for c in result.unmet_conditions)


def test_sickness_during_pregnancy_30_days_is_enough_for_umowa_o_prace() -> None:
    rule = _make_sickness_during_pregnancy_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_pregnant=True,
        insurance_title=InsuranceTitle.umowa_o_prace,
        insured_days_continuous=30,
    )

    result = evaluate_sickness_benefit_during_pregnancy_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible


def test_sickness_during_pregnancy_requires_verification_when_pregnancy_status_unknown() -> None:
    rule = _make_sickness_during_pregnancy_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insurance_title=InsuranceTitle.umowa_o_prace,
        insured_days_continuous=30,
    )

    result = evaluate_sickness_benefit_during_pregnancy_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert any("ciąży" in m for m in result.missing_data)
    assert result.plan is not None


def test_sickness_during_pregnancy_self_employed_debt_over_threshold_is_not_eligible() -> None:
    rule = _make_sickness_during_pregnancy_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_pregnant=True,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        insured_days_continuous=90,
        debt_amount_zl=Decimal("100.00"),
    )

    result = evaluate_sickness_benefit_during_pregnancy_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert any(s.type == SolutionType.corrective_action for s in result.possible_solutions)


def _make_rehabilitation_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("90.00"),
        weeks_by_child_count=None,
        duration_until_birth=False,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        legal_basis=["ustawa zasiłkowa art. 18"],
        deadlines=["Przed upływem okresu zasiłku chorobowego"],
        required_documents=[
            {"code": "wniosek", "name": "Wniosek", "when": "...", "applies_to": None},
            {"code": "z3", "name": "Z-3", "when": "...", "applies_to": "standard"},
        ],
    )


def test_rehabilitation_benefit_likely_eligible_not_pregnant_gets_90_percent() -> None:
    rule = _make_rehabilitation_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        sickness_benefit_period_exhausted=True,
        medical_prognosis_recovery_possible=True,
        excluded_from_rehabilitation_benefit=False,
        is_pregnant=False,
    )

    result = evaluate_rehabilitation_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks is None
    assert result.plan.duration_description == "do 12 miesięcy"
    assert result.plan.rate_percentage == Decimal("90.00")
    assert any("90%" in w for w in result.warnings)


def test_rehabilitation_benefit_pregnant_gets_100_percent() -> None:
    rule = _make_rehabilitation_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        sickness_benefit_period_exhausted=True,
        medical_prognosis_recovery_possible=True,
        excluded_from_rehabilitation_benefit=False,
        is_pregnant=True,
    )

    result = evaluate_rehabilitation_benefit_eligibility(request, rule)

    assert result.plan.rate_percentage == Decimal("100.00")


def test_rehabilitation_benefit_not_eligible_when_sickness_benefit_not_exhausted() -> None:
    rule = _make_rehabilitation_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        sickness_benefit_period_exhausted=False,
        medical_prognosis_recovery_possible=True,
        excluded_from_rehabilitation_benefit=False,
        is_pregnant=False,
    )

    result = evaluate_rehabilitation_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_rehabilitation_benefit_not_eligible_without_positive_prognosis() -> None:
    rule = _make_rehabilitation_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        sickness_benefit_period_exhausted=True,
        medical_prognosis_recovery_possible=False,
        excluded_from_rehabilitation_benefit=False,
        is_pregnant=False,
    )

    result = evaluate_rehabilitation_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_rehabilitation_benefit_not_eligible_when_excluded_by_other_benefit() -> None:
    rule = _make_rehabilitation_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        sickness_benefit_period_exhausted=True,
        medical_prognosis_recovery_possible=True,
        excluded_from_rehabilitation_benefit=True,
        is_pregnant=False,
    )

    result = evaluate_rehabilitation_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_rehabilitation_benefit_requires_verification_when_all_fields_missing() -> None:
    rule = _make_rehabilitation_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1)

    result = evaluate_rehabilitation_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert len(result.missing_data) == 4
    assert result.plan is None


def test_rehabilitation_benefit_self_employed_debt_over_threshold_is_not_eligible() -> None:
    rule = _make_rehabilitation_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        sickness_benefit_period_exhausted=True,
        medical_prognosis_recovery_possible=True,
        excluded_from_rehabilitation_benefit=False,
        is_pregnant=False,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        debt_amount_zl=Decimal("100.00"),
    )

    result = evaluate_rehabilitation_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert any(s.type == SolutionType.corrective_action for s in result.possible_solutions)


def _make_supplementary_leave_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        # Standard maternity-leave week table - used only to compute the real filing
        # deadline (Kodeks pracy art. 1802 §4: 21 days / 3 weeks before the end of the
        # base maternity leave), not the supplementary leave's own entitlement.
        weeks_by_child_count={"1": 20, "2": 31, "3": 33, "4": 35, "5+": 37},
        duration_until_birth=False,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="Pracodawca albo ZUS",
        legal_basis=["Kodeks pracy art. 1802 §1, §3 i §4"],
        deadlines=["21 dni przed zakończeniem urlopu macierzyńskiego"],
        required_documents=[
            {"code": "wniosek", "name": "Wniosek", "when": "...", "applies_to": None},
        ],
    )


def test_supplementary_leave_likely_eligible_standard_case() -> None:
    rule = _make_supplementary_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        child_hospitalization_weeks=3,
        gestational_week_at_birth=34,
        birth_weight_grams=2200,
        postpartum_weeks_elapsed=4,
    )

    result = evaluate_supplementary_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks == 3
    assert result.plan.rate_percentage == Decimal("100.00")


def test_supplementary_leave_past_hospitalization_cutoff_week_is_still_eligible() -> None:
    """The 8th/15th week post-partum only limits WHICH hospitalization weeks count
    toward the entitlement (Kodeks pracy art. 1802 §1 i §3) - it is not a filing
    deadline, so being past it must not disqualify the benefit by itself."""
    rule = _make_supplementary_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        child_hospitalization_weeks=2,
        gestational_week_at_birth=34,
        birth_weight_grams=2200,
        postpartum_weeks_elapsed=10,
    )

    result = evaluate_supplementary_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert any("8. tydzień" in w or "hospitalizacji" in w for w in result.warnings)


def test_supplementary_leave_not_eligible_when_filing_deadline_passed() -> None:
    """Real deadline: wniosek nie później niż 21 dni (3 tygodnie) przed końcem urlopu
    macierzyńskiego (Kodeks pracy art. 1802 §4). 1 child -> 20-week maternity leave;
    at 18 weeks post-partum only 2 weeks remain, which is under the 3-week minimum."""
    rule = _make_supplementary_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        child_hospitalization_weeks=2,
        gestational_week_at_birth=34,
        birth_weight_grams=2200,
        postpartum_weeks_elapsed=18,
    )

    result = evaluate_supplementary_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None
    assert any("art. 1802 §4" in c for c in result.unmet_conditions)


def test_supplementary_leave_filing_deadline_exactly_3_weeks_remaining_is_eligible() -> None:
    rule = _make_supplementary_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        child_hospitalization_weeks=2,
        gestational_week_at_birth=34,
        birth_weight_grams=2200,
        postpartum_weeks_elapsed=17,
    )

    result = evaluate_supplementary_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible


def test_supplementary_leave_not_eligible_without_hospitalization() -> None:
    rule = _make_supplementary_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        child_hospitalization_weeks=0,
        gestational_week_at_birth=38,
        birth_weight_grams=3200,
        postpartum_weeks_elapsed=1,
    )

    result = evaluate_supplementary_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_supplementary_leave_requires_verification_when_hospitalization_weeks_missing() -> None:
    rule = _make_supplementary_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        gestational_week_at_birth=34,
        birth_weight_grams=2200,
        postpartum_weeks_elapsed=4,
    )

    result = evaluate_supplementary_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert any("pobytu dziecka w szpitalu" in m for m in result.missing_data)
    assert result.plan is None


def _make_adoption_leave_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count={"1": 20, "2": 31, "3": 33, "4": 35, "5+": 37},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="Pracodawca albo ZUS",
        legal_basis=["Kodeks pracy art. 183"],
        deadlines=["Przed rozpoczęciem korzystania z urlopu"],
        required_documents=[
            {"code": "wniosek", "name": "Wniosek", "when": "...", "applies_to": None},
        ],
    )


def test_adoption_leave_likely_eligible_for_adoption_petition() -> None:
    rule = _make_adoption_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_adoption_or_foster_care=True,
        foster_care_type=FosterCareType.wniosek_o_przysposobienie,
        child_age_years=10,
    )

    result = evaluate_adoption_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks == 20


def test_adoption_leave_not_eligible_past_14_for_adoption_petition() -> None:
    rule = _make_adoption_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_adoption_or_foster_care=True,
        foster_care_type=FosterCareType.wniosek_o_przysposobienie,
        child_age_years=14,
    )

    result = evaluate_adoption_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_adoption_leave_foster_care_age_limit_is_7_without_deferral() -> None:
    rule = _make_adoption_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_adoption_or_foster_care=True,
        foster_care_type=FosterCareType.rodzina_zastepcza,
        school_obligation_deferred=False,
        child_age_years=7,
    )

    result = evaluate_adoption_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_adoption_leave_foster_care_age_limit_extends_to_10_with_deferral() -> None:
    rule = _make_adoption_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_adoption_or_foster_care=True,
        foster_care_type=FosterCareType.rodzina_zastepcza,
        school_obligation_deferred=True,
        child_age_years=9,
    )

    result = evaluate_adoption_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible


def test_adoption_leave_not_eligible_for_professional_foster_family() -> None:
    rule = _make_adoption_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_adoption_or_foster_care=True,
        foster_care_type=FosterCareType.rodzina_zastepcza_zawodowa,
        child_age_years=3,
    )

    result = evaluate_adoption_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_adoption_leave_points_to_standard_benefit_when_not_adoption_or_foster_care() -> None:
    """unmet + an alternative_benefit solution = requires_verification (same
    confirm-the-alternative-separately convention as the other evaluators), not a
    flat not_eligible."""
    rule = _make_adoption_leave_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_adoption_or_foster_care=False,
    )

    result = evaluate_adoption_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.plan is None
    assert any(
        s.type == SolutionType.alternative_benefit and s.related_benefit_code == BENEFIT_CODE
        for s in result.possible_solutions
    )


def test_adoption_leave_requires_verification_when_adoption_flag_missing() -> None:
    """Nothing confirmed as unmet yet (just missing data) - the standard path is
    still open, so a plan is still shown, same convention as the other evaluators."""
    rule = _make_adoption_leave_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1)

    result = evaluate_adoption_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.plan is not None


def _make_stillbirth_funeral_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("0.00"),
        lump_sum_amount_zl=Decimal("7000.00"),
        weeks_by_child_count=None,
        duration_until_birth=False,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        legal_basis=["Poradnik ZUS 2026"],
        deadlines=["W ciągu 12 miesięcy od pochówku"],
        required_documents=[
            {"code": "wniosek_z12", "name": "Wniosek Z-12", "when": "...", "applies_to": None},
        ],
    )


def test_stillbirth_funeral_benefit_likely_eligible_within_deadline() -> None:
    """Deadline runs from the day of BURIAL (days_since_burial), not death - the
    Poradnik ZUS 2026 wording is explicit about this for the stillbirth variant."""
    rule = _make_stillbirth_funeral_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_stillbirth_or_infant_death=True,
        days_since_burial=30,
    )

    result = evaluate_stillbirth_funeral_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks is None
    assert result.plan.rate_percentage is None
    assert result.plan.lump_sum_amount_zl == Decimal("7000.00")


def test_stillbirth_funeral_benefit_not_eligible_past_12_month_deadline() -> None:
    rule = _make_stillbirth_funeral_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_stillbirth_or_infant_death=True,
        days_since_burial=400,
    )

    result = evaluate_stillbirth_funeral_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_stillbirth_funeral_benefit_not_eligible_without_stillbirth() -> None:
    rule = _make_stillbirth_funeral_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_stillbirth_or_infant_death=False,
        days_since_burial=10,
    )

    result = evaluate_stillbirth_funeral_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None


def test_stillbirth_funeral_benefit_days_since_death_alone_is_not_enough() -> None:
    """days_since_death (art. 1801 leave-after-death purpose) must NOT be mistaken for
    days_since_burial (the Z-12 filing deadline) - providing only the former still
    leaves the deadline unconfirmed."""
    rule = _make_stillbirth_funeral_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        is_stillbirth_or_infant_death=True,
        days_since_death=30,
    )

    result = evaluate_stillbirth_funeral_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert any("pochówku" in m for m in result.missing_data)


def test_stillbirth_funeral_benefit_requires_verification_when_fields_missing() -> None:
    rule = _make_stillbirth_funeral_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1)

    result = evaluate_stillbirth_funeral_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert len(result.missing_data) == 2
