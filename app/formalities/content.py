"""Statyczne treści przewodnika po formalnościach, wzięte wprost z oficjalnego briefu
(``resorces/Projekt.pdf``, §H i §I) - nie wymyślone, nie zgadywane (zob. zasada
"nigdy nie zgaduj" w pamięci projektu `project-ebobo-brief`).
"""

from app.rules.seed import STILLBIRTH_FUNERAL_BENEFIT_CODE

# Projekt.pdf §H "ZAGROŻENIA ZWIĄZANE Z PRAWEM DO ZASIŁKU CHOROBOWEGO I MACIERZYŃSKIEGO"
# - cytowane niemal dosłownie, bo to oficjalne ostrzeżenia z briefu konkursowego, nie
# nasza interpretacja.
GENERAL_RISKS: list[str] = [
    "Zawarcie umowy albo podjęcie działalności gospodarczej wyłącznie dla pozoru (w "
    "celu zgłoszenia się do ubezpieczenia chorobowego) - ZUS może po postępowaniu "
    "uznać umowę za zawartą dla pozoru i wydać decyzję o niepodleganiu ubezpieczeniom "
    "społecznym, co pozbawia prawa do zasiłków.",
    "Podwyższenie podstawy wymiaru składek w okresie ciąży wyłącznie w celu uzyskania "
    "wyższych świadczeń - ZUS może po postępowaniu ustalić niższą podstawę, co obniży "
    "wysokość zasiłków.",
    "Niepodleganie ubezpieczeniu chorobowemu na dzień porodu - np. przez niezgłoszenie "
    "się do dobrowolnego ubezpieczenia, albo rozwiązanie stosunku pracy/zakończenie "
    "działalności gospodarczej/zakończenie umowy zlecenia przed porodem.",
]

# Projekt.pdf §I "SZCZEGÓLNA OCHRONA KOBIET - PRACOWNIC W CIĄŻY ORAZ PRACOWNIKÓW W
# OKRESIE URLOPÓW ZWIĄZANYCH Z RODZICIELSTWEM" - streszczenie.
EMPLOYMENT_PROTECTION_NOTE = (
    "W okresie ciąży oraz urlopu macierzyńskiego, a także od dnia złożenia wniosku o "
    "urlop macierzyński / na warunkach urlopu macierzyńskiego / uzupełniający urlop "
    "macierzyński / urlop ojcowski / urlop rodzicielski (albo ich części) do dnia "
    "zakończenia tego urlopu, pracodawca nie może przygotowywać się do wypowiedzenia "
    "lub rozwiązania umowy o pracę z tą osobą ani jej wypowiedzieć czy rozwiązać "
    "(Kodeks pracy, Projekt.pdf §I)."
)

# Projekt.pdf, wymagania funkcjonalne, punkt (i): wymóg wskazania podmiotów
# charytatywnych wspierających w szczególnych sytuacjach. Żadna konkretna organizacja
# nie jest tu wymieniona, bo projekt nie ma zweryfikowanych, aktualnych danych o takich
# podmiotach - wymyślanie nazw naruszyłoby zasadę "nigdy nie zgaduj".
CHARITABLE_SUPPORT_NOTE = (
    "Brief wymaga wskazania podmiotów o charakterze charytatywnym wspierających "
    "rodziców w szczególnych sytuacjach (śmierć dziecka, przedwczesny poród, "
    "poronienie, urodzenie ciężko chorego dziecka - Projekt.pdf, wymagania "
    "funkcjonalne, punkt i). Ta sekcja jest celowo pusta: projekt nie dysponuje "
    "zweryfikowaną, aktualną listą takich organizacji - zob. project-ebobo-brief "
    "('nigdy nie zgaduj'). Wymaga uzupełnienia przed pokazaniem jako kompletne."
)

DIFFICULT_SITUATION_BENEFIT_CODES: list[str] = [STILLBIRTH_FUNERAL_BENEFIT_CODE]

HOW_BENEFITS_ARE_PAID = (
    "Zasiłek wypłaca płatnik składek (pracodawca), jeśli zgłasza do ubezpieczenia "
    "chorobowego powyżej 20 ubezpieczonych - w pozostałych przypadkach, a także gdy "
    "ubezpieczenie już ustało (np. zasiłek w wysokości zasiłku macierzyńskiego), "
    "wypłaca ZUS. Właściwa instytucja dla konkretnego świadczenia jest wskazana w "
    "polu institution odpowiedzi - tam też trzeba złożyć wniosek."
)


def build_next_steps(benefit_code: str, institution: str) -> list[str]:
    return [
        f"Sprawdź uprawnienia: POST /api/v1/eligibility/check/{benefit_code}.",
        "Jeśli status to requires_verification, uzupełnij dane wskazane w "
        "missing_data i sprawdź ponownie.",
        f"Oblicz przewidywaną kwotę świadczenia: POST /api/v1/benefits/calculate/{benefit_code}.",
        "Przygotuj wymagane dokumenty (zob. required_documents).",
        f"Złóż wniosek z dokumentami u właściwej instytucji: {institution}.",
        "Jeśli possible_solutions wskazuje related_benefit_code innego świadczenia, "
        "sprawdź je osobno - może przysługiwać niezależnie.",
    ]
