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
    ADOPTION_LEAVE_BENEFIT_CODE,
    ADOPTION_LEAVE_BENEFIT_NAME,
    ALTERNATIVE_BENEFIT_CODE,
    ALTERNATIVE_BENEFIT_NAME,
    PARENTAL_LEAVE_BENEFIT_CODE,
    PARENTAL_LEAVE_BENEFIT_NAME,
    PATERNITY_LEAVE_BENEFIT_CODE,
    PATERNITY_LEAVE_BENEFIT_NAME,
    SICKNESS_DURING_PREGNANCY_BENEFIT_CODE,
    SICKNESS_DURING_PREGNANCY_BENEFIT_NAME,
    STILLBIRTH_FUNERAL_BENEFIT_CODE,
    STILLBIRTH_FUNERAL_BENEFIT_NAME,
    SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
    SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_NAME,
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


def _decide_status(
    missing_data: list[str], unmet_conditions: list[str], solutions: list[PossibleSolution]
) -> EligibilityStatus:
    has_alternative = any(s.type == SolutionType.alternative_benefit for s in solutions)
    if missing_data or (unmet_conditions and has_alternative):
        return EligibilityStatus.requires_verification
    if unmet_conditions:
        return EligibilityStatus.not_eligible
    return EligibilityStatus.likely_eligible


def _build_plan(rule: BenefitRuleVersion, request: MaternityLeaveEligibilityRequest) -> BenefitPlan:
    is_self_employed = request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES
    required_documents = [
        RequiredDocument(code=doc["code"], name=doc["name"], when=doc["when"])
        for doc in rule.required_documents
        if _document_applies(doc, is_self_employed)
    ]
    weeks = None
    duration_description = None
    if rule.duration_until_birth:
        duration_description = "do dnia porodu"
    else:
        weeks = _weeks_for_children_count(rule.weeks_by_child_count, request.children_count)
    return BenefitPlan(
        weeks=weeks,
        duration_description=duration_description,
        rate_percentage=rule.rate_percentage,
        institution=rule.institution,
        required_documents=required_documents,
        deadlines=list(rule.deadlines),
        legal_basis=list(rule.legal_basis),
    )


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
                    related_benefit_code=ALTERNATIVE_BENEFIT_CODE,
                )
            )
        elif (
            request.employment_ended_reason
            == EmploymentEndedReason.naruszenie_prawa_wyrokiem_sadu
        ):
            # Unlike the branch above, this reason has no related_benefit_code: art. 30
            # ust. 1 pkt 2 grants THIS SAME benefit (not the separate "do dnia porodu"
            # benefit under ust. 3, which explicitly only lists death/upadłość/likwidacja -
            # see evaluate_alternative_maternity_benefit_eligibility for that boundary).
            # KNOWN LIMITATION (deliberately deferred, not fixed by this branch): since art.
            # 30 ust. 1 pkt 2 arguably means the standard condition IS met via this
            # alternative legal basis, this should plausibly land in met_conditions rather
            # than unmet_conditions/SolutionType.alternative_benefit - that reclassification
            # is a separate future task, tracked in this plan's self-review checklist.
            solutions.append(
                PossibleSolution(
                    type=SolutionType.alternative_benefit,
                    description=(
                        "Rozwiązanie umowy w okresie ciąży z naruszeniem przepisów prawa, "
                        "stwierdzone prawomocnym orzeczeniem sądu, uprawnia do zwykłego "
                        "zasiłku macierzyńskiego za okres urlopu macierzyńskiego pomimo "
                        "ustania ubezpieczenia - to jest to samo świadczenie; sprawdź je "
                        "ponownie z potwierdzeniem tej okoliczności."
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

    status = _decide_status(missing_data, unmet_conditions, solutions)

    warnings: list[str] = []
    if request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES:
        warnings.append(
            "Osoby prowadzące pozarolniczą działalność gospodarczą składały dotąd "
            "zaświadczenie Z-3b, które zniesiono 2026-10-24 bez oficjalnie "
            "potwierdzonego zastąpienia w dostępnych źródłach - sprawdź aktualny "
            "formularz ZAM/eZUS przed złożeniem wniosku."
        )

    # Only populate the plan when the *standard* path is still viable: either
    # everything is confirmed (likely_eligible), or nothing has been confirmed as
    # failed yet and we're just missing data (requires_verification with no
    # unmet_conditions). Once a standard condition is confirmed unmet - whether
    # that lands on not_eligible, or on requires_verification because an
    # alternative path (e.g. art. 30) exists, or because unrelated missing data
    # happens to bump the status - the standard plan no longer applies and must
    # stay None.
    is_standard_path_open = status == EligibilityStatus.likely_eligible or (
        status == EligibilityStatus.requires_verification and not unmet_conditions
    )
    plan = _build_plan(rule, request) if is_standard_path_open else None

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


def evaluate_alternative_maternity_benefit_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    met_conditions: list[str] = []
    unmet_conditions: list[str] = []
    missing_data: list[str] = []
    solutions: list[PossibleSolution] = []
    warnings: list[str] = []

    if request.insured_at_birth is None:
        missing_data.append("status ubezpieczenia chorobowego w dniu porodu")
    elif request.insured_at_birth:
        unmet_conditions.append(
            "świadczenie dotyczy wyłącznie osób, których ubezpieczenie chorobowe ustało w "
            "okresie ciąży - wnioskodawczyni była ubezpieczona w dniu porodu"
        )
        solutions.append(
            PossibleSolution(
                type=SolutionType.alternative_benefit,
                description=(
                    "Wnioskodawczyni była ubezpieczona w dniu porodu, więc właściwym "
                    "świadczeniem jest zasiłek macierzyński za okres urlopu macierzyńskiego, "
                    "a nie to świadczenie alternatywne."
                ),
                legal_basis="ustawa zasiłkowa art. 29 ust. 1 pkt 1",
                related_benefit_code=BENEFIT_CODE,
            )
        )
    elif request.employment_ended_reason is None:
        missing_data.append("powód ustania ubezpieczenia chorobowego w okresie ciąży")
    elif request.employment_ended_reason == EmploymentEndedReason.naruszenie_prawa_wyrokiem_sadu:
        # art. 30 ust. 3 (this benefit) only lists death/upadłość/likwidacja pracodawcy as
        # triggers - NOT unlawful termination by court ruling. That reason instead grants the
        # *standard* benefit under art. 30 ust. 1 pkt 2 - point there, don't grant this one.
        unmet_conditions.append(
            "rozwiązanie umowy z naruszeniem przepisów prawa nie jest przesłanką tego "
            "świadczenia (ustawa zasiłkowa art. 30 ust. 3) - uprawnia wyłącznie do zwykłego "
            "zasiłku macierzyńskiego"
        )
        solutions.append(
            PossibleSolution(
                type=SolutionType.alternative_benefit,
                description=(
                    "Rozwiązanie umowy z naruszeniem przepisów prawa, stwierdzone "
                    "prawomocnym orzeczeniem sądu, uprawnia do zwykłego zasiłku "
                    "macierzyńskiego za okres urlopu macierzyńskiego (nie do tego "
                    "świadczenia) - sprawdź to świadczenie osobno."
                ),
                legal_basis="ustawa zasiłkowa art. 30 ust. 1 pkt 2",
                related_benefit_code=BENEFIT_CODE,
            )
        )
    else:
        met_conditions.append(
            "ubezpieczenie ustało w okresie ciąży wskutek śmierci, upadłości lub likwidacji "
            "pracodawcy (ustawa zasiłkowa art. 30 ust. 3)"
        )
        if request.other_employment_secured is None:
            missing_data.append(
                "informacja, czy zapewniono inne zatrudnienie po ustaniu poprzedniego "
                "(ustawa zasiłkowa art. 30 ust. 3)"
            )
        elif request.other_employment_secured:
            unmet_conditions.append(
                "zapewniono inne zatrudnienie po ustaniu poprzedniego - świadczenie "
                "przysługuje tylko, gdy nie zapewniono innego zatrudnienia (ustawa "
                "zasiłkowa art. 30 ust. 3)"
            )
        else:
            met_conditions.append(
                "nie zapewniono innego zatrudnienia po ustaniu poprzedniego (ustawa "
                "zasiłkowa art. 30 ust. 3)"
            )

    status = _decide_status(missing_data, unmet_conditions, solutions)

    # Unlike the standard evaluator, missing_data alone must NOT surface a plan here:
    # every missing fact checked above (insured_at_birth, employment_ended_reason,
    # other_employment_secured) is itself a trigger condition for this benefit, not an
    # independent/orthogonal field - so only a confirmed likely_eligible result (every
    # condition checked and satisfied) warrants a plan.
    plan = _build_plan(rule, request) if status == EligibilityStatus.likely_eligible else None

    return EligibilityResult(
        benefit_code=ALTERNATIVE_BENEFIT_CODE,
        benefit_name=ALTERNATIVE_BENEFIT_NAME,
        status=status,
        met_conditions=met_conditions,
        unmet_conditions=unmet_conditions,
        missing_data=missing_data,
        possible_solutions=solutions,
        plan=plan,
        rules_version=rule.version,
        warnings=warnings,
    )


_PATERNITY_LEAVE_DEADLINE_MONTHS = 12


def evaluate_paternity_leave_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    met_conditions: list[str] = []
    unmet_conditions: list[str] = []
    missing_data: list[str] = []
    solutions: list[PossibleSolution] = []

    if request.father_insured is None:
        missing_data.append("status ubezpieczenia chorobowego ojca dziecka")
    elif request.father_insured:
        met_conditions.append("ojciec dziecka objęty ubezpieczeniem chorobowym")
    else:
        unmet_conditions.append("ojciec dziecka nie jest objęty ubezpieczeniem chorobowym")
        solutions.append(
            PossibleSolution(
                type=SolutionType.limitation,
                description=(
                    "Bez ubezpieczenia chorobowego ojcu nie przysługuje urlop ojcowski. "
                    "Sprawdź, czy drugi rodzic ma niezależne uprawnienia (np. urlop "
                    "rodzicielski)."
                ),
            )
        )

    if request.child_age_months is None:
        missing_data.append("wiek dziecka w miesiącach")
    elif request.child_age_months >= _PATERNITY_LEAVE_DEADLINE_MONTHS:
        unmet_conditions.append(
            f"dziecko ukończyło {_PATERNITY_LEAVE_DEADLINE_MONTHS}. miesiąc życia - prawo "
            "do urlopu ojcowskiego wygasło (Kodeks pracy)"
        )
    else:
        met_conditions.append(
            f"dziecko nie ukończyło jeszcze {_PATERNITY_LEAVE_DEADLINE_MONTHS}. miesiąca "
            "życia - termin na skorzystanie z urlopu ojcowskiego nie minął"
        )

    status = _decide_status(missing_data, unmet_conditions, solutions)
    plan = _build_plan(rule, request) if status == EligibilityStatus.likely_eligible else None

    return EligibilityResult(
        benefit_code=PATERNITY_LEAVE_BENEFIT_CODE,
        benefit_name=PATERNITY_LEAVE_BENEFIT_NAME,
        status=status,
        met_conditions=met_conditions,
        unmet_conditions=unmet_conditions,
        missing_data=missing_data,
        possible_solutions=solutions,
        plan=plan,
        rules_version=rule.version,
        warnings=[],
    )


# --- STUB BENEFITS (Faza 2, not yet implemented) -----------------------------------
# These evaluators always return the same static result regardless of input. They
# exist so the frontend can build UI against a stable API shape before the real
# eligibility logic is written (explicit product decision - see project memory
# `project-ebobo-stub-benefits-debt`). Each one's `warnings` entry says so plainly;
# `status` is deliberately always `requires_verification`, never `likely_eligible`, so a
# stub can never falsely tell a real user they qualify for something nobody has actually
# evaluated.
def _static_placeholder_result(
    benefit_code: str, benefit_name: str, rule: BenefitRuleVersion, todo_note: str
) -> EligibilityResult:
    return EligibilityResult(
        benefit_code=benefit_code,
        benefit_name=benefit_name,
        status=EligibilityStatus.requires_verification,
        met_conditions=[],
        unmet_conditions=[],
        missing_data=["ocena merytoryczna dla tego świadczenia nie jest jeszcze zaimplementowana"],
        possible_solutions=[],
        plan=None,
        rules_version=rule.version,
        warnings=[
            "TYMCZASOWA ODPOWIEDŹ ZASTĘPCZA: logika oceny uprawnień dla tego świadczenia "
            "nie została jeszcze zaimplementowana - status jest stały niezależnie od "
            "podanych danych i służy wyłącznie do budowy widoków frontendowych, nie do "
            f"realnej oceny uprawnień. {todo_note}"
        ],
    )


def evaluate_sickness_benefit_during_pregnancy_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    return _static_placeholder_result(
        SICKNESS_DURING_PREGNANCY_BENEFIT_CODE,
        SICKNESS_DURING_PREGNANCY_BENEFIT_NAME,
        rule,
        "Docelowo: 100% podstawy, do 270 dni (ustawa zasiłkowa art. 8 ust. 1); wymaga "
        "weryfikacji okresu wyczekiwania (30/90 dni zależnie od tytułu ubezpieczenia, "
        "art. 4) i statusu ciąży.",
    )


def evaluate_supplementary_maternity_leave_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    return _static_placeholder_result(
        SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
        SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_NAME,
        rule,
        "Docelowo: 1 tydzień za każdy tydzień hospitalizacji dziecka, limit do 15. lub "
        "8. tygodnia po porodzie zależnie od okoliczności (Kodeks pracy art. 1802), 100% "
        "podstawy.",
    )


def evaluate_parental_leave_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    return _static_placeholder_result(
        PARENTAL_LEAVE_BENEFIT_CODE,
        PARENTAL_LEAVE_BENEFIT_NAME,
        rule,
        "Docelowo: 41/43 tygodni (65/67 z 'Za życiem'), 70% podstawy albo 81,5% łącznie "
        "z macierzyńskim pod warunkami; wymaga modelu podziału między rodzicami.",
    )


def evaluate_adoption_leave_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    return _static_placeholder_result(
        ADOPTION_LEAVE_BENEFIT_CODE,
        ADOPTION_LEAVE_BENEFIT_NAME,
        rule,
        "Docelowo: tabela 20/31/33/35/37 tygodni (jak zasiłek macierzyński), min. 9 "
        "tygodni, 100% podstawy, z limitami wieku dziecka zależnymi od formy "
        "(przysposobienie / rodzina zastępcza).",
    )


def evaluate_stillbirth_funeral_benefit_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    return _static_placeholder_result(
        STILLBIRTH_FUNERAL_BENEFIT_CODE,
        STILLBIRTH_FUNERAL_BENEFIT_NAME,
        rule,
        "Docelowo: świadczenie ryczałtowe 7 000 zł (nie procent podstawy wymiaru), "
        "wniosek Z-12 w ciągu 12 miesięcy od pochówku - wymaga rozszerzenia modelu "
        "danych o kwotę ryczałtową.",
    )
