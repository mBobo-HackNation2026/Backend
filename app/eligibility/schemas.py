from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class InsuranceTitle(StrEnum):
    umowa_o_prace = "umowa_o_prace"
    zlecenie = "zlecenie"
    dzialalnosc_gospodarcza = "dzialalnosc_gospodarcza"
    inny = "inny"


class EmploymentEndedReason(StrEnum):
    upadlosc_likwidacja_smierc_pracodawcy = "upadlosc_likwidacja_smierc_pracodawcy"
    naruszenie_prawa_wyrokiem_sadu = "naruszenie_prawa_wyrokiem_sadu"


class MaternityLeaveEligibilityRequest(BaseModel):
    """Współdzielony schemat requestu dla wszystkich obecnie zaimplementowanych świadczeń
    (zob. app/eligibility/registry.py) - każde pole dotyczy tylko tych świadczeń, których
    ocena go faktycznie używa; pozostałe pola są dla nich po prostu ignorowane."""

    children_count: int = Field(ge=1, description="Liczba dzieci urodzonych przy jednym porodzie")
    insured_at_birth: bool | None = Field(
        default=None,
        description=(
            "Czy wnioskodawczyni była objęta ubezpieczeniem chorobowym w dniu porodu. "
            "None = nieznane."
        ),
    )
    insurance_title: InsuranceTitle | None = Field(
        default=None, description="Tytuł ubezpieczenia, jeśli znany."
    )
    debt_amount_zl: Decimal | None = Field(
        default=None,
        description="Zadłużenie składkowe na dzień powstania prawa do zasiłku, jeśli dotyczy.",
    )
    employment_ended_reason: EmploymentEndedReason | None = Field(
        default=None,
        description=(
            "Jeśli insured_at_birth=False: powód ustania ubezpieczenia w okresie ciąży, "
            "o ile wystąpił."
        ),
    )
    other_employment_secured: bool | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie 'zasiłku w wysokości zasiłku macierzyńskiego' (ustawa "
            "zasiłkowa art. 30 ust. 3, employment_ended_reason="
            "upadlosc_likwidacja_smierc_pracodawcy): czy po ustaniu poprzedniego "
            "zatrudnienia zapewniono wnioskodawczyni inne zatrudnienie. "
            "None = nieznane."
        ),
    )
    father_insured: bool | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie urlopu ojcowskiego: czy ojciec dziecka jest objęty "
            "ubezpieczeniem chorobowym. None = nieznane."
        ),
    )
    child_age_months: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Dotyczy wyłącznie urlopu ojcowskiego: wiek dziecka w pełnych miesiącach w "
            "dniu składania wniosku. Prawo do urlopu ojcowskiego wygasa po ukończeniu "
            "przez dziecko 12. miesiąca życia (Kodeks pracy). None = nieznane."
        ),
    )


class EligibilityStatus(StrEnum):
    """Wynik wstępnej oceny uprawnień. Nigdy nie jest to decyzja ZUS."""

    likely_eligible = "likely_eligible"
    """Wszystkie wymagane warunki są spełnione na podstawie podanych danych."""
    not_eligible = "not_eligible"
    """Potwierdzono, że co najmniej jeden warunek nie jest spełniony i nie ma
    alternatywnej ścieżki wymagającej weryfikacji."""
    requires_verification = "requires_verification"
    """Brakuje danych albo warunek nie jest spełniony, ale istnieje alternatywna
    ścieżka, którą trzeba potwierdzić osobno."""


class SolutionType(StrEnum):
    """Rodzaj możliwego rozwiązania."""

    alternative_benefit = "alternative_benefit"
    """Inne świadczenie, o które użytkownik może się ubiegać."""
    corrective_action = "corrective_action"
    """Działanie naprawcze, które może spełnić brakujący warunek."""
    limitation = "limitation"
    """Ograniczenie wynikające z przepisów, które należy uwzględnić."""


class DataSource(StrEnum):
    """Źródło danych wejściowych, na których oparto ocenę."""

    user = "user"
    """Dane podane ręcznie przez użytkownika."""


class PossibleSolution(BaseModel):
    type: SolutionType = Field(description="Rodzaj rozwiązania (patrz SolutionType).")
    description: str = Field(description="Opis rozwiązania przeznaczony dla użytkownika.")
    legal_basis: str | None = Field(
        default=None,
        description="Podstawa prawna rozwiązania, jeśli dotyczy.",
    )
    related_benefit_code: str | None = Field(
        default=None,
        description=(
            "Kod świadczenia, które warto sprawdzić osobno przez "
            "POST /eligibility/check/{benefit_code}, jeśli to rozwiązanie wskazuje na inne "
            "świadczenie niż to, którego dotyczy bieżąca ocena."
        ),
    )


class RequiredDocument(BaseModel):
    code: str = Field(description="Stabilny kod dokumentu.")
    name: str = Field(description="Nazwa dokumentu wyświetlana użytkownikowi.")
    when: str = Field(
        description="Kiedy dokument jest potrzebny, opisowo (np. przy składaniu wniosku)."
    )


class BenefitPlan(BaseModel):
    weeks: int | None = Field(
        default=None,
        description=(
            "Liczba tygodni, na które przysługuje świadczenie. Null, gdy czas trwania nie jest "
            "wyrażony w tygodniach - patrz duration_description."
        ),
    )
    duration_description: str | None = Field(
        default=None,
        description=(
            "Opis czasu trwania, gdy nie wyraża się go w tygodniach (np. 'do dnia porodu'). "
            "Null, gdy obowiązuje weeks."
        ),
    )
    rate_percentage: Decimal = Field(
        description="Stawka świadczenia w procentach podstawy wymiaru."
    )
    institution: str = Field(description="Instytucja, do której składa się wniosek (np. ZUS).")
    required_documents: list[RequiredDocument] = Field(
        description="Dokumenty, które należy przygotować lub złożyć."
    )
    deadlines: list[str] = Field(description="Terminy do spełnienia, opisane słownie.")
    legal_basis: list[str] = Field(description="Podstawy prawne uzasadniające plan.")


class EligibilityResult(BaseModel):
    benefit_code: str = Field(description="Kod świadczenia zgodny z definicją w regułach.")
    benefit_name: str = Field(description="Nazwa świadczenia do wyświetlenia użytkownikowi.")
    status: EligibilityStatus = Field(
        description=(
            "Wynik wstępnej oceny: likely_eligible - warunki spełnione; not_eligible - "
            "potwierdzony niespełniony warunek bez alternatywnej ścieżki; "
            "requires_verification - brakujące dane lub niespełniony warunek, dla którego "
            "istnieje ścieżka wymagająca osobnego potwierdzenia."
        )
    )
    met_conditions: list[str] = Field(
        description="Warunki uznane za spełnione na podstawie podanych danych."
    )
    unmet_conditions: list[str] = Field(description="Warunki potwierdzone jako niespełnione.")
    missing_data: list[str] = Field(
        description="Dane potrzebne do pełnej oceny, których nie podano."
    )
    possible_solutions: list[PossibleSolution] = Field(
        description=(
            "Możliwe rozwiązania: działania naprawcze, świadczenia alternatywne lub ograniczenia."
        )
    )
    plan: BenefitPlan | None = Field(
        description="Plan działania (wnioski, załączniki, instytucja, terminy, podstawa prawna). "
        "Null, gdy plan nie dotyczy wyniku oceny."
    )
    rules_version: int = Field(
        description="Wersja reguł (BenefitRuleVersion), na podstawie której wykonano ocenę."
    )
    data_source: DataSource = Field(
        default=DataSource.user,
        description=(
            "Źródło danych wejściowych. Obecnie zawsze 'user' (dane podane ręcznie). "
            "W przyszłości pojawią się wartości z integracji (np. symulowanej ZUS/mObywatel), "
            "które nie są jeszcze zaimplementowane."
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Ostrzeżenia dla użytkownika, np. o ograniczeniach oceny.",
    )
