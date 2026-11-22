"""Modele przewodnika po formalnościach.

Dokumenty/terminy/instytucja/podstawa prawna są wzięte wprost z reguły świadczenia
(``BenefitRuleVersion``, to samo źródło co ``BenefitPlan`` w silniku uprawnień) - nie
duplikujemy ich osobno. To, czego tu przybywa, to treści niezależne od konkretnej oceny:
ryzyka utraty uprawnień, ochrona przed zwolnieniem i kolejne kroki w procesie.
"""

from pydantic import BaseModel, Field

from app.eligibility.schemas import RequiredDocument


class FormalitiesGuide(BaseModel):
    benefit_code: str = Field(description="Kod świadczenia.")
    benefit_name: str = Field(description="Nazwa świadczenia do wyświetlenia użytkownikowi.")
    institution: str = Field(description="Instytucja, do której składa się wniosek.")
    required_documents: list[RequiredDocument] = Field(
        description="Dokumenty, które należy przygotować lub złożyć."
    )
    deadlines: list[str] = Field(description="Terminy do spełnienia, opisane słownie.")
    legal_basis: list[str] = Field(description="Podstawy prawne dotyczące tego świadczenia.")
    general_risks: list[str] = Field(
        description=(
            "Ogólne ryzyka utraty uprawnień albo zmniejszenia wysokości świadczenia "
            "(Projekt.pdf §H) - dotyczą całego systemu zasiłków, nie tylko tego "
            "świadczenia."
        )
    )
    employment_protection_note: str = Field(
        description=(
            "Ochrona przed zwolnieniem w okresie ciąży/urlopów związanych z "
            "rodzicielstwem (Kodeks pracy, Projekt.pdf §I)."
        )
    )
    next_steps: list[str] = Field(
        description="Kolejne kroki w procesie ubiegania się o to świadczenie, w kolejności."
    )
    rules_version: int = Field(
        description="Wersja reguł (BenefitRuleVersion), z której pochodzą dokumenty/terminy."
    )


class GeneralFormalitiesGuide(BaseModel):
    how_benefits_are_paid: str = Field(
        description=(
            "Ogólne wyjaśnienie, kto wypłaca zasiłek (pracodawca albo ZUS) i od czego to zależy."
        )
    )
    general_risks: list[str] = Field(
        description=(
            "Ryzyka utraty uprawnień albo zmniejszenia wysokości świadczeń (Projekt.pdf §H)."
        )
    )
    employment_protection_note: str = Field(
        description=(
            "Ochrona przed zwolnieniem w okresie ciąży/urlopów związanych z rodzicielstwem."
        )
    )
    charitable_support_note: str = Field(
        description=(
            "Dotyczy wymogu z Projekt.pdf (punkt i): informacje o podmiotach "
            "charytatywnych wspierających rodziców w szczególnych sytuacjach (śmierć "
            "dziecka, przedwczesny poród, poronienie, ciężka choroba dziecka). Lista "
            "konkretnych organizacji NIE jest tu podana - wymaga zweryfikowanych, "
            "aktualnych danych, których projekt jeszcze nie ma (zob. zasada "
            "'nigdy nie zgaduj' - project-ebobo-brief)."
        )
    )
    difficult_situation_benefit_codes: list[str] = Field(
        description=(
            "Kody świadczeń bezpośrednio odpowiadające na szczególnie trudne sytuacje "
            "wymienione w briefie (np. martwe urodzenie)."
        )
    )
