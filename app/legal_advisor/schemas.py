from typing import Literal

from pydantic import BaseModel, Field

from app.eligibility.schemas import EligibilityStatus


class GroundedRecommendation(BaseModel):
    """Jedna propozycja dalszego postępowania wraz z fragmentami wiedzy prawnej, na
    których AI ją oparło. Pusta lista ``supporting_fragment_ids`` jest dopuszczalna
    (ogólna/proceduralna wskazówka, np. "przygotuj dokumenty", nie niesie własnej
    tezy prawnej do zweryfikowania) - ale lista NIEPRAWIDŁOWYCH id (spoza
    dostarczonego zbioru fragmentów) powoduje odrzucenie całej rekomendacji."""

    text: str
    supporting_fragment_ids: list[str] = Field(default_factory=list)


class AIExplanationRaw(BaseModel):
    """Oczekiwany kształt odpowiedzi modelu AI - pierwsza linia walidacji (brief pkt 6:
    "Odpowiedź AI musi przechodzić walidację schematu Pydantic"). Celowo nie ma tu pól
    status/amount - model nigdy nie jest proszony o nie i nawet gdyby je zwrócił,
    zostałyby po prostu zignorowane (Pydantic domyślnie odrzuca nieznane pola), bo
    ``LegalAdvisorExplainResponse`` buduje ``status`` wyłącznie z wyniku silnika."""

    explanation: str
    missing_data_explained: list[str] = Field(default_factory=list)
    suggested_next_steps: list[GroundedRecommendation] = Field(default_factory=list)
    other_benefits_to_check: list[str] = Field(default_factory=list)
    cited_fragment_ids: list[str] = Field(default_factory=list)
    requires_additional_verification: bool = False


class LegalAdvisorExplainResponse(BaseModel):
    benefit_code: str
    status: EligibilityStatus = Field(
        description="Wynik deterministycznego silnika uprawnień - AI go nie zmienia ani nie ustala."
    )
    explanation: str = Field(description="Wyjaśnienie wyniku w prostym języku.")
    missing_data_explained: list[str] = Field(
        default_factory=list, description="Brakujące dane/dokumenty, wyjaśnione w prostym języku."
    )
    suggested_next_steps: list[str] = Field(
        default_factory=list,
        description=(
            "Zgodne z prawem propozycje dalszego postępowania. Każda pozycja albo nie "
            "niesie własnej tezy prawnej (ogólna wskazówka proceduralna), albo jest "
            "oparta na co najmniej jednym fragmencie z lokalnej bazy wiedzy prawnej - "
            "rekomendacje AI powołujące się na nieistniejący fragment są odrzucane w "
            "całości, nigdy nie są pokazywane jako potwierdzone."
        ),
    )
    other_benefits_to_check: list[str] = Field(
        default_factory=list,
        description="Inne świadczenia, które warto sprawdzić osobno (kody do /eligibility/check).",
    )
    verified_legal_basis: list[str] = Field(
        default_factory=list,
        description=(
            "Fragmenty wiedzy prawnej (z ``app/legal_knowledge``, zawierające faktyczną "
            "treść przepisu, nie tylko etykietę), na których AI oparło wyjaśnienie - "
            "przytoczone wyłącznie, jeśli backend zweryfikował, że fragment faktycznie "
            "istnieje i dotyczy tego świadczenia. Niezweryfikowane cytaty są odrzucane - "
            "nigdy nie są pokazywane użytkownikowi jako potwierdzone."
        ),
    )
    requires_additional_verification: bool = Field(
        description=(
            "True, gdy AI samo to zgłosiło, gdy backend odrzucił choć jeden "
            "niezweryfikowany cytat prawny lub rekomendację z odpowiedzi AI, albo gdy w "
            "lokalnej bazie wiedzy brak fragmentów dla tego świadczenia."
        )
    )
    rules_version: int = Field(description="Wersja reguł, na podstawie której wykonano ocenę.")
    ai_available: bool = Field(description="Czy odpowiedź pochodzi faktycznie od dostawcy AI.")
    source: Literal["ai", "fallback"] = Field(
        description=(
            "'ai' - wyjaśnienie wygenerowane przez model; 'fallback' - OpenRouter był "
            "niedostępny/zwrócił nieprawidłową odpowiedź, więc użyto treści zbudowanej "
            "wyłącznie z deterministycznego wyniku silnika (bez AI, bez ryzyka halucynacji)."
        )
    )
    request_log_entry_id: int | None = Field(
        default=None,
        description=(
            "Id wpisu w dzienniku żądań (request_log) dla tej analizy - punkt zaczepienia "
            "pod przyszłe powiązanie z feedbackiem użytkownika (brief pkt 5)."
        ),
    )
