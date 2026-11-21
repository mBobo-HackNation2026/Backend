"""Czysta logika oceny uprawnień do zasiłku macierzyńskiego za okres urlopu macierzyńskiego.

Brak zależności od bazy danych czy HTTP - funkcja przyjmuje gotową wersję reguły
(``BenefitRuleVersion``) oraz dane wniosku i zwraca ustrukturyzowany wynik oceny.
"""

from decimal import Decimal

from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.schemas import (
    BenefitPlan,
    EligibilityResult,
    EligibilityStatus,
    EmploymentEndedReason,
    InsuranceTitle,
    MaternityLeaveEligibilityRequest,
    PossibleSolution,
    RequiredDocument,
    SolutionType,
)
from app.rules.seed import (
    MATERNITY_LEAVE_BENEFIT_CODE as BENEFIT_CODE,
)
from app.rules.seed import (
    MATERNITY_LEAVE_BENEFIT_NAME as BENEFIT_NAME,
)

_SELF_EMPLOYED_LIKE_TITLES = {InsuranceTitle.dzialalnosc_gospodarcza}


def _weeks_for_children_count(weeks_by_child_count: dict, children_count: int) -> int:
    key = str(children_count) if children_count < 5 else "5+"
    return weeks_by_child_count[key]


def _document_applies(doc: dict, is_self_employed: bool) -> bool:
    """Whether a seed-data required-document entry applies to this request.

    ``applies_to`` is an internal seed-data-only tag (never exposed on the public
    ``RequiredDocument`` schema): ``None``/missing means "always", "standard" means
    non-self-employed titles (employer issues Z-3). Self-employed-like titles get no
    "self_employed"-tagged document today (see ``app/rules/seed.py`` for why), but the
    tag is kept generic so a future rule version can add one without an engine change.
    """
    applies_to = doc.get("applies_to")
    if applies_to is None:
        return True
    if applies_to == "self_employed":
        return is_self_employed
    if applies_to == "standard":
        return not is_self_employed
    return True


def evaluate_maternity_leave_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    met_conditions: list[str] = []
    unmet_conditions: list[str] = []
    missing_data: list[str] = []
    solutions: list[PossibleSolution] = []

    if request.insured_at_birth is None:
        missing_data.append("status ubezpieczenia chorobowego w dniu porodu")
    elif request.insured_at_birth:
        met_conditions.append(
            "ubezpieczenie chorobowe w dniu porodu (ustawa zasiłkowa art. 29 ust. 1 pkt 1)"
        )
    else:
        unmet_conditions.append("brak ubezpieczenia chorobowego w dniu porodu")
        if (
            request.employment_ended_reason
            == EmploymentEndedReason.upadlosc_likwidacja_smierc_pracodawcy
        ):
            solutions.append(
                PossibleSolution(
                    type=SolutionType.alternative_benefit,
                    description=(
                        "Zasiłek w wysokości zasiłku macierzyńskiego (100% podstawy wymiaru, do "
                        "dnia porodu) - przysługuje, gdy ubezpieczenie ustało w okresie ciąży "
                        "wskutek upadłości, likwidacji lub śmierci pracodawcy i nie zapewniono "
                        "innego zatrudnienia."
                    ),
                    legal_basis="ustawa zasiłkowa art. 30 ust. 1 pkt 1 i ust. 3",
                )
            )
        elif (
            request.employment_ended_reason
            == EmploymentEndedReason.naruszenie_prawa_wyrokiem_sadu
        ):
            solutions.append(
                PossibleSolution(
                    type=SolutionType.alternative_benefit,
                    description=(
                        "Zasiłek w wysokości zasiłku macierzyńskiego - przysługuje, gdy "
                        "rozwiązanie umowy w okresie ciąży naruszało przepisy prawa, co zostało "
                        "potwierdzone prawomocnym wyrokiem sądu."
                    ),
                    legal_basis="ustawa zasiłkowa art. 30 ust. 1 pkt 2",
                )
            )
        else:
            solutions.append(
                PossibleSolution(
                    type=SolutionType.limitation,
                    description=(
                        "Bez ubezpieczenia chorobowego w dniu porodu i bez okoliczności "
                        "przewidzianych w art. 30 ustawy zasiłkowej nie ma podstawy do tego "
                        "świadczenia z tego tytułu. Sprawdź, czy drugi rodzic ma niezależne "
                        "uprawnienie (np. urlop ojcowski)."
                    ),
                )
            )

    if request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES:
        if request.debt_amount_zl is None:
            missing_data.append(
                "informacja o zadłużeniu składkowym na dzień powstania prawa do zasiłku"
            )
        else:
            threshold = (
                rule.min_wage_reference_zl * rule.debt_threshold_percent_of_min_wage / Decimal(100)
            )
            if request.debt_amount_zl > threshold:
                unmet_conditions.append(
                    f"zadłużenie składkowe ({request.debt_amount_zl} zł) przekracza "
                    f"{rule.debt_threshold_percent_of_min_wage}% minimalnego wynagrodzenia "
                    f"({threshold} zł) - ustawa zasiłkowa art. 2a"
                )
                solutions.append(
                    PossibleSolution(
                        type=SolutionType.corrective_action,
                        description=(
                            "Spłać zadłużenie składkowe w całości - prawo do zasiłku zostanie "
                            "przywrócone, o ile spłata nastąpi w ciągu 6 miesięcy od dnia "
                            "powstania prawa do świadczenia."
                        ),
                        legal_basis="ustawa zasiłkowa art. 2a ust. 2",
                    )
                )
            else:
                met_conditions.append(
                    "brak zadłużenia składkowego przekraczającego próg (ustawa zasiłkowa art. 2a)"
                )

    has_alternative = any(s.type == SolutionType.alternative_benefit for s in solutions)

    if missing_data or (unmet_conditions and has_alternative):
        status = EligibilityStatus.requires_verification
    elif unmet_conditions:
        status = EligibilityStatus.not_eligible
    else:
        status = EligibilityStatus.likely_eligible

    warnings: list[str] = []
    if request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES:
        warnings.append(
            "Osoby prowadzące pozarolniczą działalność gospodarczą składały dotąd "
            "zaświadczenie Z-3b, które zniesiono 2026-10-24 bez oficjalnie "
            "potwierdzonego zastąpienia w dostępnych źródłach - sprawdź aktualny "
            "formularz ZAM/eZUS przed złożeniem wniosku."
        )

    plan = None
    # Only populate the plan when the *standard* path is still viable: either
    # everything is confirmed (likely_eligible), or nothing has been confirmed as
    # failed yet and we're just missing data (requires_verification with no
    # unmet_conditions). Once a standard condition is confirmed unmet - whether
    # that lands on not_eligible, or on requires_verification because an
    # alternative path (e.g. art. 30) exists, or because unrelated missing data
    # happens to bump the status - the standard plan no longer applies and must
    # stay None. A confirmed alternative path has no BenefitRuleVersion of its own
    # yet, so possible_solutions is the only place it is described for now.
    is_standard_path_open = status == EligibilityStatus.likely_eligible or (
        status == EligibilityStatus.requires_verification and not unmet_conditions
    )
    if is_standard_path_open:
        weeks = _weeks_for_children_count(rule.weeks_by_child_count, request.children_count)
        is_self_employed = request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES
        required_documents = [
            RequiredDocument(code=doc["code"], name=doc["name"], when=doc["when"])
            for doc in rule.required_documents
            if _document_applies(doc, is_self_employed)
        ]
        plan = BenefitPlan(
            weeks=weeks,
            rate_percentage=rule.rate_percentage,
            institution=(
                "Pracodawca (jeśli zgłasza powyżej 20 ubezpieczonych do ubezpieczenia "
                "chorobowego) albo ZUS"
            ),
            required_documents=required_documents,
            deadlines=[
                "Wniosek o urlop macierzyński - przed rozpoczęciem korzystania z urlopu (lub "
                "łącznie z wnioskiem o urlop rodzicielski)",
            ],
            legal_basis=list(rule.legal_basis),
        )

    return EligibilityResult(
        benefit_code=BENEFIT_CODE,
        benefit_name=BENEFIT_NAME,
        status=status,
        met_conditions=met_conditions,
        unmet_conditions=unmet_conditions,
        missing_data=missing_data,
        possible_solutions=solutions,
        plan=plan,
        rules_version=rule.version,
        warnings=warnings,
    )
