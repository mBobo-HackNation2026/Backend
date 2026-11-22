"""Dostęp do ``LEGAL_FRAGMENTS`` - "minimalny RAG bez bazy wektorowej": wybór
fragmentów to proste filtrowanie po ``benefit_code`` i dacie obowiązywania, nie
wyszukiwanie semantyczne (nie jest potrzebne przy tak małym, statycznym zbiorze)."""

from datetime import date as date_

from app.legal_knowledge.fragments import LEGAL_FRAGMENTS
from app.legal_knowledge.schemas import LegalFragment


def get_fragments_for_benefit(
    benefit_code: str, *, as_of: date_ | None = None
) -> list[LegalFragment]:
    """Fragmenty powiązane z danym świadczeniem, obowiązujące na dzień ``as_of``
    (domyślnie dziś). Fragment z ``effective_to`` w przeszłości jest pomijany -
    przygotowanie pod przyszłe nieaktualne/wygasłe źródła, nawet jeśli dziś żaden
    fragment faktycznie nie wygasł."""
    reference_date = as_of or date_.today()
    return [
        fragment
        for fragment in LEGAL_FRAGMENTS
        if benefit_code in fragment.related_benefit_codes
        and fragment.effective_from <= reference_date
        and (fragment.effective_to is None or fragment.effective_to >= reference_date)
    ]


def get_fragment_by_id(fragment_id: str) -> LegalFragment | None:
    for fragment in LEGAL_FRAGMENTS:
        if fragment.id == fragment_id:
            return fragment
    return None
