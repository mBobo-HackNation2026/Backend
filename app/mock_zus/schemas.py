"""Modele symulowanych danych ZUS (MockZUSProvider).

Dane tutaj są CAŁKOWICIE oddzielone od silnika uprawnień i kalkulatora - nigdy nie są
automatycznie wstrzykiwane do ``MaternityLeaveEligibilityRequest``. Front pobiera je
osobno (``GET /mock-zus/profiles/{profile_id}``) i pokazuje użytkownikowi obok jego
własnych deklaracji, nigdy w ich miejsce - przy rozbieżności oba źródła muszą być
widoczne (zob. ``POST /mock-zus/profiles/{profile_id}/compare``).
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.eligibility.schemas import InsuranceTitle


class MockInsurancePeriod(BaseModel):
    insurance_title: InsuranceTitle = Field(description="Tytuł ubezpieczenia w tym okresie.")
    start_date: date = Field(description="Data rozpoczęcia okresu ubezpieczenia.")
    end_date: date | None = Field(
        default=None, description="Data zakończenia okresu. Null = ubezpieczenie trwa nadal."
    )
    payer_name: str = Field(
        description="Symulowana nazwa płatnika składek (pracodawcy/zleceniodawcy)."
    )


class MockEZLAEntry(BaseModel):
    code: str = Field(description="Symulowany numer zaświadczenia e-ZLA.")
    start_date: date
    end_date: date
    status: Literal["aktualne", "zakonczone", "anulowane"] = Field(
        description="Status zaświadczenia."
    )


class MockBenefitUsageEntry(BaseModel):
    benefit_code: str = Field(description="Kod świadczenia (zob. app/eligibility/registry.py).")
    period_start: date
    period_end: date
    weeks_used: int | None = Field(default=None)
    amount_paid_zl: Decimal | None = Field(default=None)


class MockZusProfileSummary(BaseModel):
    profile_id: str = Field(description="Stabilny identyfikator profilu demonstracyjnego.")
    label: str = Field(description="Nazwa do wyświetlenia na ekranie wyboru sprawy.")
    description: str = Field(description="Krótki opis scenariusza.")


class MockZusProfileData(BaseModel):
    profile_id: str
    label: str
    as_of_date: date = Field(description="Data, na którą symulowany jest ten stan konta ZUS.")
    data_source: Literal["mock_zus_simulated"] = Field(
        default="mock_zus_simulated",
        description="Jawny znacznik, że to dane symulowane, nigdy prawdziwy odczyt z ZUS.",
    )
    is_currently_insured: bool = Field(
        description="Czy profil jest objęty ubezpieczeniem chorobowym na as_of_date."
    )
    current_insurance_title: InsuranceTitle | None = Field(default=None)
    insurance_periods: list[MockInsurancePeriod] = Field(default_factory=list)
    debt_amount_zl: Decimal = Field(description="Symulowane zadłużenie składkowe na as_of_date.")
    e_zla_entries: list[MockEZLAEntry] = Field(default_factory=list)
    benefit_usage_history: list[MockBenefitUsageEntry] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=lambda: [
            "Dane symulowane (MockZUSProvider) - nie pochodzą z rzeczywistego systemu ZUS."
        ]
    )


class MockZusCompareRequest(BaseModel):
    """Deklaracje podane przez użytkownika, porównywane z dansymi symulowanego profilu.
    Wszystkie pola opcjonalne - porównywane jest tylko to, co faktycznie podano."""

    insurance_title: InsuranceTitle | None = Field(default=None)
    insured_at_birth: bool | None = Field(
        default=None,
        description=(
            "Deklaracja użytkownika o własnym ubezpieczeniu - porównywana z "
            "is_currently_insured profilu (przybliżenie: profil opisuje stan na "
            "as_of_date, nie dokładnie na dzień porodu)."
        ),
    )
    debt_amount_zl: Decimal | None = Field(default=None)


class FieldComparison(BaseModel):
    field: str = Field(description="Nazwa porównywanego pola.")
    declared_value: str | None = Field(
        default=None, description="Wartość zadeklarowana przez użytkownika (jako tekst)."
    )
    simulated_value: str | None = Field(
        default=None, description="Wartość z symulowanego profilu ZUS (jako tekst)."
    )
    matches: bool | None = Field(
        default=None,
        description="Czy wartości się zgadzają. Null, gdy jedna ze stron nie podała wartości.",
    )


class MockZusCompareResponse(BaseModel):
    profile_id: str
    comparisons: list[FieldComparison]
    has_discrepancies: bool = Field(description="Czy którekolwiek porównane pole ma matches=False.")
