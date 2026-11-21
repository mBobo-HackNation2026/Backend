"""Modele requestu/response dla kalkulatora świadczeń.

Kalkulator jest celowo niezależny od potwierdzonego wyniku oceny uprawnień
(``app/eligibility``): liczy hipotetyczną kwotę na podstawie podanych danych, nawet gdy
``POST /eligibility/check/{benefit_code}`` zwróciłby ``requires_verification`` albo
``not_eligible``. Te dwie funkcje - ustalenie uprawnień i wyliczenie kwoty - są z założenia
rozdzielone (zob. pamięć projektu `project-ebobo-priority-reset-2026-11-21`).
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.eligibility.schemas import InsuranceTitle


class BasisOfCalculation(BaseModel):
    """Podstawa wymiaru zasiłku - zob. ustawa zasiłkowa art. 36-38 (pracownik) / art. 48
    (niebędący pracownikiem), art. 42 (podstawa minimalna), art. 11 ust. 5 i art. 36 ust. 3
    (miesiąc = 30 dni, podstawa dzienna = 1/30 podstawy miesięcznej)."""

    monthly_basis_zl: Decimal = Field(
        description=(
            "Miesięczna podstawa wymiaru po odliczeniu 13,71% (składki finansowane przez "
            "ubezpieczonego)."
        )
    )
    daily_basis_zl: Decimal = Field(
        description=(
            "Dzienna podstawa wymiaru = 1/30 podstawy miesięcznej (ustawa zasiłkowa "
            "art. 36 ust. 3)."
        )
    )
    deduction_rate_percent: Decimal = Field(
        description="Stawka odliczenia składek finansowanych przez ubezpieczonego (13,71%)."
    )
    minimum_basis_applied: bool = Field(
        description=(
            "Czy zastosowano podstawę minimalną (płaca minimalna pomniejszona o 13,71%), "
            "ponieważ podana podstawa była niższa. Dotyczy wyłącznie pracowników pełnoetatowych."
        )
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Ostrzeżenia dotyczące wyliczenia podstawy (np. brakujące dane, uproszczenia).",
    )


class CalculatedAmount(BaseModel):
    benefit_code: str = Field(description="Kod świadczenia.")
    benefit_name: str = Field(description="Nazwa świadczenia do wyświetlenia użytkownikowi.")
    basis: BasisOfCalculation | None = Field(
        default=None,
        description="Podstawa wymiaru użyta do obliczeń. Null dla świadczeń ryczałtowych.",
    )
    total_days: int | None = Field(
        default=None,
        description=(
            "Liczba dni, za które wyliczono kwotę. Null, gdy nieznana (np. 'do dnia porodu') "
            "albo świadczenie jest ryczałtowe."
        ),
    )
    total_amount_zl: Decimal | None = Field(
        default=None,
        description=(
            "Łączna wyliczona kwota świadczenia w złotych. Null, gdy nie da się jej wyliczyć "
            "bez dodatkowych danych (np. faktycznej daty porodu)."
        ),
    )
    lump_sum_amount_zl: Decimal | None = Field(
        default=None,
        description="Kwota ryczałtowa (gdy świadczenie nie jest procentem podstawy wymiaru).",
    )
    rate_breakdown: list["RatePeriod"] = Field(
        default_factory=list,
        description=(
            "Rozbicie okresu na części o różnej stawce (np. świadczenie rehabilitacyjne: "
            "90% przez pierwsze 3 miesiące, 75% dalej). Puste dla świadczeń ze stałą stawką."
        ),
    )
    rules_version: int = Field(description="Wersja reguł użyta do obliczeń.")
    warnings: list[str] = Field(default_factory=list, description="Ostrzeżenia dla użytkownika.")


class RatePeriod(BaseModel):
    days: int = Field(description="Liczba dni w tym okresie.")
    rate_percentage: Decimal = Field(description="Stawka w tym okresie (% podstawy wymiaru).")
    amount_zl: Decimal = Field(description="Kwota za ten okres w złotych.")


CalculatedAmount.model_rebuild()


class ParentCalculationInput(BaseModel):
    """Dane jednego rodzica potrzebne do wyliczenia jego podstawy wymiaru - podzbiór pól z
    ``MaternityLeaveEligibilityRequest`` używany w porównaniu wariantów podziału urlopu
    rodzicielskiego między rodzicami."""

    label: str = Field(description="Etykieta rodzica do wyświetlenia (np. 'Matka', 'Ojciec').")
    average_monthly_income_zl: Decimal | None = Field(default=None)
    insurance_title: InsuranceTitle | None = Field(default=None)
    voluntary_contribution_base_zl: Decimal | None = Field(default=None)
    is_full_time_employment: bool | None = Field(default=None)


class ParentalLeaveCompareRequest(BaseModel):
    """Request dla porównania wariantów podziału urlopu rodzicielskiego między rodzicami."""

    children_count: int = Field(ge=1)
    za_zyciem_certificate: bool | None = Field(default=None)
    full_dose_claimed_within_21_days: bool | None = Field(default=None)
    parent_a: ParentCalculationInput
    parent_b: ParentCalculationInput


class ParentalLeaveVariant(BaseModel):
    label: str = Field(description="Opis wariantu (np. 'Matka wykorzystuje maksymalny wymiar').")
    weeks_parent_a: int
    weeks_parent_b: int
    amount_parent_a_zl: Decimal | None
    amount_parent_b_zl: Decimal | None
    total_household_amount_zl: Decimal | None


class ParentalLeaveCompareResponse(BaseModel):
    total_pool_weeks: int = Field(description="Łączna pula tygodni urlopu rodzicielskiego.")
    non_transferable_weeks_per_parent: int = Field(
        description=(
            "Liczba tygodni nieprzenoszalnych na rzecz drugiego rodzica (Kodeks pracy art. 1821a)."
        )
    )
    rate_percentage: Decimal = Field(description="Zastosowana stawka (70% albo 81,5%).")
    variants: list[ParentalLeaveVariant]
    warnings: list[str] = Field(default_factory=list)
