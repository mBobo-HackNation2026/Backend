"""Statyczne profile demonstracyjne MockZUSProvider.

Każdy profil to kompletny, symulowany "wyciąg z konta ZUS" dla jednej demo-sprawy -
dane wyłącznie syntetyczne, nigdy pochodzące z prawdziwych dokumentów ZUS (zob. pamięć
projektu `project-ebobo-brief`: chronione próbki z `resorces/Sprawy/` nie są
publikowane). Brak potrzeby przechowywania w bazie/wersjonowania jak reguł świadczeń -
to dane demonstracyjne, nie parametry prawne.
"""

from datetime import date
from decimal import Decimal

from app.eligibility.schemas import InsuranceTitle
from app.mock_zus.schemas import (
    MockInsurancePeriod,
    MockZusProfileData,
    MockZusProfileSummary,
)

_AS_OF_DATE = date(2026, 11, 22)

MOCK_ZUS_PROFILES: dict[str, MockZusProfileData] = {
    "matka_umowa_o_prace_standard": MockZusProfileData(
        profile_id="matka_umowa_o_prace_standard",
        label="Matka na umowie o pracę, bez przeszkód",
        as_of_date=_AS_OF_DATE,
        is_currently_insured=True,
        current_insurance_title=InsuranceTitle.umowa_o_prace,
        insurance_periods=[
            MockInsurancePeriod(
                insurance_title=InsuranceTitle.umowa_o_prace,
                start_date=date(2023, 1, 1),
                end_date=None,
                payer_name="ABC Logistyka Sp. z o.o.",
            )
        ],
        debt_amount_zl=Decimal("0.00"),
    ),
    "zlecenie_okres_wyczekiwania": MockZusProfileData(
        profile_id="zlecenie_okres_wyczekiwania",
        label="Zleceniobiorczyni, krótki okres ubezpieczenia (w trakcie wyczekiwania)",
        as_of_date=_AS_OF_DATE,
        is_currently_insured=True,
        current_insurance_title=InsuranceTitle.zlecenie,
        insurance_periods=[
            MockInsurancePeriod(
                insurance_title=InsuranceTitle.zlecenie,
                start_date=date(2026, 10, 8),
                end_date=None,
                payer_name="Zleceniodawca XYZ Sp. z o.o.",
            )
        ],
        debt_amount_zl=Decimal("0.00"),
    ),
    "upadlosc_pracodawcy": MockZusProfileData(
        profile_id="upadlosc_pracodawcy",
        label="Ubezpieczenie ustało wskutek upadłości pracodawcy w ciąży",
        as_of_date=_AS_OF_DATE,
        is_currently_insured=False,
        current_insurance_title=None,
        insurance_periods=[
            MockInsurancePeriod(
                insurance_title=InsuranceTitle.umowa_o_prace,
                start_date=date(2022, 3, 1),
                end_date=date(2026, 9, 15),
                payer_name="Firma Budowlana Sp. z o.o. (w upadłości)",
            )
        ],
        debt_amount_zl=Decimal("0.00"),
    ),
    "dzialalnosc_z_zadluzeniem": MockZusProfileData(
        profile_id="dzialalnosc_z_zadluzeniem",
        label="Działalność gospodarcza z zadłużeniem składkowym",
        as_of_date=_AS_OF_DATE,
        is_currently_insured=True,
        current_insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        insurance_periods=[
            MockInsurancePeriod(
                insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
                start_date=date(2020, 5, 1),
                end_date=None,
                payer_name="Jednoosobowa działalność gospodarcza",
            )
        ],
        debt_amount_zl=Decimal("100.00"),
    ),
    "ojciec_urlop_ojcowski": MockZusProfileData(
        profile_id="ojciec_urlop_ojcowski",
        label="Ojciec ubezpieczony, dziecko w wieku kwalifikującym do urlopu ojcowskiego",
        as_of_date=_AS_OF_DATE,
        is_currently_insured=True,
        current_insurance_title=InsuranceTitle.umowa_o_prace,
        insurance_periods=[
            MockInsurancePeriod(
                insurance_title=InsuranceTitle.umowa_o_prace,
                start_date=date(2019, 6, 1),
                end_date=None,
                payer_name="Szkoła Podstawowa nr 5",
            )
        ],
        debt_amount_zl=Decimal("0.00"),
    ),
}

_PROFILE_DESCRIPTIONS: dict[str, str] = {
    "matka_umowa_o_prace_standard": (
        "Standardowy przypadek: ciągłe ubezpieczenie na umowę o pracę, brak zadłużenia - "
        "demonstruje likely_eligible bez przeszkód."
    ),
    "zlecenie_okres_wyczekiwania": (
        "Zleceniobiorczyni ubezpieczona od 45 dni (wymagane 90 przy dobrowolnym "
        "ubezpieczeniu) - demonstruje requires_verification/not_eligible z powodu "
        "niespełnionego okresu wyczekiwania."
    ),
    "upadlosc_pracodawcy": (
        "Ubezpieczenie ustało w okresie ciąży wskutek upadłości pracodawcy - "
        "demonstruje ścieżkę art. 30 ustawy zasiłkowej (zasiłek w wysokości zasiłku "
        "macierzyńskiego)."
    ),
    "dzialalnosc_z_zadluzeniem": (
        "Osoba prowadząca działalność gospodarczą z zadłużeniem składkowym powyżej "
        "progu 1% minimalnego wynagrodzenia - demonstruje wyłączenie prawa do "
        "zasiłku z powodu zadłużenia (ustawa zasiłkowa art. 2a)."
    ),
    "ojciec_urlop_ojcowski": (
        "Ojciec ubezpieczony na umowę o pracę, dziecko w wieku 2 miesięcy - "
        "demonstruje urlop ojcowski w terminie."
    ),
}


def list_profile_summaries() -> list[MockZusProfileSummary]:
    return [
        MockZusProfileSummary(
            profile_id=profile_id,
            label=profile.label,
            description=_PROFILE_DESCRIPTIONS[profile_id],
        )
        for profile_id, profile in MOCK_ZUS_PROFILES.items()
    ]


def get_profile(profile_id: str) -> MockZusProfileData | None:
    return MOCK_ZUS_PROFILES.get(profile_id)
