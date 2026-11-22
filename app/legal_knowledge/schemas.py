from datetime import date

from pydantic import BaseModel


class LegalFragment(BaseModel):
    """Jeden fragment wiedzy prawnej - jednostka redakcyjna przepisu wraz z jego
    faktyczną treścią (nie tylko etykietą cytatu). To jest to, co faktycznie
    trafia do modelu AI jako grounding (zob. ``app/legal_advisor/service.py``) i to,
    względem czego backend weryfikuje identyfikatory źródeł zwrócone przez AI."""

    id: str
    source: str
    citation: str
    content: str
    effective_from: date
    effective_to: date | None = None
    related_benefit_codes: list[str]


def display_label(fragment: LegalFragment) -> str:
    """Czytelna dla użytkownika etykieta cytatu - ten sam styl, co dotychczasowe
    stringi w ``BenefitRuleVersion.legal_basis``, żeby nie zmieniać kontraktu
    odpowiedzi (``verified_legal_basis: list[str]``)."""
    return f"{fragment.source} {fragment.citation} ({fragment.content})"
