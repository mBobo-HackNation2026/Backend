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


def ensure_seeded(db: Session) -> None:
    _ensure_maternity_leave_seeded(db)
    _ensure_alternative_benefit_seeded(db)


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
