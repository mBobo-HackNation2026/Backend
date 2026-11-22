from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

# Sanity upper bound for monetary input fields (income/debt/contribution base), not a
# legal limit - purely defensive. Without it, an absurd/malformed value (e.g. a typo
# with far too many digits) can reach Decimal arithmetic in the calculator and raise
# decimal.InvalidOperation on .quantize() once it exceeds the default 28-digit
# precision context, crashing the request with an uncaught HTTP 500 instead of a
# clean 422. 1 miliard zł/miesiąc is already absurdly higher than any real income.
_MAX_REASONABLE_MONTHLY_AMOUNT_ZL = Decimal("1000000000.00")


class InsuranceTitle(StrEnum):
    umowa_o_prace = "umowa_o_prace"
    zlecenie = "zlecenie"
    dzialalnosc_gospodarcza = "dzialalnosc_gospodarcza"
    inny = "inny"


class EmploymentEndedReason(StrEnum):
    upadlosc_likwidacja_smierc_pracodawcy = "upadlosc_likwidacja_smierc_pracodawcy"
    naruszenie_prawa_wyrokiem_sadu = "naruszenie_prawa_wyrokiem_sadu"


class FosterCareType(StrEnum):
    rodzina_zastepcza = "rodzina_zastepcza"
    rodzina_zastepcza_zawodowa = "rodzina_zastepcza_zawodowa"
    wniosek_o_przysposobienie = "wniosek_o_przysposobienie"


class BonusType(StrEnum):
    miesieczna = "miesieczna"
    kwartalna = "kwartalna"
    roczna = "roczna"


class MaternityLeaveEligibilityRequest(BaseModel):
    """Współdzielony schemat requestu dla wszystkich obecnie zaimplementowanych świadczeń
    (zob. app/eligibility/registry.py) - każde pole dotyczy tylko tych świadczeń, których
    ocena go faktycznie używa; pozostałe pola są dla nich po prostu ignorowane."""

    # --- Pola wspólne / podstawowe ---
    children_count: int = Field(ge=1, description="Liczba dzieci urodzonych przy jednym porodzie")
    insured_at_birth: bool | None = Field(
        default=None,
        description=(
            "Czy wnioskodawczyni była objęta ubezpieczeniem chorobowym w dniu porodu. "
            "None = nieznane."
        ),
    )
    insurance_title: InsuranceTitle | None = Field(
        default=None,
        description=(
            "Tytuł ubezpieczenia, jeśli znany. Używany też przy ustalaniu podstawy wymiaru "
            "(pracownik - ustawa zasiłkowa art. 36-38, niebędący pracownikiem - art. 48)."
        ),
    )
    debt_amount_zl: Decimal | None = Field(
        default=None,
        ge=0,
        le=_MAX_REASONABLE_MONTHLY_AMOUNT_ZL,
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

    # --- Zasiłek chorobowy w ciąży / świadczenie rehabilitacyjne (okresy wyczekiwania) ---
    is_pregnant: bool | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie zasiłku chorobowego w ciąży: czy niezdolność do pracy "
            "powstała w okresie ciąży - warunkuje podwyższoną stawkę 100% (zamiast 80%) "
            "i dłuższy maksymalny okres 270 dni (zamiast 182) (ustawa zasiłkowa art. 8 "
            "ust. 1 i art. 11 ust. 1). None = nieznane."
        ),
    )
    insured_days_continuous: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Liczba dni nieprzerwanego ubezpieczenia chorobowego do dnia powstania "
            "niezdolności do pracy. Dotyczy głównie zasiłku chorobowego w ciąży - weryfikuje "
            "okres wyczekiwania: 30 dni przy ubezpieczeniu obowiązkowym, 90 dni przy "
            "dobrowolnym (ustawa zasiłkowa art. 4). None = nieznane."
        ),
    )

    # --- Uzupełniający urlop macierzyński (hospitalizacja dziecka) ---
    child_hospitalization_weeks: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Dotyczy wyłącznie uzupełniającego urlopu macierzyńskiego: liczba tygodni "
            "pobytu dziecka w szpitalu po porodzie; niepełny tydzień zaokrągla się w górę "
            "(Kodeks pracy art. 1802 §1). None = nieznane."
        ),
    )
    gestational_week_at_birth: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Dotyczy wyłącznie uzupełniającego urlopu macierzyńskiego: tydzień ciąży, w "
            "którym nastąpił poród - razem z birth_weight_grams określa graniczny tydzień "
            "po porodzie (15. albo 8.) do którego można skorzystać z urlopu "
            "(Kodeks pracy art. 1802 §1). None = nieznane."
        ),
    )
    birth_weight_grams: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Dotyczy wyłącznie uzupełniającego urlopu macierzyńskiego: masa urodzeniowa "
            "dziecka w gramach - patrz gestational_week_at_birth. None = nieznane."
        ),
    )
    postpartum_weeks_elapsed: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Dotyczy wyłącznie uzupełniającego urlopu macierzyńskiego: liczba pełnych "
            "tygodni, które upłynęły od porodu do dnia składania wniosku - porównywana z "
            "granicznym tygodniem wynikającym z gestational_week_at_birth/"
            "birth_weight_grams. None = nieznane."
        ),
    )

    # --- Urlop na warunkach urlopu macierzyńskiego (adopcja / rodzina zastępcza) ---
    is_adoption_or_foster_care: bool | None = Field(
        default=None,
        description=(
            "Czy wniosek dotyczy przyjęcia dziecka na wychowanie (przysposobienie lub "
            "rodzina zastępcza), a nie urodzenia własnego dziecka (Kodeks pracy art. 183). "
            "None = nieznane."
        ),
    )
    foster_care_type: FosterCareType | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie urlopu na warunkach urlopu macierzyńskiego, gdy "
            "is_adoption_or_foster_care=True: forma przyjęcia dziecka - określa "
            "obowiązujący limit wieku dziecka (Kodeks pracy art. 183 §1/§1(1)/§3). Uwaga: "
            "rodzina_zastepcza_zawodowa nie uprawnia do tego urlopu. None = nieznane."
        ),
    )
    child_age_years: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Dotyczy wyłącznie urlopu na warunkach urlopu macierzyńskiego: wiek dziecka w "
            "pełnych latach w dniu przyjęcia na wychowanie/złożenia wniosku - limit zależy "
            "od foster_care_type (7 lat rodzina zastępcza, 10 lat przy odroczonym "
            "obowiązku szkolnym, 14 lat przysposobienie). None = nieznane."
        ),
    )
    school_obligation_deferred: bool | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie urlopu na warunkach urlopu macierzyńskiego przy rodzinie "
            "zastępczej: czy wobec dziecka odroczono obowiązek szkolny - podnosi limit "
            "wieku z 7 do 10 lat (Kodeks pracy art. 183 §1). None = nieznane."
        ),
    )

    # --- Urlop rodzicielski (w tym podział między rodzicami) ---
    za_zyciem_certificate: bool | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie urlopu rodzicielskiego: czy dziecko posiada zaświadczenie "
            "'Za życiem' (ciężkie i nieodwracalne upośledzenie albo nieuleczalna choroba "
            "zagrażająca życiu) - wydłuża urlop rodzicielski z 41/43 do 65/67 tygodni "
            "(ustawa zasiłkowa art. 31 ust. 3). None = nieznane."
        ),
    )
    full_dose_claimed_within_21_days: bool | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie urlopu rodzicielskiego: czy wniosek o cały przysługujący "
            "wymiar urlopu rodzicielskiego złożono nie później niż 21 dni po porodzie - "
            "warunkuje stawkę 81,5% łącznie z macierzyńskim zamiast 70% (ustawa zasiłkowa "
            "art. 31 ust. 3g i ust. 4; nie dotyczy nieprzenoszalnych 9 tygodni drugiego "
            "rodzica, zawsze płatnych 70%). None = nieznane."
        ),
    )
    other_parent_used_parental_leave_weeks: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Dotyczy wyłącznie urlopu rodzicielskiego: liczba tygodni urlopu "
            "rodzicielskiego już wykorzystanych przez drugiego rodzica - 9 tygodni z puli "
            "jest nieprzenoszalne per rodzic (Kodeks pracy art. 1821a). None = nieznane."
        ),
    )
    part_time_fraction_during_parental_leave: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Dotyczy wyłącznie urlopu rodzicielskiego: ułamek etatu, w jakim wnioskodawca "
            "planuje łączyć urlop rodzicielski z pracą (maks. 1/2 etatu) - wydłuża urlop "
            "proporcjonalnie, maks. do 82/86 tygodni (130/134 z zaświadczeniem 'Za życiem'; "
            "Kodeks pracy art. 1821f). None = nie dotyczy/nieznane."
        ),
    )

    # --- Świadczenie rehabilitacyjne ---
    sickness_benefit_period_exhausted: bool | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie świadczenia rehabilitacyjnego: czy wnioskodawca wyczerpał "
            "maksymalny okres zasiłku chorobowego - świadczenie rehabilitacyjne przysługuje "
            "dopiero po jego wyczerpaniu (ustawa zasiłkowa art. 18 ust. 1). None = nieznane."
        ),
    )
    medical_prognosis_recovery_possible: bool | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie świadczenia rehabilitacyjnego: czy lekarz orzecznik ZUS "
            "stwierdził, że dalsze leczenie lub rehabilitacja rokują odzyskanie zdolności "
            "do pracy (ustawa zasiłkowa art. 18 ust. 1). None = nieznane."
        ),
    )
    excluded_from_rehabilitation_benefit: bool | None = Field(
        default=None,
        description=(
            "Dotyczy wyłącznie świadczenia rehabilitacyjnego: czy wnioskodawcy przysługuje "
            "już inne świadczenie wykluczające prawo do świadczenia rehabilitacyjnego "
            "(emerytura, renta, zasiłek dla bezrobotnych, świadczenie przedemerytalne, "
            "rodzicielskie świadczenie uzupełniające, nauczycielskie świadczenie "
            "kompensacyjne, urlop dla poratowania zdrowia - ustawa zasiłkowa art. 18 "
            "ust. 7). None = nieznane."
        ),
    )

    # --- Martwe urodzenie / zgon dziecka ---
    is_stillbirth_or_infant_death: bool | None = Field(
        default=None,
        description=(
            "Czy doszło do martwego urodzenia dziecka albo zgonu dziecka przed "
            "ukończeniem 8. tygodnia życia - wpływa na wymiar urlopu macierzyńskiego "
            "(8 tygodni po porodzie, nie krócej niż 7 dni od zgonu, Kodeks pracy art. 1801) "
            "oraz uprawnia do zasiłku pogrzebowego w razie martwego urodzenia. "
            "None = nieznane."
        ),
    )
    days_since_death: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Dotyczy wyłącznie minimalnego gwarantowanego wymiaru urlopu macierzyńskiego "
            "po zgonie dziecka (7 dni od zgonu, Kodeks pracy art. 1801) - NIE używane do "
            "terminu zasiłku pogrzebowego przy martwym urodzeniu, który liczy się od dnia "
            "pochówku, nie od zgonu (patrz days_since_burial). None = nieznane."
        ),
    )
    children_survived_count: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Liczba dzieci z tego samego porodu, które pozostały przy życiu - potrzebna "
            "WYŁĄCZNIE gdy is_stillbirth_or_infant_death=True i children_count > 1, żeby "
            "ustalić wymiar urlopu macierzyńskiego 'stosowny do liczby dzieci pozostałych "
            "przy życiu' (Kodeks pracy art. 1801 §1 zdanie 2). Ignorowane przy jednym "
            "dziecku (wymiar to wtedy zawsze 8 tygodni) albo gdy "
            "is_stillbirth_or_infant_death nie jest True. None = nieznane."
        ),
    )
    days_since_burial: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Dotyczy wyłącznie zasiłku pogrzebowego w razie martwego urodzenia: liczba "
            "dni, które upłynęły od dnia pochówku (nie od zgonu/porodu) - wniosek Z-12 "
            "trzeba złożyć w ciągu 12 miesięcy od dnia pochówku (Poradnik ZUS 2026, "
            "s.36). None = nieznane."
        ),
    )

    # --- Podstawa wymiaru (dla kalkulatora) ---
    average_monthly_income_zl: Decimal | None = Field(
        default=None,
        ge=0,
        le=_MAX_REASONABLE_MONTHLY_AMOUNT_ZL,
        description=(
            "Średni miesięczny przychód/wynagrodzenie z 12 miesięcy kalendarzowych "
            "poprzedzających miesiąc powstania prawa do świadczenia - podstawa wyliczenia "
            "podstawy wymiaru zasiłku (ustawa zasiłkowa art. 36-38 dla pracownika, art. 48 "
            "dla niebędącego pracownikiem). None = nieznane."
        ),
    )
    is_full_time_employment: bool | None = Field(
        default=None,
        description=(
            "Czy ubezpieczony jest zatrudniony w pełnym wymiarze czasu pracy. Używane "
            "wyłącznie do ustalenia, czy stosuje się podstawę minimalną (ustawa "
            "zasiłkowa art. 45 ust. 1 - dotyczy wyłącznie pracy w pełnym wymiarze czasu "
            "pracy; przy niepełnym etacie podstawa minimalna nie obowiązuje). "
            "None = nieznane - kalkulator wtedy NIE stosuje podstawy minimalnej i "
            "sygnalizuje to ostrzeżeniem, zamiast zgadywać."
        ),
    )
    employment_duration_months: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Liczba pełnych miesięcy zatrudnienia/ubezpieczenia przed miesiącem powstania "
            "prawa do świadczenia. Jeśli <12 miesięcy, podstawę wymiaru liczy się ze "
            "średniej pełnych przepracowanych miesięcy (ustawa zasiłkowa art. 36 ust. 2). "
            "None = nieznane."
        ),
    )
    voluntary_contribution_base_zl: Decimal | None = Field(
        default=None,
        ge=0,
        le=_MAX_REASONABLE_MONTHLY_AMOUNT_ZL,
        description=(
            "Dotyczy wyłącznie ubezpieczonych niebędących pracownikami (zlecenie/"
            "działalność gospodarcza): zadeklarowana podstawa wymiaru dobrowolnej składki "
            "chorobowej, ograniczona do 23 550,00 zł miesięcznie w 2026 r. - limit "
            "podstawy zasiłku po odliczeniu: 20 321,30 zł (ustawa zasiłkowa art. 48). "
            "None = nieznane/nie dotyczy."
        ),
    )
    bonus_type: BonusType | None = Field(
        default=None,
        description=(
            "Rodzaj premii/nagrody uwzględnianej w podstawie wymiaru, jeśli dotyczy: "
            "miesięczna wlicza się kwotą za dany miesiąc, kwartalna jako 1/12 sumy z 4 "
            "poprzednich kwartałów, roczna (np. trzynastka) jako 1/12 kwoty za rok "
            "poprzedni (ustawa zasiłkowa art. 42). None = nie dotyczy/nieznane."
        ),
    )
    months_since_last_benefit: Decimal | None = Field(
        default=None,
        ge=0,
        description=(
            "Liczba miesięcy, które upłynęły od zakończenia poprzedniego okresu "
            "pobierania zasiłku. Przerwa krótsza niż 1 miesiąc kalendarzowy zachowuje tę "
            "samą podstawę wymiaru, dłuższa powoduje przeliczenie od nowa (ustawa "
            "zasiłkowa art. 43). None = nie dotyczy/nieznane."
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
    rate_percentage: Decimal | None = Field(
        default=None,
        description=(
            "Stawka świadczenia w procentach podstawy wymiaru. Null, gdy świadczenie "
            "jest kwotą ryczałtową - patrz lump_sum_amount_zl."
        ),
    )
    lump_sum_amount_zl: Decimal | None = Field(
        default=None,
        description=(
            "Kwota ryczałtowa świadczenia w złotych, gdy świadczenie nie jest wyrażone "
            "jako procent podstawy wymiaru (np. zasiłek pogrzebowy przy martwym "
            "urodzeniu). Null, gdy obowiązuje rate_percentage."
        ),
    )
    institution: str = Field(description="Instytucja, do której składa się wniosek (np. ZUS).")
    required_documents: list[RequiredDocument] = Field(
        description="Dokumenty, które należy przygotować lub złożyć."
    )
    deadlines: list[str] = Field(description="Terminy do spełnienia, opisane słownie.")
    legal_basis: list[str] = Field(description="Podstawy prawne uzasadniające plan.")


class MissingFieldInfo(BaseModel):
    """Stabilny identyfikator brakującego pola żądania, sparowany z tekstem komunikatu
    (patrz ``EligibilityResult.missing_fields``). ``field`` jest zawsze dokładną nazwą
    pola z ``MaternityLeaveEligibilityRequest`` - FE może je bezpiecznie zmapować na
    kontrolkę formularza bez heurystycznego parsowania polskiego tekstu."""

    field: str = Field(description="Nazwa pola w MaternityLeaveEligibilityRequest.")
    message: str = Field(
        description="Ten sam tekst co odpowiadający wpis w missing_data (ta sama kolejność)."
    )


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
    missing_fields: list[MissingFieldInfo] = Field(
        default_factory=list,
        description=(
            "Stabilne identyfikatory pól żądania, każdy sparowany z dokładną treścią "
            "komunikatu, który też występuje w missing_data - do bezpiecznego budowania "
            "formularza uzupełniania danych bez parsowania tekstu. Może mieć więcej "
            "wpisów niż missing_data, gdy jeden komunikat dotyczy więcej niż jednego "
            "pola (ta sama message wtedy powtarza się, raz na pole). missing_data "
            "zostaje bez zmian dla kompatybilności wstecznej; to pole jest dodatkiem."
        ),
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
