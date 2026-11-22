"""Niewielka, statyczna baza fragmentów wiedzy prawnej (bez bazy wektorowej - zob.
brief "eBobo Legal Intelligence", rozbudowa Funkcji 1, pkt 2: "Na tym etapie nie
potrzebujemy ChromaDB, Pinecone ani dodatkowej infrastruktury").

Treść każdego fragmentu NIE jest tu wymyślana od nowa - jest rozbita/zrestrukturyzowana
z cytatów już zweryfikowanych i używanych w ``app/rules/seed.py`` (``legal_basis``),
które przeszły już wcześniejszą, wielokrotną weryfikację względem źródeł w ``resorces/``
w trakcie tej sesji (w tym poprawki cytowań przy okazji napraw Etap 4 - zob. pamięć
projektu ``project-ebobo-etap4-qa-fixes``). Gdzie jeden wpis w ``legal_basis`` łączył
dwa różne przepisy w jednym stringu, rozdzielono go tutaj na osobne fragmenty - bez
zmiany treści merytorycznej.

``effective_from=date(2026, 1, 1)`` dla wszystkich fragmentów - to ta sama data, którą
``app/rules/seed.py`` już przypisuje każdej wersji reguły (stan prawny przyjęty w
całym projekcie), nie nowa, zgadywana wartość.
"""

from datetime import date

from app.legal_knowledge.schemas import LegalFragment
from app.rules.seed import (
    ADOPTION_LEAVE_BENEFIT_CODE,
    ALTERNATIVE_BENEFIT_CODE,
    MATERNITY_LEAVE_BENEFIT_CODE,
    PARENTAL_LEAVE_BENEFIT_CODE,
    PATERNITY_LEAVE_BENEFIT_CODE,
    REHABILITATION_BENEFIT_CODE,
    SICKNESS_DURING_PREGNANCY_BENEFIT_CODE,
    STILLBIRTH_FUNERAL_BENEFIT_CODE,
    SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
)

_EFFECTIVE_FROM = date(2026, 1, 1)


def _fragment(
    id: str,
    source: str,
    citation: str,
    content: str,
    related_benefit_codes: list[str],
) -> LegalFragment:
    return LegalFragment(
        id=id,
        source=source,
        citation=citation,
        content=content,
        effective_from=_EFFECTIVE_FROM,
        effective_to=None,
        related_benefit_codes=related_benefit_codes,
    )


LEGAL_FRAGMENTS: list[LegalFragment] = [
    _fragment(
        "kp_art_180_par1",
        "Kodeks pracy",
        "art. 180 §1",
        "wymiar urlopu macierzyńskiego wg liczby dzieci urodzonych przy jednym porodzie",
        [MATERNITY_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_29_ust1_pkt1",
        "ustawa zasiłkowa",
        "art. 29 ust. 1 pkt 1",
        "prawo do zasiłku macierzyńskiego",
        [
            MATERNITY_LEAVE_BENEFIT_CODE,
            SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
            ADOPTION_LEAVE_BENEFIT_CODE,
        ],
    ),
    _fragment(
        "uz_art_31_ust1",
        "ustawa zasiłkowa",
        "art. 31 ust. 1",
        "wysokość zasiłku macierzyńskiego - 100% podstawy wymiaru",
        [
            MATERNITY_LEAVE_BENEFIT_CODE,
            ALTERNATIVE_BENEFIT_CODE,
            SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
            ADOPTION_LEAVE_BENEFIT_CODE,
        ],
    ),
    _fragment(
        "uz_art_30",
        "ustawa zasiłkowa",
        "art. 30",
        "zasiłek w wysokości zasiłku macierzyńskiego po ustaniu ubezpieczenia w ciąży",
        [MATERNITY_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_30_ust3",
        "ustawa zasiłkowa",
        "art. 30 ust. 3",
        "zasiłek w wysokości zasiłku macierzyńskiego do dnia porodu, gdy ubezpieczenie "
        "ustało wskutek śmierci/upadłości/likwidacji pracodawcy",
        [ALTERNATIVE_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_2a",
        "ustawa zasiłkowa",
        "art. 2a",
        "wyłączenie prawa do zasiłku z powodu zadłużenia składkowego (dotyczy osób "
        "prowadzących pozarolniczą działalność, powyżej progu liczonego od "
        "minimalnego wynagrodzenia)",
        [
            MATERNITY_LEAVE_BENEFIT_CODE,
            SICKNESS_DURING_PREGNANCY_BENEFIT_CODE,
            REHABILITATION_BENEFIT_CODE,
            SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
            ADOPTION_LEAVE_BENEFIT_CODE,
        ],
    ),
    _fragment(
        "kp_urlop_ojcowski_wymiar",
        "Kodeks pracy",
        "urlop ojcowski - wymiar",
        "2 tygodnie urlopu ojcowskiego, wykorzystywane jednorazowo albo w nie więcej "
        "niż dwóch częściach, z których żadna nie może być krótsza niż tydzień",
        [PATERNITY_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "kp_urlop_ojcowski_termin",
        "Kodeks pracy",
        "urlop ojcowski - termin",
        "prawo do urlopu ojcowskiego wygasa z ukończeniem przez dziecko 12. miesiąca życia",
        [PATERNITY_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "kp_art_1821a_par1_2",
        "Kodeks pracy",
        "art. 1821a § 1-2",
        "urlop rodzicielski w wymiarze 41 (jedno dziecko) albo 43 tygodni (więcej "
        "dzieci przy jednym porodzie), wydłużony do 65/67 tygodni przy zaświadczeniu "
        "'Za życiem'",
        [PARENTAL_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "kp_art_1821a_par4",
        "Kodeks pracy",
        "art. 1821a § 4",
        "9 tygodni z puli urlopu rodzicielskiego jest nieprzenoszalne - przysługuje "
        "wyłącznie drugiemu rodzicowi i przepada, jeśli z niego nie skorzysta",
        [PARENTAL_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_31_ust2",
        "ustawa zasiłkowa",
        "art. 31 ust. 2",
        "standardowa stawka zasiłku za okres urlopu rodzicielskiego - 70% podstawy wymiaru",
        [PARENTAL_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_30a_art31_ust3",
        "ustawa zasiłkowa",
        "art. 30a i art. 31 ust. 3",
        "podwyższona, łączna stawka 81,5% (liczona razem z zasiłkiem macierzyńskim), "
        "pod warunkiem złożenia wniosku o udzielenie urlopu w pełnym wymiarze w "
        "ciągu 21 dni po porodzie",
        [PARENTAL_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_31_ust3f",
        "ustawa zasiłkowa",
        "art. 31 ust. 3f",
        "9 nieprzenoszalnych tygodni drugiego rodzica jest zawsze płatne 70%, "
        "niezależnie od tego, czy pierwszy rodzic wybrał stawkę 81,5%",
        [PARENTAL_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "kp_art_1821f",
        "Kodeks pracy",
        "art. 1821f",
        "można łączyć korzystanie z urlopu rodzicielskiego z wykonywaniem pracy u "
        "pracodawcy udzielającego urlopu, w wymiarze nie wyższym niż 1/2 etatu - "
        "wtedy urlop proporcjonalnie się wydłuża",
        [PARENTAL_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_8_ust1",
        "ustawa zasiłkowa",
        "art. 8 ust. 1",
        "okres zasiłkowy wydłużony do 270 dni dla niezdolności do pracy przypadającej "
        "w okresie ciąży (zamiast standardowych 182 dni)",
        [SICKNESS_DURING_PREGNANCY_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_11_ust1",
        "ustawa zasiłkowa",
        "art. 11 ust. 1",
        "stawka 100% podstawy wymiaru dla niezdolności do pracy przypadającej w "
        "okresie ciąży (zamiast standardowych 80%)",
        [SICKNESS_DURING_PREGNANCY_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_4",
        "ustawa zasiłkowa",
        "art. 4",
        "okres wyczekiwania na prawo do zasiłku chorobowego: 30 dni przy ubezpieczeniu "
        "obowiązkowym, 90 dni przy ubezpieczeniu dobrowolnym",
        [SICKNESS_DURING_PREGNANCY_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_18_ust1",
        "ustawa zasiłkowa",
        "art. 18 ust. 1",
        "świadczenie rehabilitacyjne przysługuje po wyczerpaniu zasiłku chorobowego, "
        "gdy dalsze leczenie lub rehabilitacja lecznicza rokują odzyskanie zdolności do pracy",
        [REHABILITATION_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_18_ust2",
        "ustawa zasiłkowa",
        "art. 18 ust. 2",
        "stawka świadczenia rehabilitacyjnego: 90% podstawy wymiaru przez pierwsze 3 "
        "miesiące, 75% przez pozostały okres, 100% w okresie ciąży",
        [REHABILITATION_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_18_ust3",
        "ustawa zasiłkowa",
        "art. 18 ust. 3",
        "maksymalny okres pobierania świadczenia rehabilitacyjnego to 12 miesięcy",
        [REHABILITATION_BENEFIT_CODE],
    ),
    _fragment(
        "uz_art_18_ust7",
        "ustawa zasiłkowa",
        "art. 18 ust. 7",
        "świadczenie rehabilitacyjne nie przysługuje osobie uprawnionej do emerytury "
        "lub renty, zasiłku dla bezrobotnych, świadczenia przedemerytalnego, "
        "rodzicielskiego świadczenia uzupełniającego, nauczycielskiego świadczenia "
        "kompensacyjnego ani urlopu dla poratowania zdrowia",
        [REHABILITATION_BENEFIT_CODE],
    ),
    _fragment(
        "kp_art_1802_par1_3",
        "Kodeks pracy",
        "art. 1802 §1 i §3",
        "uzupełniający urlop macierzyński: 1 tydzień urlopu za każdy tydzień "
        "hospitalizacji dziecka po porodzie, liczony do 15. tygodnia po porodzie przy "
        "urodzeniu przed 28. tygodniem ciąży lub masie urodzeniowej ≤1000g, albo do "
        "8. tygodnia po porodzie w pozostałych kwalifikujących przypadkach",
        [SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "kp_art_1802_par4",
        "Kodeks pracy",
        "art. 1802 §4",
        "wniosek o uzupełniający urlop macierzyński składa się najpóźniej 21 dni "
        "przed zakończeniem (podstawowego) urlopu macierzyńskiego",
        [SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "kp_art_183_par1",
        "Kodeks pracy",
        "art. 183 §1",
        "urlop na warunkach urlopu macierzyńskiego przysługuje przy przysposobieniu "
        "dziecka do 14. roku życia oraz przyjęciu dziecka do rodziny zastępczej (do "
        "7. roku życia, albo do 10. roku życia przy odroczeniu obowiązku szkolnego)",
        [ADOPTION_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "kp_art_183_par1_1",
        "Kodeks pracy",
        "art. 183 §1(1)",
        "rodzina zastępcza zawodowa jest wyłączona z prawa do urlopu na warunkach "
        "urlopu macierzyńskiego",
        [ADOPTION_LEAVE_BENEFIT_CODE],
    ),
    _fragment(
        "poradnik_zus_stillbirth",
        "Poradnik ZUS 2026",
        "zasiłek pogrzebowy w razie martwego urodzenia dziecka",
        "ryczałt 7 000 zł, wniosek na formularzu Z-12, termin 12 miesięcy od dnia pochówku",
        [STILLBIRTH_FUNERAL_BENEFIT_CODE],
    ),
]
