"""Czysta logika kalkulatora świadczeń - niezależna od silnika uprawnień
(``app/eligibility``). Liczy hipotetyczną kwotę/okres na podstawie podanych danych, bez
sprawdzania czy świadczenie faktycznie przysługuje - to celowe rozdzielenie funkcji (zob.
pamięć projektu `project-ebobo-priority-reset-2026-11-21`).
"""

from decimal import ROUND_HALF_UP, Decimal

from app.calculator.schemas import (
    BasisOfCalculation,
    CalculatedAmount,
    ParentalLeaveCompareRequest,
    ParentalLeaveCompareResponse,
    ParentalLeaveVariant,
    RatePeriod,
)
from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.engine import _weeks_for_children_count
from app.eligibility.schemas import InsuranceTitle, MaternityLeaveEligibilityRequest
from app.rules.seed import (
    ADOPTION_LEAVE_BENEFIT_CODE,
    ADOPTION_LEAVE_BENEFIT_NAME,
    ALTERNATIVE_BENEFIT_CODE,
    ALTERNATIVE_BENEFIT_NAME,
    MATERNITY_LEAVE_BENEFIT_CODE,
    MATERNITY_LEAVE_BENEFIT_NAME,
    PARENTAL_LEAVE_BENEFIT_CODE,
    PARENTAL_LEAVE_BENEFIT_NAME,
    PATERNITY_LEAVE_BENEFIT_CODE,
    PATERNITY_LEAVE_BENEFIT_NAME,
    REHABILITATION_BENEFIT_CODE,
    REHABILITATION_BENEFIT_NAME,
    SICKNESS_DURING_PREGNANCY_BENEFIT_CODE,
    SICKNESS_DURING_PREGNANCY_BENEFIT_NAME,
    STILLBIRTH_FUNERAL_BENEFIT_CODE,
    STILLBIRTH_FUNERAL_BENEFIT_NAME,
    SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
    SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_NAME,
)

# Nazwy świadczeń podane jawnie (nie przez rule.benefit_type.name), żeby silnik kalkulatora
# dało się testować na BenefitRuleVersion skonstruowanym w pamięci, bez zapisanej relacji
# do BenefitType - ta sama konwencja co w app/eligibility/engine.py.
_BENEFIT_NAMES: dict[str, str] = {
    MATERNITY_LEAVE_BENEFIT_CODE: MATERNITY_LEAVE_BENEFIT_NAME,
    ALTERNATIVE_BENEFIT_CODE: ALTERNATIVE_BENEFIT_NAME,
    PATERNITY_LEAVE_BENEFIT_CODE: PATERNITY_LEAVE_BENEFIT_NAME,
    PARENTAL_LEAVE_BENEFIT_CODE: PARENTAL_LEAVE_BENEFIT_NAME,
    SICKNESS_DURING_PREGNANCY_BENEFIT_CODE: SICKNESS_DURING_PREGNANCY_BENEFIT_NAME,
    REHABILITATION_BENEFIT_CODE: REHABILITATION_BENEFIT_NAME,
    SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE: SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_NAME,
    ADOPTION_LEAVE_BENEFIT_CODE: ADOPTION_LEAVE_BENEFIT_NAME,
    STILLBIRTH_FUNERAL_BENEFIT_CODE: STILLBIRTH_FUNERAL_BENEFIT_NAME,
}

_CENTS = Decimal("0.01")

# ustawa zasiłkowa: składki finansowane przez ubezpieczonego potrącane z podstawy wymiaru
# (emerytalna 9,76% + rentowa 1,5% + chorobowa 2,45% = 13,71%) - zob. Załącznik (pamięć
# projektu `project-ebobo-legal-rules`).
_EMPLOYEE_CONTRIBUTION_DEDUCTION_PERCENT = Decimal("13.71")
# Art. 11 ust. 5 i art. 36 ust. 3 ustawy zasiłkowej: miesiąc = 30 dni, podstawa dzienna =
# 1/30 podstawy miesięcznej.
_DAYS_PER_MONTH = 30
_MINIMUM_WAGE_2026_ZL = Decimal("4806.00")
# ustawa zasiłkowa art. 48: limit miesięcznej podstawy dobrowolnej składki chorobowej w 2026 r.
_VOLUNTARY_CONTRIBUTION_BASE_CAP_ZL = Decimal("23550.00")
_VOLUNTARY_INSURANCE_TITLES = {InsuranceTitle.zlecenie, InsuranceTitle.dzialalnosc_gospodarcza}
_PARENTAL_LEAVE_NON_TRANSFERABLE_WEEKS = 9
_PARENTAL_LEAVE_FULL_DOSE_RATE_PERCENT = Decimal("81.50")
_REHABILITATION_TOTAL_DAYS = 12 * _DAYS_PER_MONTH
_REHABILITATION_FIRST_PERIOD_DAYS = 3 * _DAYS_PER_MONTH
_REHABILITATION_FIRST_PERIOD_RATE = Decimal("90.00")
_REHABILITATION_LATER_PERIOD_RATE = Decimal("75.00")
_REHABILITATION_PREGNANT_RATE = Decimal("100.00")
_SICKNESS_DURING_PREGNANCY_MAX_DAYS = 270


def _round(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def calculate_basis_of_calculation(
    *,
    average_monthly_income_zl: Decimal | None,
    insurance_title: InsuranceTitle | None,
    voluntary_contribution_base_zl: Decimal | None,
) -> BasisOfCalculation | None:
    """Ustawa zasiłkowa art. 36-38 (pracownik) / art. 48 (niebędący pracownikiem).

    Zwraca ``None``, gdy brakuje danych potrzebnych do obliczenia (nigdy nie zgaduje).
    """
    warnings: list[str] = []
    is_voluntary = insurance_title in _VOLUNTARY_INSURANCE_TITLES

    if is_voluntary:
        source = voluntary_contribution_base_zl
        if source is None:
            return None
        if source > _VOLUNTARY_CONTRIBUTION_BASE_CAP_ZL:
            warnings.append(
                "Zadeklarowana podstawa składki dobrowolnej przekracza limit "
                f"{_VOLUNTARY_CONTRIBUTION_BASE_CAP_ZL} zł obowiązujący w 2026 r. - "
                "ograniczono do limitu (ustawa zasiłkowa art. 48)."
            )
            source = _VOLUNTARY_CONTRIBUTION_BASE_CAP_ZL
    else:
        source = average_monthly_income_zl
        if source is None:
            return None

    monthly_basis = _round(
        source * (Decimal(100) - _EMPLOYEE_CONTRIBUTION_DEDUCTION_PERCENT) / Decimal(100)
    )

    minimum_basis_applied = False
    if not is_voluntary:
        minimum_floor = _round(
            _MINIMUM_WAGE_2026_ZL
            * (Decimal(100) - _EMPLOYEE_CONTRIBUTION_DEDUCTION_PERCENT)
            / Decimal(100)
        )
        if monthly_basis < minimum_floor:
            monthly_basis = minimum_floor
            minimum_basis_applied = True
            warnings.append(
                "Zastosowano podstawę minimalną wyliczoną ze wzoru (płaca minimalna "
                f"{_MINIMUM_WAGE_2026_ZL} zł pomniejszona o 13,71%) - oficjalna, gotowa "
                "tabela minimalnych podstaw nie jest publikowana w dostępnych materiałach "
                "źródłowych (ustawa zasiłkowa art. 45); dotyczy wyłącznie pracowników "
                "pełnoetatowych, nie dobrowolnie ubezpieczonych."
            )

    daily_basis = _round(monthly_basis / Decimal(_DAYS_PER_MONTH))

    return BasisOfCalculation(
        monthly_basis_zl=monthly_basis,
        daily_basis_zl=daily_basis,
        deduction_rate_percent=_EMPLOYEE_CONTRIBUTION_DEDUCTION_PERCENT,
        minimum_basis_applied=minimum_basis_applied,
        warnings=warnings,
    )


def _resolve_segments(
    benefit_code: str, rule: BenefitRuleVersion, request: MaternityLeaveEligibilityRequest
) -> tuple[int | None, list[tuple[int, Decimal]], list[str]]:
    """Ustala (łączną liczbę dni, [(dni, stawka%), ...], ostrzeżenia) dla danego
    świadczenia - wyłącznie do celów wyliczenia kwoty, niezależnie od potwierdzonych
    uprawnień. Zwraca ``(None, [], [...])`` gdy okresu nie da się wyliczyć z góry.
    """
    if benefit_code == STILLBIRTH_FUNERAL_BENEFIT_CODE:
        return None, [], []

    if benefit_code == ALTERNATIVE_BENEFIT_CODE:
        return (
            None,
            [],
            [
                "Czas trwania to 'do dnia porodu' - łączna kwota zależy od rzeczywistej "
                "daty porodu i nie może być wyliczona z góry; poniżej tylko stawka "
                "dzienna/podstawa."
            ],
        )

    if benefit_code == SICKNESS_DURING_PREGNANCY_BENEFIT_CODE:
        days = _SICKNESS_DURING_PREGNANCY_MAX_DAYS
        return (
            days,
            [(days, rule.rate_percentage)],
            [
                "270 dni to maksymalny okres - rzeczywista wypłacona kwota zależy od "
                "faktycznej długości niezdolności do pracy."
            ],
        )

    if benefit_code == REHABILITATION_BENEFIT_CODE:
        days = _REHABILITATION_TOTAL_DAYS
        warnings = [
            "12 miesięcy (360 dni) to maksymalny okres - rzeczywista wypłacona kwota "
            "zależy od faktycznego czasu pobierania świadczenia. Podstawa wymiaru "
            "podlega też kwartalnej waloryzacji (ustawa zasiłkowa art. 19 ust. 2), która "
            "nie jest tu uwzględniana."
        ]
        if request.is_pregnant:
            return days, [(days, _REHABILITATION_PREGNANT_RATE)], warnings
        return (
            days,
            [
                (_REHABILITATION_FIRST_PERIOD_DAYS, _REHABILITATION_FIRST_PERIOD_RATE),
                (
                    days - _REHABILITATION_FIRST_PERIOD_DAYS,
                    _REHABILITATION_LATER_PERIOD_RATE,
                ),
            ],
            warnings,
        )

    if benefit_code == PARENTAL_LEAVE_BENEFIT_CODE:
        table = (
            rule.weeks_by_child_count_za_zyciem
            if request.za_zyciem_certificate
            else rule.weeks_by_child_count
        )
        total_pool = _weeks_for_children_count(table, request.children_count)
        other_parent_used = request.other_parent_used_parental_leave_weeks or 0
        reserved_for_other_parent = max(other_parent_used, _PARENTAL_LEAVE_NON_TRANSFERABLE_WEEKS)
        weeks = max(total_pool - reserved_for_other_parent, 0)
        rate = (
            _PARENTAL_LEAVE_FULL_DOSE_RATE_PERCENT
            if request.full_dose_claimed_within_21_days
            else rule.rate_percentage
        )
        days = weeks * 7
        return days, [(days, rate)], []

    if benefit_code == SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE:
        weeks = request.child_hospitalization_weeks or 0
        days = weeks * 7
        return days, [(days, rule.rate_percentage)], []

    # zasilek_macierzynski_urlop_macierzynski, urlop_ojcowski,
    # urlop_na_warunkach_urlopu_macierzynskiego: płaska tabela tygodni wg liczby dzieci.
    weeks = _weeks_for_children_count(rule.weeks_by_child_count, request.children_count)
    days = weeks * 7
    return days, [(days, rule.rate_percentage)], []


def calculate_benefit(
    benefit_code: str, rule: BenefitRuleVersion, request: MaternityLeaveEligibilityRequest
) -> CalculatedAmount:
    benefit_name = _BENEFIT_NAMES[benefit_code]
    warnings: list[str] = []

    if rule.lump_sum_amount_zl is not None:
        return CalculatedAmount(
            benefit_code=benefit_code,
            benefit_name=benefit_name,
            basis=None,
            total_days=None,
            total_amount_zl=rule.lump_sum_amount_zl,
            lump_sum_amount_zl=rule.lump_sum_amount_zl,
            rate_breakdown=[],
            rules_version=rule.version,
            warnings=[],
        )

    total_days, segments, segment_warnings = _resolve_segments(benefit_code, rule, request)
    warnings.extend(segment_warnings)

    basis = calculate_basis_of_calculation(
        average_monthly_income_zl=request.average_monthly_income_zl,
        insurance_title=request.insurance_title,
        voluntary_contribution_base_zl=request.voluntary_contribution_base_zl,
    )
    if basis is None:
        warnings.append(
            "Brak danych o dochodzie - podaj average_monthly_income_zl (albo "
            "voluntary_contribution_base_zl dla zlecenia/działalności gospodarczej), "
            "aby wyliczyć kwotę."
        )
        return CalculatedAmount(
            benefit_code=benefit_code,
            benefit_name=benefit_name,
            basis=None,
            total_days=total_days,
            total_amount_zl=None,
            lump_sum_amount_zl=None,
            rate_breakdown=[],
            rules_version=rule.version,
            warnings=warnings,
        )
    warnings.extend(basis.warnings)

    rate_breakdown: list[RatePeriod] = []
    total_amount: Decimal | None = Decimal("0.00") if segments else None
    for days, rate in segments:
        amount = _round(basis.daily_basis_zl * rate / Decimal(100) * days)
        rate_breakdown.append(RatePeriod(days=days, rate_percentage=rate, amount_zl=amount))
        total_amount += amount  # type: ignore[operator]

    return CalculatedAmount(
        benefit_code=benefit_code,
        benefit_name=benefit_name,
        basis=basis,
        total_days=total_days,
        total_amount_zl=total_amount,
        lump_sum_amount_zl=None,
        rate_breakdown=rate_breakdown,
        rules_version=rule.version,
        warnings=warnings,
    )


def compare_parental_leave_variants(
    rule: BenefitRuleVersion, request: ParentalLeaveCompareRequest
) -> ParentalLeaveCompareResponse:
    table = (
        rule.weeks_by_child_count_za_zyciem
        if request.za_zyciem_certificate
        else rule.weeks_by_child_count
    )
    total_pool = _weeks_for_children_count(table, request.children_count)
    rate = (
        _PARENTAL_LEAVE_FULL_DOSE_RATE_PERCENT
        if request.full_dose_claimed_within_21_days
        else rule.rate_percentage
    )

    def amount_for(weeks: int, parent) -> Decimal | None:  # noqa: ANN001
        basis = calculate_basis_of_calculation(
            average_monthly_income_zl=parent.average_monthly_income_zl,
            insurance_title=parent.insurance_title,
            voluntary_contribution_base_zl=parent.voluntary_contribution_base_zl,
        )
        if basis is None:
            return None
        return _round(basis.daily_basis_zl * rate / Decimal(100) * weeks * 7)

    max_for_a = max(total_pool - _PARENTAL_LEAVE_NON_TRANSFERABLE_WEEKS, 0)
    max_for_b = max(total_pool - _PARENTAL_LEAVE_NON_TRANSFERABLE_WEEKS, 0)
    equal_a = total_pool // 2
    equal_b = total_pool - equal_a

    variant_specs = [
        (
            f"{request.parent_a.label} wykorzystuje maksymalny możliwy wymiar",
            max_for_a,
            total_pool - max_for_a,
        ),
        (
            f"{request.parent_b.label} wykorzystuje maksymalny możliwy wymiar",
            total_pool - max_for_b,
            max_for_b,
        ),
        ("Podział po równo między rodzicami", equal_a, equal_b),
    ]

    variants: list[ParentalLeaveVariant] = []
    for label, weeks_a, weeks_b in variant_specs:
        amount_a = amount_for(weeks_a, request.parent_a)
        amount_b = amount_for(weeks_b, request.parent_b)
        total = amount_a + amount_b if amount_a is not None and amount_b is not None else None
        variants.append(
            ParentalLeaveVariant(
                label=label,
                weeks_parent_a=weeks_a,
                weeks_parent_b=weeks_b,
                amount_parent_a_zl=amount_a,
                amount_parent_b_zl=amount_b,
                total_household_amount_zl=total,
            )
        )

    warnings: list[str] = []
    if (
        request.parent_a.average_monthly_income_zl is None
        and request.parent_a.voluntary_contribution_base_zl is None
    ):
        warnings.append(
            f"Brak danych o dochodzie {request.parent_a.label} - kwoty dla tego rodzica "
            "nie zostały wyliczone."
        )
    if (
        request.parent_b.average_monthly_income_zl is None
        and request.parent_b.voluntary_contribution_base_zl is None
    ):
        warnings.append(
            f"Brak danych o dochodzie {request.parent_b.label} - kwoty dla tego rodzica "
            "nie zostały wyliczone."
        )
    if request.full_dose_claimed_within_21_days:
        warnings.append(
            "Stawka 81,5% nie obejmuje nieprzenoszalnych 9 tygodni drugiego rodzica, "
            "które są zawsze płatne 70% (ustawa zasiłkowa art. 31 ust. 3f) - ten "
            "uproszczony model stosuje jedną stawkę do całego wymiaru każdego wariantu, "
            "zweryfikuj dokładne rozliczenie z ZUS/pracodawcą."
        )

    return ParentalLeaveCompareResponse(
        total_pool_weeks=total_pool,
        non_transferable_weeks_per_parent=_PARENTAL_LEAVE_NON_TRANSFERABLE_WEEKS,
        rate_percentage=rate,
        variants=variants,
        warnings=warnings,
    )
