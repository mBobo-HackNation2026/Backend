from datetime import date
from decimal import Decimal

from app.calculator.engine import calculate_basis_of_calculation, calculate_benefit
from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.schemas import InsuranceTitle, MaternityLeaveEligibilityRequest


def _make_maternity_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count={"1": 20, "2": 31, "3": 33, "4": 35, "5+": 37},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        legal_basis=["ustawa zasiłkowa art. 29"],
        deadlines=[],
        required_documents=[],
    )


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
        legal_basis=["ustawa zasiłkowa art. 19"],
        deadlines=[],
        required_documents=[],
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
        deadlines=[],
        required_documents=[],
    )


def _make_stillbirth_rule() -> BenefitRuleVersion:
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
        deadlines=[],
        required_documents=[],
    )


def test_basis_of_calculation_applies_13_71_percent_deduction() -> None:
    basis = calculate_basis_of_calculation(
        average_monthly_income_zl=Decimal("6000.00"),
        insurance_title=InsuranceTitle.umowa_o_prace,
        voluntary_contribution_base_zl=None,
    )

    assert basis is not None
    assert basis.monthly_basis_zl == Decimal("5177.40")
    assert basis.daily_basis_zl == Decimal("172.58")
    assert basis.minimum_basis_applied is False


def test_basis_of_calculation_applies_minimum_floor_for_full_time_employee() -> None:
    basis = calculate_basis_of_calculation(
        average_monthly_income_zl=Decimal("1000.00"),
        insurance_title=InsuranceTitle.umowa_o_prace,
        voluntary_contribution_base_zl=None,
        is_full_time_employment=True,
    )

    assert basis is not None
    assert basis.minimum_basis_applied is True
    assert basis.monthly_basis_zl == Decimal("4147.10")


def test_basis_of_calculation_does_not_apply_floor_without_full_time_status() -> None:
    """Art. 45 ust. 1 ustawy zasiłkowej restricts the floor to full-time employment -
    when that status is unknown, the calculator must not guess it applies."""
    basis = calculate_basis_of_calculation(
        average_monthly_income_zl=Decimal("1000.00"),
        insurance_title=InsuranceTitle.umowa_o_prace,
        voluntary_contribution_base_zl=None,
        is_full_time_employment=None,
    )

    assert basis is not None
    assert basis.minimum_basis_applied is False
    assert basis.monthly_basis_zl == Decimal("862.90")
    assert any("pełnym wymiarze" in w for w in basis.warnings)


def test_basis_of_calculation_does_not_apply_floor_for_part_time_employee() -> None:
    basis = calculate_basis_of_calculation(
        average_monthly_income_zl=Decimal("1000.00"),
        insurance_title=InsuranceTitle.umowa_o_prace,
        voluntary_contribution_base_zl=None,
        is_full_time_employment=False,
    )

    assert basis is not None
    assert basis.minimum_basis_applied is False
    assert basis.monthly_basis_zl == Decimal("862.90")


def test_basis_of_calculation_uses_voluntary_contribution_base_for_zlecenie() -> None:
    basis = calculate_basis_of_calculation(
        average_monthly_income_zl=Decimal("10000.00"),
        insurance_title=InsuranceTitle.zlecenie,
        voluntary_contribution_base_zl=Decimal("3000.00"),
    )

    assert basis is not None
    assert basis.monthly_basis_zl == Decimal("2588.70")
    assert basis.minimum_basis_applied is False


def test_basis_of_calculation_caps_voluntary_contribution_base_at_limit() -> None:
    basis = calculate_basis_of_calculation(
        average_monthly_income_zl=None,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        voluntary_contribution_base_zl=Decimal("50000.00"),
    )

    assert basis is not None
    assert any("limit" in w for w in basis.warnings)


def test_basis_of_calculation_returns_none_without_income_data() -> None:
    basis = calculate_basis_of_calculation(
        average_monthly_income_zl=None,
        insurance_title=InsuranceTitle.umowa_o_prace,
        voluntary_contribution_base_zl=None,
    )

    assert basis is None


def test_calculate_maternity_leave_total_amount() -> None:
    rule = _make_maternity_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        average_monthly_income_zl=Decimal("6000.00"),
        insurance_title=InsuranceTitle.umowa_o_prace,
    )

    result = calculate_benefit("zasilek_macierzynski_urlop_macierzynski", rule, request)

    assert result.total_days == 140
    assert result.total_amount_zl == Decimal("24161.20")
    assert len(result.rate_breakdown) == 1
    assert result.rate_breakdown[0].rate_percentage == Decimal("100.00")


def test_calculate_maternity_leave_without_income_returns_no_amount() -> None:
    rule = _make_maternity_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1)

    result = calculate_benefit("zasilek_macierzynski_urlop_macierzynski", rule, request)

    assert result.total_amount_zl is None
    assert result.total_days == 140
    assert any("Brak danych o dochodzie" in w for w in result.warnings)


def test_calculate_rehabilitation_benefit_splits_rate_by_period_when_not_pregnant() -> None:
    rule = _make_rehabilitation_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        average_monthly_income_zl=Decimal("6000.00"),
        is_pregnant=False,
    )

    result = calculate_benefit("swiadczenie_rehabilitacyjne", rule, request)

    assert result.total_days == 360
    assert len(result.rate_breakdown) == 2
    assert result.rate_breakdown[0].days == 90
    assert result.rate_breakdown[0].rate_percentage == Decimal("90.00")
    assert result.rate_breakdown[1].days == 270
    assert result.rate_breakdown[1].rate_percentage == Decimal("75.00")


def test_calculate_rehabilitation_benefit_flat_rate_when_pregnant() -> None:
    rule = _make_rehabilitation_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        average_monthly_income_zl=Decimal("6000.00"),
        is_pregnant=True,
    )

    result = calculate_benefit("swiadczenie_rehabilitacyjne", rule, request)

    assert len(result.rate_breakdown) == 1
    assert result.rate_breakdown[0].rate_percentage == Decimal("100.00")


def test_calculate_alternative_benefit_has_no_total_amount() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        average_monthly_income_zl=Decimal("6000.00"),
    )

    result = calculate_benefit("zasilek_w_wysokosci_zasilku_macierzynskiego", rule, request)

    assert result.total_days is None
    assert result.total_amount_zl is None
    assert result.basis is not None
    assert any("do dnia porodu" in w for w in result.warnings)


def test_calculate_stillbirth_funeral_benefit_returns_lump_sum() -> None:
    rule = _make_stillbirth_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1)

    result = calculate_benefit("zasilek_pogrzebowy_martwe_urodzenie", rule, request)

    assert result.basis is None
    assert result.lump_sum_amount_zl == Decimal("7000.00")
    assert result.total_amount_zl == Decimal("7000.00")
