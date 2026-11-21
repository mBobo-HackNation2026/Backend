"""Dane startowe dla silnika uprawnień - jedno źródło prawdy dla stawek
i okresów, do czasu aż panel admina (Faza 8) nie przejmie ich edycji.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType

MATERNITY_LEAVE_BENEFIT_CODE = "zasilek_macierzynski_urlop_macierzynski"
MATERNITY_LEAVE_BENEFIT_NAME = "Zasiłek macierzyński za okres urlopu macierzyńskiego"
ALTERNATIVE_BENEFIT_CODE = "zasilek_w_wysokosci_zasilku_macierzynskiego"
ALTERNATIVE_BENEFIT_NAME = (
    "Zasiłek w wysokości zasiłku macierzyńskiego (po ustaniu ubezpieczenia w ciąży)"
)
PATERNITY_LEAVE_BENEFIT_CODE = "urlop_ojcowski"
PATERNITY_LEAVE_BENEFIT_NAME = "Zasiłek macierzyński za okres urlopu ojcowskiego"
REHABILITATION_BENEFIT_CODE = "swiadczenie_rehabilitacyjne"
REHABILITATION_BENEFIT_NAME = "Świadczenie rehabilitacyjne"

# --- STUB BENEFITS (Faza 2, not yet implemented) -----------------------------------
# These three benefit codes are registered and return a real HTTP 200 response so the
# frontend can build UI around a stable API shape, but their eligibility evaluators
# (app/eligibility/engine.py) are placeholders: they always return the same static
# `requires_verification` result regardless of input, with a `warnings` entry saying so
# explicitly. REAL per-request eligibility logic for these three is tracked as outstanding
# work - see project memory `project-ebobo-stub-benefits-debt` - and must be implemented
# (with the usual TDD + review process) before these are anything more than a UI
# placeholder. Do not remove the "TYMCZASOWA ODPOWIEDŹ ZASTĘPCZA" warning without
# actually implementing the real logic first.
#
# urlop_rodzicielski (parental leave) and zasilek_chorobowy_w_ciazy (sickness during
# pregnancy) USED to be in this list but now have real evaluators and dedicated seed
# functions (_ensure_parental_leave_seeded / _ensure_sickness_during_pregnancy_seeded
# below) - see app/eligibility/engine.py.
SICKNESS_DURING_PREGNANCY_BENEFIT_CODE = "zasilek_chorobowy_w_ciazy"
SICKNESS_DURING_PREGNANCY_BENEFIT_NAME = "Zasiłek chorobowy w ciąży"
SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE = "uzupelniajacy_urlop_macierzynski"
SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_NAME = (
    "Zasiłek za okres uzupełniającego urlopu macierzyńskiego"
)
PARENTAL_LEAVE_BENEFIT_CODE = "urlop_rodzicielski"
PARENTAL_LEAVE_BENEFIT_NAME = "Zasiłek macierzyński za okres urlopu rodzicielskiego"
ADOPTION_LEAVE_BENEFIT_CODE = "urlop_na_warunkach_urlopu_macierzynskiego"
ADOPTION_LEAVE_BENEFIT_NAME = "Zasiłek za okres urlopu na warunkach urlopu macierzyńskiego"
STILLBIRTH_FUNERAL_BENEFIT_CODE = "zasilek_pogrzebowy_martwe_urodzenie"
STILLBIRTH_FUNERAL_BENEFIT_NAME = "Zasiłek pogrzebowy w razie martwego urodzenia dziecka"


def ensure_seeded(db: Session) -> None:
    _ensure_maternity_leave_seeded(db)
    _ensure_alternative_benefit_seeded(db)
    _ensure_paternity_leave_seeded(db)
    _ensure_sickness_during_pregnancy_seeded(db)
    _ensure_rehabilitation_benefit_seeded(db)
    _ensure_stub_benefit_seeded(
        db,
        code=SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
        name=SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_NAME,
        description=(
            "[PLACEHOLDER - logika oceny jeszcze niezaimplementowana] Docelowo: 100% "
            "podstawy wymiaru; 1 tydzień za każdy tydzień hospitalizacji dziecka, limit "
            "do 15. tygodnia po porodzie (urodzenie <28 tyg. ciąży lub masa ≤1000g) albo "
            "do 8. tygodnia po porodzie w pozostałych kwalifikujących przypadkach "
            "(Kodeks pracy art. 1802)."
        ),
    )
    _ensure_parental_leave_seeded(db)
    _ensure_stub_benefit_seeded(
        db,
        code=ADOPTION_LEAVE_BENEFIT_CODE,
        name=ADOPTION_LEAVE_BENEFIT_NAME,
        description=(
            "[PLACEHOLDER - logika oceny jeszcze niezaimplementowana] Docelowo: ta sama "
            "tabela 20/31/33/35/37 tygodni co zasiłek macierzyński, min. 9 tygodni, 100% "
            "podstawy; limity wieku: rodzina zastępcza do 7 lat dziecka (10 lat przy "
            "odroczeniu obowiązku szkolnego), wniosek o przysposobienie do 14 lat dziecka."
        ),
    )
    _ensure_stub_benefit_seeded(
        db,
        code=STILLBIRTH_FUNERAL_BENEFIT_CODE,
        name=STILLBIRTH_FUNERAL_BENEFIT_NAME,
        description=(
            "[PLACEHOLDER - logika oceny jeszcze niezaimplementowana] Docelowo: "
            "świadczenie ryczałtowe 7 000 zł niezależnie od faktycznych kosztów (nie "
            "procent podstawy wymiaru), wniosek na formularzu Z-12 w ciągu 12 miesięcy "
            "od pochówku (Poradnik ZUS 2026, s.35-36) - ten model danych (rate_percentage "
            "+ weeks) nie pasuje do świadczenia kwotowego i będzie wymagał rozszerzenia."
        ),
    )


def _ensure_maternity_leave_seeded(db: Session) -> None:
    benefit_type = db.query(BenefitType).filter_by(code=MATERNITY_LEAVE_BENEFIT_CODE).one_or_none()
    if benefit_type is None:
        benefit_type = BenefitType(
            code=MATERNITY_LEAVE_BENEFIT_CODE,
            name=MATERNITY_LEAVE_BENEFIT_NAME,
            description=(
                "Świadczenie za okres urlopu macierzyńskiego po urodzeniu dziecka, wypłacane "
                "ubezpieczonej matce (lub ubezpieczonemu ojcu w szczególnych przypadkach "
                "przewidzianych w Kodeksie pracy)."
            ),
        )
        db.add(benefit_type)
        db.flush()

    existing_rule = (
        db.query(BenefitRuleVersion)
        .filter_by(benefit_type_id=benefit_type.id, is_current=True)
        .one_or_none()
    )
    if existing_rule is not None:
        return

    rule = BenefitRuleVersion(
        benefit_type_id=benefit_type.id,
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count={"1": 20, "2": 31, "3": 33, "4": 35, "5+": 37},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution=(
            "Pracodawca (jeśli zgłasza powyżej 20 ubezpieczonych do ubezpieczenia "
            "chorobowego) albo ZUS"
        ),
        deadlines=[
            "Wniosek o urlop macierzyński - przed rozpoczęciem korzystania z urlopu (lub "
            "łącznie z wnioskiem o urlop rodzicielski)",
        ],
        legal_basis=[
            "Kodeks pracy art. 180 §1 (wymiar urlopu macierzyńskiego wg liczby dzieci)",
            "ustawa zasiłkowa art. 29 ust. 1 pkt 1 (prawo do zasiłku macierzyńskiego)",
            "ustawa zasiłkowa art. 31 ust. 1 (wysokość zasiłku - 100% podstawy wymiaru)",
            "ustawa zasiłkowa art. 30 (zasiłek w wysokości zasiłku macierzyńskiego po ustaniu "
            "ubezpieczenia w ciąży)",
            "ustawa zasiłkowa art. 2a (wyłączenie prawa z powodu zadłużenia składkowego)",
        ],
        # "applies_to" is an internal seed-data-only tag consumed by the eligibility
        # engine to pick the right document set given request.insurance_title; it is
        # never exposed on the public RequiredDocument schema. None/missing = always
        # required. "standard" = non-self-employed titles (umowa_o_prace, unknown) -
        # the employer issues Z-3. Self-employed-like titles (dzialalnosc_gospodarcza)
        # get NO zaświadczenie płatnika document here: they historically filed Z-3b,
        # which was abolished 2026-10-24 with no replacement documented in any source
        # material we have (see project memory project-ebobo-legal-rules, point 3) -
        # per the project's "never fabricate" rule we don't invent one. The engine
        # adds a `warnings` entry instead of guessing a document code.
        required_documents=[
            {
                "code": "wniosek_urlop_macierzynski",
                "name": (
                    "Wniosek o udzielenie urlopu macierzyńskiego (do pracodawcy) albo wniosek "
                    "ZAM (do ZUS)"
                ),
                "when": (
                    "przed rozpoczęciem korzystania z urlopu, ewentualnie łącznie z wnioskiem "
                    "o urlop rodzicielski"
                ),
                "applies_to": None,
            },
            {
                "code": "zaswiadczenie_z3",
                "name": "Zaświadczenie płatnika składek Z-3",
                "when": "gdy płatnikiem zasiłku jest ZUS, a nie pracodawca",
                "applies_to": "standard",
            },
            {
                "code": "akt_urodzenia",
                "name": "Skrócony odpis aktu urodzenia dziecka",
                "when": (
                    "po porodzie (niewymagany, jeśli płatnikiem jest ZUS - dane pozyskiwane są "
                    "z rejestru stanu cywilnego)"
                ),
                "applies_to": None,
            },
        ],
    )
    db.add(rule)
    db.commit()


def _ensure_alternative_benefit_seeded(db: Session) -> None:
    benefit_type = db.query(BenefitType).filter_by(code=ALTERNATIVE_BENEFIT_CODE).one_or_none()
    if benefit_type is None:
        benefit_type = BenefitType(
            code=ALTERNATIVE_BENEFIT_CODE,
            name=ALTERNATIVE_BENEFIT_NAME,
            description=(
                "Świadczenie przysługujące ubezpieczonej będącej pracownicą, której umowa o "
                "pracę wygasła wskutek śmierci pracodawcy, albo którą rozwiązano w okresie "
                "ciąży z powodu ogłoszenia upadłości lub likwidacji pracodawcy, o ile nie "
                "zapewniono jej innego zatrudnienia (ustawa zasiłkowa art. 30 ust. 3). Nie "
                "obejmuje rozwiązania umowy z naruszeniem przepisów prawa stwierdzonym "
                "prawomocnym orzeczeniem sądu - ten przypadek uprawnia wyłącznie do zwykłego "
                "zasiłku macierzyńskiego (art. 30 ust. 1 pkt 2), nie do tego świadczenia."
            ),
        )
        db.add(benefit_type)
        db.flush()

    existing_rule = (
        db.query(BenefitRuleVersion)
        .filter_by(benefit_type_id=benefit_type.id, is_current=True)
        .one_or_none()
    )
    if existing_rule is not None:
        return

    rule = BenefitRuleVersion(
        benefit_type_id=benefit_type.id,
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count=None,
        duration_until_birth=True,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        legal_basis=[
            "ustawa zasiłkowa art. 30 ust. 3 (zasiłek w wysokości zasiłku macierzyńskiego do "
            "dnia porodu, po ustaniu ubezpieczenia wskutek śmierci/upadłości/likwidacji "
            "pracodawcy)",
            "ustawa zasiłkowa art. 31 ust. 1 (wysokość zasiłku - 100% podstawy wymiaru)",
        ],
        deadlines=[
            "Wniosek ZAM - jak najszybciej po ustaniu ubezpieczenia. Roszczenie o zasiłek "
            "przedawnia się po upływie 6 miesięcy od ostatniego dnia okresu, za który zasiłek "
            "przysługuje (ustawa zasiłkowa art. 67 ust. 1).",
        ],
        # This benefit has no employer by definition (the employer relationship already
        # ended), so there is no "applies_to": "standard" Z-3 document here - just the
        # wniosek and a document confirming the reason insurance ended. See
        # app/eligibility/engine.py's evaluate_alternative_maternity_benefit_eligibility for
        # why no debt-threshold/self-employed logic applies to this benefit either.
        required_documents=[
            {
                "code": "wniosek_zam",
                "name": "Wniosek ZAM o zasiłek macierzyński",
                "when": "po ustaniu ubezpieczenia, przed porodem lub niezwłocznie po porodzie",
                "applies_to": None,
            },
            {
                "code": "dokument_potwierdzajacy_przyczyne_ustania_ubezpieczenia",
                "name": (
                    "Dokument potwierdzający przyczynę i okoliczności ustania zatrudnienia "
                    "(np. świadectwo pracy ze wskazaniem przyczyny, dokumenty z postępowania "
                    "upadłościowego/likwidacyjnego) oraz potwierdzenie braku innego "
                    "zatrudnienia"
                ),
                "when": "wraz z wnioskiem",
                "applies_to": None,
            },
            {
                "code": "akt_urodzenia",
                "name": "Skrócony odpis aktu urodzenia dziecka",
                "when": (
                    "po porodzie (niewymagany, jeśli dane pozyskiwane są z rejestru stanu "
                    "cywilnego)"
                ),
                "applies_to": None,
            },
        ],
    )
    db.add(rule)
    db.commit()


def _ensure_paternity_leave_seeded(db: Session) -> None:
    benefit_type = db.query(BenefitType).filter_by(code=PATERNITY_LEAVE_BENEFIT_CODE).one_or_none()
    if benefit_type is None:
        benefit_type = BenefitType(
            code=PATERNITY_LEAVE_BENEFIT_CODE,
            name=PATERNITY_LEAVE_BENEFIT_NAME,
            description=(
                "Świadczenie za okres urlopu ojcowskiego - 2 tygodnie, do wykorzystania "
                "jednorazowo lub w maksymalnie dwóch częściach, nie dłużej niż do "
                "ukończenia przez dziecko 12. miesiąca życia (Kodeks pracy)."
            ),
        )
        db.add(benefit_type)
        db.flush()

    existing_rule = (
        db.query(BenefitRuleVersion)
        .filter_by(benefit_type_id=benefit_type.id, is_current=True)
        .one_or_none()
    )
    if existing_rule is not None:
        return

    rule = BenefitRuleVersion(
        benefit_type_id=benefit_type.id,
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        rate_percentage=Decimal("100.00"),
        # Urlop ojcowski is a flat 2 weeks regardless of how many children were born at
        # once (unlike urlop macierzyński, which scales with children_count) - every key
        # maps to the same figure.
        weeks_by_child_count={"1": 2, "2": 2, "3": 2, "4": 2, "5+": 2},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution=(
            "Pracodawca (jeśli zgłasza powyżej 20 ubezpieczonych do ubezpieczenia "
            "chorobowego) albo ZUS"
        ),
        legal_basis=[
            "Kodeks pracy (urlop ojcowski - 2 tygodnie, wykorzystywane jednorazowo albo "
            "w nie więcej niż dwóch częściach, nie krótszych niż tydzień każda)",
            "Kodeks pracy (termin: do ukończenia przez dziecko 12. miesiąca życia)",
        ],
        deadlines=[
            "Wniosek o urlop ojcowski - nie później niż do ukończenia przez dziecko 12. "
            "miesiąca życia; po tym terminie prawo wygasa.",
        ],
        required_documents=[
            {
                "code": "wniosek_urlop_ojcowski",
                "name": "Wniosek o udzielenie urlopu ojcowskiego",
                "when": "przed rozpoczęciem korzystania z urlopu",
                "applies_to": None,
            },
            {
                "code": "akt_urodzenia",
                "name": "Skrócony odpis aktu urodzenia dziecka",
                "when": "po porodzie",
                "applies_to": None,
            },
        ],
    )
    db.add(rule)
    db.commit()


def _ensure_parental_leave_seeded(db: Session) -> None:
    benefit_type = db.query(BenefitType).filter_by(code=PARENTAL_LEAVE_BENEFIT_CODE).one_or_none()
    if benefit_type is None:
        benefit_type = BenefitType(
            code=PARENTAL_LEAVE_BENEFIT_CODE,
            name=PARENTAL_LEAVE_BENEFIT_NAME,
            description=(
                "Świadczenie za okres urlopu rodzicielskiego, przysługujące ubezpieczonemu "
                "rodzicowi (matce lub ojcu) po wykorzystaniu urlopu macierzyńskiego. 9 "
                "tygodni z puli jest nieprzenoszalne na rzecz drugiego rodzica. Wymiar "
                "wydłuża się ze standardowych 41/43 do 65/67 tygodni, jeśli dziecko ma "
                "zaświadczenie 'Za życiem'."
            ),
        )
        db.add(benefit_type)
        db.flush()

    existing_rule = (
        db.query(BenefitRuleVersion)
        .filter_by(benefit_type_id=benefit_type.id, is_current=True)
        .one_or_none()
    )
    if existing_rule is not None:
        return

    rule = BenefitRuleVersion(
        benefit_type_id=benefit_type.id,
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        # Standardowa stawka 70%; silnik (evaluate_parental_leave_eligibility) podnosi
        # ją do 81,5% dynamicznie, gdy wniosek o pełny wymiar złożono w ciągu 21 dni po
        # porodzie (ustawa zasiłkowa art. 31 ust. 3g) - to jedyny przypadek w projekcie,
        # gdzie stawka nie jest stałą wartością z reguły.
        rate_percentage=Decimal("70.00"),
        weeks_by_child_count={"1": 41, "2": 43, "3": 43, "4": 43, "5+": 43},
        weeks_by_child_count_za_zyciem={"1": 65, "2": 67, "3": 67, "4": 67, "5+": 67},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution=(
            "Pracodawca (jeśli zgłasza powyżej 20 ubezpieczonych do ubezpieczenia "
            "chorobowego) albo ZUS"
        ),
        deadlines=[
            "Wniosek o pełny wymiar urlopu rodzicielskiego - najpóźniej w ciągu 21 dni po "
            "porodzie, aby uzyskać stawkę 81,5% łącznie z zasiłkiem macierzyńskim; poza "
            "tym terminem przysługuje stawka 70%.",
        ],
        legal_basis=[
            "Kodeks pracy art. 1821 i nast. (urlop rodzicielski - 41/43 tygodni, 65/67 "
            "tygodni z zaświadczeniem 'Za życiem')",
            "Kodeks pracy art. 1821a (9 tygodni z puli nieprzenoszalne na rzecz drugiego "
            "rodzica)",
            "ustawa zasiłkowa art. 31 ust. 3 (stawka 70%) oraz ust. 3g i ust. 4 (81,5% "
            "łącznie z macierzyńskim pod warunkiem wniosku o pełny wymiar w ciągu 21 dni)",
            "Kodeks pracy art. 1821f (łączenie urlopu rodzicielskiego z pracą w wymiarze "
            "nie wyższym niż 1/2 etatu, proporcjonalne wydłużenie urlopu)",
        ],
        required_documents=[
            {
                "code": "wniosek_urlop_rodzicielski",
                "name": (
                    "Wniosek o udzielenie urlopu rodzicielskiego (do pracodawcy) albo "
                    "wniosek ZAM (do ZUS)"
                ),
                "when": (
                    "przed rozpoczęciem korzystania z urlopu, ewentualnie łącznie z "
                    "wnioskiem o urlop macierzyński"
                ),
                "applies_to": None,
            },
            {
                "code": "zaswiadczenie_za_zyciem",
                "name": (
                    "Zaświadczenie 'Za życiem' potwierdzające ciężkie i nieodwracalne "
                    "upośledzenie albo nieuleczalną chorobę zagrażającą życiu dziecka"
                ),
                "when": "wraz z wnioskiem, jeśli dotyczy wydłużonego wymiaru urlopu",
                "applies_to": "za_zyciem",
            },
            {
                "code": "akt_urodzenia",
                "name": "Skrócony odpis aktu urodzenia dziecka",
                "when": (
                    "po porodzie (niewymagany, jeśli płatnikiem jest ZUS - dane pozyskiwane "
                    "są z rejestru stanu cywilnego)"
                ),
                "applies_to": None,
            },
        ],
    )
    db.add(rule)
    db.commit()


def _ensure_sickness_during_pregnancy_seeded(db: Session) -> None:
    benefit_type = (
        db.query(BenefitType).filter_by(code=SICKNESS_DURING_PREGNANCY_BENEFIT_CODE).one_or_none()
    )
    if benefit_type is None:
        benefit_type = BenefitType(
            code=SICKNESS_DURING_PREGNANCY_BENEFIT_CODE,
            name=SICKNESS_DURING_PREGNANCY_BENEFIT_NAME,
            description=(
                "Zasiłek chorobowy przysługujący ubezpieczonej, której niezdolność do "
                "pracy powstała w okresie ciąży - podwyższona stawka 100% podstawy "
                "wymiaru i wydłużony maksymalny okres 270 dni (w porównaniu do zwykłego "
                "zasiłku chorobowego: 80%, do 182 dni)."
            ),
        )
        db.add(benefit_type)
        db.flush()

    existing_rule = (
        db.query(BenefitRuleVersion)
        .filter_by(benefit_type_id=benefit_type.id, is_current=True)
        .one_or_none()
    )
    if existing_rule is not None:
        return

    rule = BenefitRuleVersion(
        benefit_type_id=benefit_type.id,
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count=None,
        duration_until_birth=False,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        deadlines=[
            "Wniosek o zasiłek chorobowy - niezwłocznie po otrzymaniu zaświadczenia "
            "lekarskiego (e-ZLA). Roszczenie przedawnia się po upływie 6 miesięcy od "
            "ostatniego dnia okresu, za który zasiłek przysługuje (ustawa zasiłkowa "
            "art. 67 ust. 1).",
        ],
        legal_basis=[
            "ustawa zasiłkowa art. 8 ust. 1 (270 dni dla niezdolności w okresie ciąży, "
            "zamiast standardowych 182 dni)",
            "ustawa zasiłkowa art. 11 ust. 1 (stawka 100% dla niezdolności w okresie "
            "ciąży, zamiast standardowych 80%)",
            "ustawa zasiłkowa art. 4 (okres wyczekiwania: 30 dni - ubezpieczenie "
            "obowiązkowe, 90 dni - dobrowolne)",
            "ustawa zasiłkowa art. 2a (wyłączenie prawa z powodu zadłużenia składkowego "
            "- dotyczy osób prowadzących pozarolniczą działalność)",
        ],
        required_documents=[
            {
                "code": "zaswiadczenie_lekarskie_ezla",
                "name": "Zaświadczenie lekarskie (e-ZLA)",
                "when": "wystawiane elektronicznie przez lekarza, nie składane osobno",
                "applies_to": None,
            },
            {
                "code": "zaswiadczenie_z3",
                "name": "Zaświadczenie płatnika składek Z-3",
                "when": "gdy płatnikiem zasiłku jest ZUS, a nie pracodawca",
                "applies_to": "standard",
            },
        ],
    )
    db.add(rule)
    db.commit()


def _ensure_rehabilitation_benefit_seeded(db: Session) -> None:
    benefit_type = db.query(BenefitType).filter_by(code=REHABILITATION_BENEFIT_CODE).one_or_none()
    if benefit_type is None:
        benefit_type = BenefitType(
            code=REHABILITATION_BENEFIT_CODE,
            name=REHABILITATION_BENEFIT_NAME,
            description=(
                "Świadczenie przysługujące ubezpieczonemu, który po wyczerpaniu zasiłku "
                "chorobowego jest nadal niezdolny do pracy, a dalsze leczenie lub "
                "rehabilitacja rokują odzyskanie zdolności do pracy. Stawka 90% przez "
                "pierwsze 3 miesiące, 75% przez pozostały okres, 100% w okresie ciąży; "
                "maksymalnie 12 miesięcy."
            ),
        )
        db.add(benefit_type)
        db.flush()

    existing_rule = (
        db.query(BenefitRuleVersion)
        .filter_by(benefit_type_id=benefit_type.id, is_current=True)
        .one_or_none()
    )
    if existing_rule is not None:
        return

    rule = BenefitRuleVersion(
        benefit_type_id=benefit_type.id,
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        # Stawka startowa (silnik dynamicznie ustawia 100%, jeśli wnioskodawca jest w
        # ciąży - evaluate_rehabilitation_benefit_eligibility w app/eligibility/engine.py).
        rate_percentage=Decimal("90.00"),
        weeks_by_child_count=None,
        duration_until_birth=False,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        deadlines=[
            "Wniosek o świadczenie rehabilitacyjne - przed upływem okresu pobierania "
            "zasiłku chorobowego, wraz z orzeczeniem lekarza orzecznika ZUS o rokowaniu "
            "odzyskania zdolności do pracy.",
        ],
        legal_basis=[
            "ustawa zasiłkowa art. 18 ust. 1 (świadczenie rehabilitacyjne po wyczerpaniu "
            "zasiłku chorobowego, gdy dalsze leczenie lub rehabilitacja rokują "
            "odzyskanie zdolności do pracy)",
            "ustawa zasiłkowa art. 18 ust. 2 (stawka 90% przez pierwsze 3 miesiące, 75% "
            "przez pozostały okres, 100% w okresie ciąży)",
            "ustawa zasiłkowa art. 18 ust. 3 (maksymalny okres 12 miesięcy)",
            "ustawa zasiłkowa art. 18 ust. 7 (wyłączenia: emerytura, renta, zasiłek dla "
            "bezrobotnych, świadczenie przedemerytalne, rodzicielskie świadczenie "
            "uzupełniające, nauczycielskie świadczenie kompensacyjne, urlop dla "
            "poratowania zdrowia)",
            "ustawa zasiłkowa art. 2a (wyłączenie prawa z powodu zadłużenia składkowego)",
        ],
        required_documents=[
            {
                "code": "wniosek_swiadczenie_rehabilitacyjne",
                "name": "Wniosek o świadczenie rehabilitacyjne",
                "when": "przed upływem okresu pobierania zasiłku chorobowego",
                "applies_to": None,
            },
            {
                "code": "zaswiadczenie_lekarza_orzecznika",
                "name": (
                    "Orzeczenie lekarza orzecznika ZUS o rokowaniu odzyskania zdolności "
                    "do pracy"
                ),
                "when": "wraz z wnioskiem",
                "applies_to": None,
            },
            {
                "code": "zaswiadczenie_z3",
                "name": "Zaświadczenie płatnika składek Z-3",
                "when": "gdy płatnikiem zasiłku jest ZUS, a nie pracodawca",
                "applies_to": "standard",
            },
        ],
    )
    db.add(rule)
    db.commit()


def _ensure_stub_benefit_seeded(db: Session, *, code: str, name: str, description: str) -> None:
    """Seeds a minimal, mostly-placeholder rule row for a benefit whose eligibility
    evaluator is itself a static placeholder (see the STUB BENEFITS note above). The
    numeric fields here are never actually read by the evaluator - they exist only
    because BenefitRuleVersion's columns are NOT NULL and get_current_rule needs a row
    to find, not because they're meaningful figures for this benefit yet.
    """
    benefit_type = db.query(BenefitType).filter_by(code=code).one_or_none()
    if benefit_type is None:
        benefit_type = BenefitType(code=code, name=name, description=description)
        db.add(benefit_type)
        db.flush()

    existing_rule = (
        db.query(BenefitRuleVersion)
        .filter_by(benefit_type_id=benefit_type.id, is_current=True)
        .one_or_none()
    )
    if existing_rule is not None:
        return

    rule = BenefitRuleVersion(
        benefit_type_id=benefit_type.id,
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        rate_percentage=Decimal("0.00"),
        weeks_by_child_count=None,
        duration_until_birth=False,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        legal_basis=[description],
        deadlines=[],
        required_documents=[],
    )
    db.add(rule)
    db.commit()
