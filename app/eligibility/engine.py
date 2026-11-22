"""Czysta logika oceny uprawnień do zasiłku macierzyńskiego za okres urlopu macierzyńskiego.

Brak zależności od bazy danych czy HTTP - funkcja przyjmuje gotową wersję reguły
(``BenefitRuleVersion``) oraz dane wniosku i zwraca ustrukturyzowany wynik oceny.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.schemas import (
    BenefitPlan,
    EligibilityResult,
    EligibilityStatus,
    EmploymentEndedReason,
    FosterCareType,
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
    REHABILITATION_BENEFIT_CODE,
    REHABILITATION_BENEFIT_NAME,
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
# Broader than _SELF_EMPLOYED_LIKE_TITLES: zlecenie is "dobrowolne ubezpieczenie
# chorobowe" for waiting-period purposes (ustawa zasiłkowa art. 4) even though it is NOT
# subject to the art. 2a debt-threshold restriction (that one only names osoby
# prowadzące pozarolniczą działalność i współpracujący, duchowni, marynarze).
_VOLUNTARY_INSURANCE_TITLES = {InsuranceTitle.zlecenie, InsuranceTitle.dzialalnosc_gospodarcza}


def _weeks_for_children_count(weeks_by_child_count: dict, children_count: int) -> int:
    key = str(children_count) if children_count < 5 else "5+"
    return weeks_by_child_count[key]


def _document_applies(doc: dict, is_self_employed: bool, *, za_zyciem: bool = False) -> bool:
    """Whether a seed-data required-document entry applies to this request.

    ``applies_to`` is an internal seed-data-only tag (never exposed on the public
    ``RequiredDocument`` schema): ``None``/missing means "always", "standard" means
    non-self-employed titles (employer issues Z-3). Self-employed-like titles get no
    "self_employed"-tagged document today (see ``app/rules/seed.py`` for why), but the
    tag is kept generic so a future rule version can add one without an engine change.
    "za_zyciem" (used only by urlop rodzicielski) means the document is needed only
    when the child has a "Za życiem" certificate.
    """
    applies_to = doc.get("applies_to")
    if applies_to is None:
        return True
    if applies_to == "self_employed":
        return is_self_employed
    if applies_to == "standard":
        return not is_self_employed
    if applies_to == "za_zyciem":
        return za_zyciem
    return True


def _apply_self_employed_debt_check(
    request: MaternityLeaveEligibilityRequest,
    rule: BenefitRuleVersion,
    met_conditions: list[str],
    unmet_conditions: list[str],
    missing_data: list[str],
    solutions: list[PossibleSolution],
) -> None:
    """Shared art. 2a debt-threshold check (self-employed-like titles only).

    Mutates the passed-in lists in place so callers keep accumulating into the same
    met/unmet/missing/solutions lists they already use for their other conditions.
    """
    if request.insurance_title not in _SELF_EMPLOYED_LIKE_TITLES:
        return
    if request.debt_amount_zl is None:
        missing_data.append(
            "informacja o zadłużeniu składkowym na dzień powstania prawa do zasiłku"
        )
        return
    threshold = rule.min_wage_reference_zl * rule.debt_threshold_percent_of_min_wage / Decimal(100)
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
            request.employment_ended_reason == EmploymentEndedReason.naruszenie_prawa_wyrokiem_sadu
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

    _apply_self_employed_debt_check(
        request, rule, met_conditions, unmet_conditions, missing_data, solutions
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


_PARENTAL_LEAVE_NON_TRANSFERABLE_WEEKS = 9
_PARENTAL_LEAVE_FULL_DOSE_RATE_PERCENT = Decimal("81.50")
_PARENTAL_LEAVE_MAX_PART_TIME_FRACTION = Decimal("0.5")


def _build_parental_leave_plan(
    rule: BenefitRuleVersion,
    request: MaternityLeaveEligibilityRequest,
    weeks: int,
    rate_percentage: Decimal,
) -> BenefitPlan:
    is_self_employed = request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES
    za_zyciem = bool(request.za_zyciem_certificate)
    required_documents = [
        RequiredDocument(code=doc["code"], name=doc["name"], when=doc["when"])
        for doc in rule.required_documents
        if _document_applies(doc, is_self_employed, za_zyciem=za_zyciem)
    ]
    return BenefitPlan(
        weeks=weeks,
        duration_description=None,
        rate_percentage=rate_percentage,
        institution=rule.institution,
        required_documents=required_documents,
        deadlines=list(rule.deadlines),
        legal_basis=list(rule.legal_basis),
    )


def evaluate_parental_leave_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    met_conditions: list[str] = []
    unmet_conditions: list[str] = []
    missing_data: list[str] = []
    solutions: list[PossibleSolution] = []
    warnings: list[str] = []

    if request.insured_at_birth is None:
        missing_data.append("status ubezpieczenia chorobowego wnioskującego rodzica")
    elif request.insured_at_birth:
        met_conditions.append(
            "wnioskujący rodzic objęty ubezpieczeniem chorobowym (ustawa zasiłkowa "
            "art. 29 ust. 1 pkt 1)"
        )
    else:
        unmet_conditions.append("wnioskujący rodzic nie jest objęty ubezpieczeniem chorobowym")
        solutions.append(
            PossibleSolution(
                type=SolutionType.limitation,
                description=(
                    "Bez ubezpieczenia chorobowego wnioskującemu rodzicowi nie przysługuje "
                    "urlop rodzicielski z tego tytułu. Sprawdź uprawnienia niezależnie dla "
                    "drugiego rodzica - to samo świadczenie, odrębne zgłoszenie."
                ),
            )
        )

    total_pool: int | None = None
    if request.za_zyciem_certificate is None:
        missing_data.append("informacja o zaświadczeniu 'Za życiem'")
    else:
        table = (
            rule.weeks_by_child_count_za_zyciem
            if request.za_zyciem_certificate
            else rule.weeks_by_child_count
        )
        total_pool = _weeks_for_children_count(table, request.children_count)
        if request.za_zyciem_certificate:
            met_conditions.append(
                f"zaświadczenie 'Za życiem' - wydłużony wymiar urlopu rodzicielskiego do "
                f"{total_pool} tygodni (Kodeks pracy art. 1821a § 2)"
            )

    weeks_for_applicant: int | None = None
    if request.other_parent_used_parental_leave_weeks is None:
        missing_data.append(
            "liczba tygodni urlopu rodzicielskiego już wykorzystanych przez drugiego rodzica"
        )
    elif total_pool is not None:
        reserved_for_other_parent = max(
            request.other_parent_used_parental_leave_weeks,
            _PARENTAL_LEAVE_NON_TRANSFERABLE_WEEKS,
        )
        weeks_for_applicant = max(total_pool - reserved_for_other_parent, 0)
        if weeks_for_applicant <= 0:
            unmet_conditions.append(
                "pula urlopu rodzicielskiego dostępna dla wnioskującego rodzica została "
                "wyczerpana - 9 tygodni z puli jest nieprzenoszalne na rzecz drugiego "
                "rodzica (Kodeks pracy art. 1821a § 4)"
            )
        else:
            met_conditions.append(
                f"dostępne {weeks_for_applicant} tyg. urlopu rodzicielskiego po "
                "uwzględnieniu nieprzenoszalnych 9 tygodni drugiego rodzica (Kodeks "
                "pracy art. 1821a § 4)"
            )

    rate_percentage: Decimal | None = None
    if request.full_dose_claimed_within_21_days is None:
        missing_data.append(
            "informacja, czy wniosek o pełny wymiar urlopu rodzicielskiego złożono w "
            "ciągu 21 dni po porodzie (wpływa na stawkę zasiłku)"
        )
    elif request.full_dose_claimed_within_21_days:
        rate_percentage = _PARENTAL_LEAVE_FULL_DOSE_RATE_PERCENT
        met_conditions.append(
            "wniosek o pełny wymiar złożony w ciągu 21 dni po porodzie (art. 30a) - "
            "stawka 81,5% łącznie z zasiłkiem macierzyńskim (ustawa zasiłkowa art. 31 "
            "ust. 3)"
        )
        warnings.append(
            "Stawka 81,5% dotyczy łącznego rozliczenia z zasiłkiem macierzyńskim za cały "
            "okres i nie obejmuje nieprzenoszalnych 9 tygodni drugiego rodzica, które są "
            "zawsze płatne 70% (ustawa zasiłkowa art. 31 ust. 3f) - zweryfikuj dokładne "
            "rozliczenie z ZUS/pracodawcą."
        )
    else:
        rate_percentage = rule.rate_percentage
        met_conditions.append(
            "stawka standardowa 70% podstawy wymiaru (ustawa zasiłkowa art. 31 ust. 2)"
        )

    part_time_fraction = request.part_time_fraction_during_parental_leave
    if (
        part_time_fraction is not None
        and part_time_fraction > _PARENTAL_LEAVE_MAX_PART_TIME_FRACTION
    ):
        part_time_fraction = _PARENTAL_LEAVE_MAX_PART_TIME_FRACTION
        warnings.append(
            "Łączenie urlopu rodzicielskiego z pracą jest dopuszczalne maksymalnie w "
            "wymiarze 1/2 etatu (Kodeks pracy art. 1821f) - podana wartość została "
            "ograniczona do tego limitu."
        )

    status = _decide_status(missing_data, unmet_conditions, solutions)

    is_standard_path_open = status == EligibilityStatus.likely_eligible or (
        status == EligibilityStatus.requires_verification and not unmet_conditions
    )
    plan = None
    if is_standard_path_open and weeks_for_applicant is not None and rate_percentage is not None:
        final_weeks = weeks_for_applicant
        if part_time_fraction is not None and part_time_fraction > 0:
            extended = Decimal(weeks_for_applicant) / (Decimal(1) - part_time_fraction)
            final_weeks = int(extended.to_integral_value(rounding=ROUND_HALF_UP))
            warnings.append(
                "Liczba tygodni uwzględnia proporcjonalne wydłużenie kalendarzowe przy "
                "łączeniu urlopu rodzicielskiego z pracą w niepełnym wymiarze (Kodeks "
                "pracy art. 1821f) - to wyliczenie przybliżone, zweryfikuj dokładny "
                "harmonogram z pracodawcą/ZUS."
            )
        plan = _build_parental_leave_plan(rule, request, final_weeks, rate_percentage)

    return EligibilityResult(
        benefit_code=PARENTAL_LEAVE_BENEFIT_CODE,
        benefit_name=PARENTAL_LEAVE_BENEFIT_NAME,
        status=status,
        met_conditions=met_conditions,
        unmet_conditions=unmet_conditions,
        missing_data=missing_data,
        possible_solutions=solutions,
        plan=plan,
        rules_version=rule.version,
        warnings=warnings,
    )


_SICKNESS_PREGNANCY_WAITING_DAYS_MANDATORY = 30
_SICKNESS_PREGNANCY_WAITING_DAYS_VOLUNTARY = 90
_SICKNESS_PREGNANCY_MAX_DURATION_DESCRIPTION = "do 270 dni niezdolności do pracy w okresie ciąży"


def _build_sickness_during_pregnancy_plan(
    rule: BenefitRuleVersion, request: MaternityLeaveEligibilityRequest
) -> BenefitPlan:
    is_self_employed = request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES
    required_documents = [
        RequiredDocument(code=doc["code"], name=doc["name"], when=doc["when"])
        for doc in rule.required_documents
        if _document_applies(doc, is_self_employed)
    ]
    return BenefitPlan(
        weeks=None,
        duration_description=_SICKNESS_PREGNANCY_MAX_DURATION_DESCRIPTION,
        rate_percentage=rule.rate_percentage,
        institution=rule.institution,
        required_documents=required_documents,
        deadlines=list(rule.deadlines),
        legal_basis=list(rule.legal_basis),
    )


def evaluate_sickness_benefit_during_pregnancy_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    met_conditions: list[str] = []
    unmet_conditions: list[str] = []
    missing_data: list[str] = []
    solutions: list[PossibleSolution] = []
    warnings: list[str] = []

    if request.is_pregnant is None:
        missing_data.append("status ciąży w okresie niezdolności do pracy")
    elif request.is_pregnant:
        met_conditions.append(
            "niezdolność do pracy powstała w okresie ciąży - stawka 100% i okres do 270 "
            "dni (ustawa zasiłkowa art. 8 ust. 1)"
        )
    else:
        unmet_conditions.append(
            "niezdolność do pracy nie powstała w okresie ciąży - ta podwyższona ścieżka "
            "(100%, do 270 dni) nie ma zastosowania"
        )
        solutions.append(
            PossibleSolution(
                type=SolutionType.limitation,
                description=(
                    "Bez ciąży nie przysługuje ta podwyższona ścieżka zasiłku "
                    "chorobowego (100% podstawy, do 270 dni) - może nadal przysługiwać "
                    "zwykły zasiłek chorobowy (80% albo 100% w szczególnych przypadkach, "
                    "do 182 dni), który nie jest jeszcze osobno modelowany w tym "
                    "silniku."
                ),
            )
        )

    required_waiting_days: int | None = None
    if request.insurance_title is None:
        missing_data.append(
            "tytuł ubezpieczenia (potrzebny do ustalenia okresu wyczekiwania - 30 dni "
            "przy ubezpieczeniu obowiązkowym, 90 dni przy dobrowolnym)"
        )
    else:
        required_waiting_days = (
            _SICKNESS_PREGNANCY_WAITING_DAYS_VOLUNTARY
            if request.insurance_title in _VOLUNTARY_INSURANCE_TITLES
            else _SICKNESS_PREGNANCY_WAITING_DAYS_MANDATORY
        )

    if request.insured_days_continuous is None:
        missing_data.append("liczba dni nieprzerwanego ubezpieczenia chorobowego")
    elif required_waiting_days is not None:
        if request.insured_days_continuous >= required_waiting_days:
            met_conditions.append(
                f"okres wyczekiwania ({required_waiting_days} dni) spełniony - "
                f"{request.insured_days_continuous} dni nieprzerwanego ubezpieczenia "
                "(ustawa zasiłkowa art. 4)"
            )
        else:
            unmet_conditions.append(
                f"okres wyczekiwania nie został jeszcze spełniony - wymagane "
                f"{required_waiting_days} dni nieprzerwanego ubezpieczenia, podano "
                f"{request.insured_days_continuous} (ustawa zasiłkowa art. 4)"
            )
            solutions.append(
                PossibleSolution(
                    type=SolutionType.corrective_action,
                    description=(
                        "Poczekaj do upływu wymaganego okresu wyczekiwania. Sprawdź też, "
                        "czy nie dotyczy jeden z wyjątków znoszących okres wyczekiwania "
                        "(np. absolwenci w ciągu 90 dni od ukończenia szkoły, wypadek w "
                        "drodze do/z pracy, wcześniejszy co najmniej 10-letni okres "
                        "obowiązkowego ubezpieczenia) - te wyjątki nie są jeszcze "
                        "weryfikowane automatycznie przez ten silnik."
                    ),
                    legal_basis="ustawa zasiłkowa art. 4",
                )
            )
            warnings.append(
                "Wyjątki znoszące okres wyczekiwania (ustawa zasiłkowa art. 4 ust. 3) nie "
                "są jeszcze automatycznie weryfikowane - sprawdź je ręcznie, jeśli mogą "
                "dotyczyć tego wniosku."
            )

    _apply_self_employed_debt_check(
        request, rule, met_conditions, unmet_conditions, missing_data, solutions
    )

    status = _decide_status(missing_data, unmet_conditions, solutions)

    is_standard_path_open = status == EligibilityStatus.likely_eligible or (
        status == EligibilityStatus.requires_verification and not unmet_conditions
    )
    plan = _build_sickness_during_pregnancy_plan(rule, request) if is_standard_path_open else None

    return EligibilityResult(
        benefit_code=SICKNESS_DURING_PREGNANCY_BENEFIT_CODE,
        benefit_name=SICKNESS_DURING_PREGNANCY_BENEFIT_NAME,
        status=status,
        met_conditions=met_conditions,
        unmet_conditions=unmet_conditions,
        missing_data=missing_data,
        possible_solutions=solutions,
        plan=plan,
        rules_version=rule.version,
        warnings=warnings,
    )


_REHABILITATION_RATE_FIRST_3_MONTHS = Decimal("90.00")
_REHABILITATION_RATE_PREGNANT = Decimal("100.00")
_REHABILITATION_MAX_DURATION_DESCRIPTION = "do 12 miesięcy"


def _build_rehabilitation_benefit_plan(
    rule: BenefitRuleVersion, request: MaternityLeaveEligibilityRequest, rate_percentage: Decimal
) -> BenefitPlan:
    is_self_employed = request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES
    required_documents = [
        RequiredDocument(code=doc["code"], name=doc["name"], when=doc["when"])
        for doc in rule.required_documents
        if _document_applies(doc, is_self_employed)
    ]
    return BenefitPlan(
        weeks=None,
        duration_description=_REHABILITATION_MAX_DURATION_DESCRIPTION,
        rate_percentage=rate_percentage,
        institution=rule.institution,
        required_documents=required_documents,
        deadlines=list(rule.deadlines),
        legal_basis=list(rule.legal_basis),
    )


def evaluate_rehabilitation_benefit_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    met_conditions: list[str] = []
    unmet_conditions: list[str] = []
    missing_data: list[str] = []
    solutions: list[PossibleSolution] = []
    warnings: list[str] = []

    if request.sickness_benefit_period_exhausted is None:
        missing_data.append("czy wyczerpano maksymalny okres zasiłku chorobowego")
    elif request.sickness_benefit_period_exhausted:
        met_conditions.append(
            "wyczerpano maksymalny okres zasiłku chorobowego (ustawa zasiłkowa art. 18 ust. 1)"
        )
    else:
        unmet_conditions.append(
            "nie wyczerpano jeszcze maksymalnego okresu zasiłku chorobowego - "
            "świadczenie rehabilitacyjne przysługuje dopiero po jego wyczerpaniu"
        )
        solutions.append(
            PossibleSolution(
                type=SolutionType.limitation,
                description=(
                    "Świadczenie rehabilitacyjne można uzyskać dopiero po wyczerpaniu "
                    "maksymalnego okresu zasiłku chorobowego (182 dni, albo 270 dni w "
                    "okresie ciąży)."
                ),
                legal_basis="ustawa zasiłkowa art. 18 ust. 1",
            )
        )

    if request.medical_prognosis_recovery_possible is None:
        missing_data.append(
            "czy lekarz orzecznik ZUS stwierdził rokowanie odzyskania zdolności do pracy"
        )
    elif request.medical_prognosis_recovery_possible:
        met_conditions.append(
            "lekarz orzecznik ZUS stwierdził rokowanie odzyskania zdolności do pracy "
            "(ustawa zasiłkowa art. 18 ust. 1)"
        )
    else:
        unmet_conditions.append(
            "brak pozytywnego rokowania lekarza orzecznika ZUS co do odzyskania zdolności do pracy"
        )
        solutions.append(
            PossibleSolution(
                type=SolutionType.limitation,
                description=(
                    "Bez pozytywnego rokowania lekarza orzecznika ZUS świadczenie "
                    "rehabilitacyjne nie przysługuje - rozważ wniosek o rentę z tytułu "
                    "niezdolności do pracy (poza zakresem tego silnika)."
                ),
                legal_basis="ustawa zasiłkowa art. 18 ust. 1",
            )
        )

    if request.excluded_from_rehabilitation_benefit is None:
        missing_data.append(
            "czy przysługuje już inne świadczenie wykluczające prawo do świadczenia "
            "rehabilitacyjnego"
        )
    elif request.excluded_from_rehabilitation_benefit:
        unmet_conditions.append(
            "przysługuje inne świadczenie wykluczające prawo do świadczenia "
            "rehabilitacyjnego (ustawa zasiłkowa art. 18 ust. 7)"
        )
        solutions.append(
            PossibleSolution(
                type=SolutionType.limitation,
                description=(
                    "Emerytura, renta, zasiłek dla bezrobotnych, świadczenie "
                    "przedemerytalne, rodzicielskie świadczenie uzupełniające, "
                    "nauczycielskie świadczenie kompensacyjne i urlop dla poratowania "
                    "zdrowia wykluczają prawo do świadczenia rehabilitacyjnego - sprawdź, "
                    "które z nich faktycznie przysługuje."
                ),
                legal_basis="ustawa zasiłkowa art. 18 ust. 7",
            )
        )
    else:
        met_conditions.append(
            "brak świadczeń wykluczających prawo do świadczenia rehabilitacyjnego "
            "(ustawa zasiłkowa art. 18 ust. 7)"
        )

    rate_percentage: Decimal | None = None
    if request.is_pregnant is None:
        missing_data.append("status ciąży (wpływa na stawkę: 100% zamiast 90%/75%)")
    elif request.is_pregnant:
        rate_percentage = _REHABILITATION_RATE_PREGNANT
        met_conditions.append(
            "niezdolność do pracy w okresie ciąży - stawka 100% przez cały okres "
            "(ustawa zasiłkowa art. 18 ust. 2)"
        )
    else:
        rate_percentage = _REHABILITATION_RATE_FIRST_3_MONTHS
        warnings.append(
            "Stawka 90% dotyczy pierwszych 3 miesięcy świadczenia - od 4. miesiąca "
            "obniża się do 75% (ustawa zasiłkowa art. 18 ust. 2), co nie jest jeszcze "
            "rozbijane miesiąc po miesiącu w tym wyniku."
        )

    _apply_self_employed_debt_check(
        request, rule, met_conditions, unmet_conditions, missing_data, solutions
    )

    status = _decide_status(missing_data, unmet_conditions, solutions)

    is_standard_path_open = status == EligibilityStatus.likely_eligible or (
        status == EligibilityStatus.requires_verification and not unmet_conditions
    )
    plan = None
    if is_standard_path_open and rate_percentage is not None:
        plan = _build_rehabilitation_benefit_plan(rule, request, rate_percentage)

    return EligibilityResult(
        benefit_code=REHABILITATION_BENEFIT_CODE,
        benefit_name=REHABILITATION_BENEFIT_NAME,
        status=status,
        met_conditions=met_conditions,
        unmet_conditions=unmet_conditions,
        missing_data=missing_data,
        possible_solutions=solutions,
        plan=plan,
        rules_version=rule.version,
        warnings=warnings,
    )


_SUPPLEMENTARY_LEAVE_EXTENDED_CUTOFF_WEEK = 15
_SUPPLEMENTARY_LEAVE_STANDARD_CUTOFF_WEEK = 8
_SUPPLEMENTARY_LEAVE_EXTENDED_MAX_GESTATIONAL_WEEK = 28
_SUPPLEMENTARY_LEAVE_EXTENDED_MAX_BIRTH_WEIGHT_GRAMS = 1000
# Kodeks pracy art. 1802 §4: wniosek składa się "w terminie niekrótszym niż 21 dni przed
# zakończeniem korzystania z urlopu macierzyńskiego" - to jest FAKTYCZNY termin graniczny
# tego świadczenia, niezależny od 8./15. tygodnia po porodzie (ten drugi tylko ogranicza,
# które tygodnie hospitalizacji się liczą - §1/§3 - a nie kiedy trzeba złożyć wniosek).
_SUPPLEMENTARY_LEAVE_FILING_DEADLINE_WEEKS_BEFORE_END = 3


def _resolve_supplementary_leave_cutoff_week(
    gestational_week_at_birth: int, birth_weight_grams: int
) -> int:
    """Kodeks pracy art. 1802 §1: 15. tydzień po porodzie przy urodzeniu <28 tyg.
    ciąży LUB masie ≤1000g, w pozostałych kwalifikujących przypadkach 8. tydzień."""
    is_extended_case = (
        gestational_week_at_birth < _SUPPLEMENTARY_LEAVE_EXTENDED_MAX_GESTATIONAL_WEEK
        or birth_weight_grams <= _SUPPLEMENTARY_LEAVE_EXTENDED_MAX_BIRTH_WEIGHT_GRAMS
    )
    return (
        _SUPPLEMENTARY_LEAVE_EXTENDED_CUTOFF_WEEK
        if is_extended_case
        else _SUPPLEMENTARY_LEAVE_STANDARD_CUTOFF_WEEK
    )


def _build_supplementary_maternity_leave_plan(
    rule: BenefitRuleVersion, request: MaternityLeaveEligibilityRequest, weeks: int
) -> BenefitPlan:
    is_self_employed = request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES
    required_documents = [
        RequiredDocument(code=doc["code"], name=doc["name"], when=doc["when"])
        for doc in rule.required_documents
        if _document_applies(doc, is_self_employed)
    ]
    return BenefitPlan(
        weeks=weeks,
        duration_description=None,
        rate_percentage=rule.rate_percentage,
        institution=rule.institution,
        required_documents=required_documents,
        deadlines=list(rule.deadlines),
        legal_basis=list(rule.legal_basis),
    )


def evaluate_supplementary_maternity_leave_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    met_conditions: list[str] = []
    unmet_conditions: list[str] = []
    missing_data: list[str] = []
    solutions: list[PossibleSolution] = []
    warnings: list[str] = []

    hospitalization_weeks_reported: int | None = None
    if request.child_hospitalization_weeks is None:
        missing_data.append("liczba tygodni pobytu dziecka w szpitalu po porodzie")
    elif request.child_hospitalization_weeks <= 0:
        unmet_conditions.append(
            "brak hospitalizacji dziecka po porodzie - uzupełniający urlop "
            "macierzyński nie ma zastosowania (Kodeks pracy art. 1802 §1)"
        )
    else:
        hospitalization_weeks_reported = request.child_hospitalization_weeks
        met_conditions.append(
            f"hospitalizacja dziecka po porodzie przez {hospitalization_weeks_reported} "
            "tyg. (Kodeks pracy art. 1802 §1)"
        )

    # Tydzień graniczny (8. albo 15. po porodzie) ogranicza WYŁĄCZNIE, które tygodnie
    # pobytu w szpitalu wlicza się do wymiaru urlopu (Kodeks pracy art. 1802 §1 i §3) -
    # to NIE jest termin na skorzystanie z urlopu ani na złożenie wniosku (ten jest
    # osobno, §4, patrz niżej).
    cutoff_week: int | None = None
    if request.gestational_week_at_birth is None or request.birth_weight_grams is None:
        missing_data.append(
            "tydzień ciąży w dniu porodu i masa urodzeniowa dziecka (potrzebne do "
            "ustalenia, które tygodnie hospitalizacji się liczą: do 15. albo do 8. "
            "tygodnia po porodzie)"
        )
    else:
        cutoff_week = _resolve_supplementary_leave_cutoff_week(
            request.gestational_week_at_birth, request.birth_weight_grams
        )
        met_conditions.append(
            f"do wymiaru liczą się tygodnie hospitalizacji do {cutoff_week}. tygodnia "
            "po porodzie (Kodeks pracy art. 1802 §1 i §3)"
        )
        if (
            request.postpartum_weeks_elapsed is not None
            and request.postpartum_weeks_elapsed > cutoff_week
        ):
            warnings.append(
                f"Minął {cutoff_week}. tydzień po porodzie - jeśli hospitalizacja "
                "trwała dłużej, do wymiaru urlopu liczą się tylko tygodnie przypadające "
                "do tego tygodnia (Kodeks pracy art. 1802 §1 i §3); upewnij się, że "
                "podana liczba tygodni hospitalizacji już to uwzględnia."
            )

    # Wymiar urlopu = zgłoszone tygodnie hospitalizacji, ograniczone do granicznego
    # tygodnia po porodzie (zakłada hospitalizację od dnia porodu - typowy przypadek
    # wcześniaka trafiającego na OIOM od razu po urodzeniu). Bez znajomości obu
    # wartości nie da się tego policzyć poprawnie, więc `weeks` zostaje `None` (bez
    # planu) zamiast pokazywać niesprawdzony, potencjalnie zawyżony wymiar.
    weeks: int | None = None
    if hospitalization_weeks_reported is not None and cutoff_week is not None:
        weeks = min(hospitalization_weeks_reported, cutoff_week)
        if weeks < hospitalization_weeks_reported:
            warnings.append(
                f"Zgłoszono {hospitalization_weeks_reported} tyg. hospitalizacji, ale "
                f"do wymiaru urlopu liczy się maksymalnie {cutoff_week} tyg. po "
                "porodzie (Kodeks pracy art. 1802 §1 i §3) - wymiar ograniczony do "
                f"{weeks} tyg."
            )

    # Rzeczywisty termin graniczny: wniosek najpóźniej 21 dni (3 tygodnie) przed
    # zakończeniem podstawowego urlopu macierzyńskiego (Kodeks pracy art. 1802 §4) -
    # niezależny od tygodnia granicznego powyżej.
    if request.postpartum_weeks_elapsed is None:
        missing_data.append(
            "liczba tygodni, które upłynęły od porodu (potrzebna do ustalenia terminu "
            "złożenia wniosku - art. 1802 §4)"
        )
    else:
        maternity_leave_weeks = _weeks_for_children_count(
            rule.weeks_by_child_count, request.children_count
        )
        weeks_remaining_of_maternity_leave = (
            maternity_leave_weeks - request.postpartum_weeks_elapsed
        )
        if (
            weeks_remaining_of_maternity_leave
            < _SUPPLEMENTARY_LEAVE_FILING_DEADLINE_WEEKS_BEFORE_END
        ):
            unmet_conditions.append(
                "termin na złożenie wniosku minął - wniosek trzeba złożyć nie później "
                "niż 21 dni przed zakończeniem podstawowego urlopu macierzyńskiego "
                "(Kodeks pracy art. 1802 §4)"
            )
            solutions.append(
                PossibleSolution(
                    type=SolutionType.limitation,
                    description=(
                        "Wniosek o uzupełniający urlop macierzyński trzeba złożyć nie "
                        "później niż 21 dni przed zakończeniem korzystania z urlopu "
                        "macierzyńskiego - po tym terminie prawo wygasa."
                    ),
                    legal_basis="Kodeks pracy art. 1802 §4",
                )
            )
        else:
            met_conditions.append(
                "termin na złożenie wniosku (21 dni przed końcem urlopu "
                "macierzyńskiego) nie minął (Kodeks pracy art. 1802 §4)"
            )

    _apply_self_employed_debt_check(
        request, rule, met_conditions, unmet_conditions, missing_data, solutions
    )

    status = _decide_status(missing_data, unmet_conditions, solutions)

    is_standard_path_open = status == EligibilityStatus.likely_eligible or (
        status == EligibilityStatus.requires_verification and not unmet_conditions
    )
    plan = (
        _build_supplementary_maternity_leave_plan(rule, request, weeks)
        if is_standard_path_open and weeks is not None
        else None
    )

    return EligibilityResult(
        benefit_code=SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_CODE,
        benefit_name=SUPPLEMENTARY_MATERNITY_LEAVE_BENEFIT_NAME,
        status=status,
        met_conditions=met_conditions,
        unmet_conditions=unmet_conditions,
        missing_data=missing_data,
        possible_solutions=solutions,
        plan=plan,
        rules_version=rule.version,
        warnings=warnings,
    )


_ADOPTION_LEAVE_FOSTER_CARE_AGE_LIMIT = 7
_ADOPTION_LEAVE_FOSTER_CARE_DEFERRED_AGE_LIMIT = 10
_ADOPTION_LEAVE_PETITION_AGE_LIMIT = 14


def evaluate_adoption_leave_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    met_conditions: list[str] = []
    unmet_conditions: list[str] = []
    missing_data: list[str] = []
    solutions: list[PossibleSolution] = []
    warnings: list[str] = []

    if request.is_adoption_or_foster_care is None:
        missing_data.append(
            "czy wniosek dotyczy przyjęcia dziecka na wychowanie (przysposobienie lub "
            "rodzina zastępcza)"
        )
    elif not request.is_adoption_or_foster_care:
        unmet_conditions.append(
            "wniosek nie dotyczy przyjęcia dziecka na wychowanie - to świadczenie "
            "obejmuje wyłącznie adopcję/rodzinę zastępczą"
        )
        solutions.append(
            PossibleSolution(
                type=SolutionType.alternative_benefit,
                description=(
                    "Bez przysposobienia/rodziny zastępczej właściwym świadczeniem jest "
                    "zwykły zasiłek macierzyński za okres urlopu macierzyńskiego."
                ),
                legal_basis="Kodeks pracy art. 180",
                related_benefit_code=BENEFIT_CODE,
            )
        )
    else:
        met_conditions.append(
            "wniosek dotyczy przyjęcia dziecka na wychowanie (Kodeks pracy art. 183)"
        )

        age_limit: int | None = None
        if request.foster_care_type is None:
            missing_data.append("forma przyjęcia dziecka (przysposobienie/rodzina zastępcza)")
        elif request.foster_care_type == FosterCareType.rodzina_zastepcza_zawodowa:
            unmet_conditions.append(
                "rodzina zastępcza zawodowa nie uprawnia do tego urlopu (Kodeks pracy "
                "art. 183 §1(1))"
            )
            solutions.append(
                PossibleSolution(
                    type=SolutionType.limitation,
                    description=(
                        "Rodzina zastępcza zawodowa jest wyłączona z prawa do urlopu na "
                        "warunkach urlopu macierzyńskiego."
                    ),
                    legal_basis="Kodeks pracy art. 183 §1(1)",
                )
            )
        elif request.foster_care_type == FosterCareType.wniosek_o_przysposobienie:
            age_limit = _ADOPTION_LEAVE_PETITION_AGE_LIMIT
            met_conditions.append(
                f"przysposobienie - limit wieku dziecka {age_limit} lat (Kodeks pracy art. 183 §1)"
            )
        else:
            if request.school_obligation_deferred is None:
                missing_data.append(
                    "czy wobec dziecka odroczono obowiązek szkolny (wpływa na limit "
                    "wieku: 7 albo 10 lat)"
                )
            else:
                age_limit = (
                    _ADOPTION_LEAVE_FOSTER_CARE_DEFERRED_AGE_LIMIT
                    if request.school_obligation_deferred
                    else _ADOPTION_LEAVE_FOSTER_CARE_AGE_LIMIT
                )
                met_conditions.append(
                    f"rodzina zastępcza - limit wieku dziecka {age_limit} lat (Kodeks "
                    "pracy art. 183 §1)"
                )

        if request.child_age_years is None:
            missing_data.append("wiek dziecka w pełnych latach")
        elif age_limit is not None:
            if request.child_age_years >= age_limit:
                unmet_conditions.append(
                    f"dziecko ukończyło {age_limit} lat - limit wieku dla tej formy "
                    "przyjęcia na wychowanie został przekroczony (Kodeks pracy art. 183)"
                )
                solutions.append(
                    PossibleSolution(
                        type=SolutionType.limitation,
                        description=(
                            "Po przekroczeniu limitu wieku dziecka prawo do urlopu na "
                            "warunkach urlopu macierzyńskiego nie przysługuje."
                        ),
                        legal_basis="Kodeks pracy art. 183",
                    )
                )
            else:
                met_conditions.append(
                    f"dziecko ma {request.child_age_years} lat - poniżej limitu "
                    f"{age_limit} lat (Kodeks pracy art. 183)"
                )

    _apply_self_employed_debt_check(
        request, rule, met_conditions, unmet_conditions, missing_data, solutions
    )

    status = _decide_status(missing_data, unmet_conditions, solutions)

    is_standard_path_open = status == EligibilityStatus.likely_eligible or (
        status == EligibilityStatus.requires_verification and not unmet_conditions
    )
    plan = _build_plan(rule, request) if is_standard_path_open else None
    if plan is not None:
        warnings.append(
            "Liczba tygodni pochodzi ze standardowej tabeli wg liczby dzieci - "
            "gwarancja minimum 9 tygodni przy adopcji dziecka bliskiego granicy "
            "wiekowej (Kodeks pracy art. 183) nie jest jeszcze uwzględniana osobno, "
            "zweryfikuj w granicznych przypadkach."
        )

    return EligibilityResult(
        benefit_code=ADOPTION_LEAVE_BENEFIT_CODE,
        benefit_name=ADOPTION_LEAVE_BENEFIT_NAME,
        status=status,
        met_conditions=met_conditions,
        unmet_conditions=unmet_conditions,
        missing_data=missing_data,
        possible_solutions=solutions,
        plan=plan,
        rules_version=rule.version,
        warnings=warnings,
    )


_STILLBIRTH_FUNERAL_DEADLINE_DAYS = 365


def _build_stillbirth_funeral_benefit_plan(
    rule: BenefitRuleVersion, request: MaternityLeaveEligibilityRequest
) -> BenefitPlan:
    is_self_employed = request.insurance_title in _SELF_EMPLOYED_LIKE_TITLES
    required_documents = [
        RequiredDocument(code=doc["code"], name=doc["name"], when=doc["when"])
        for doc in rule.required_documents
        if _document_applies(doc, is_self_employed)
    ]
    return BenefitPlan(
        weeks=None,
        duration_description=None,
        rate_percentage=None,
        lump_sum_amount_zl=rule.lump_sum_amount_zl,
        institution=rule.institution,
        required_documents=required_documents,
        deadlines=list(rule.deadlines),
        legal_basis=list(rule.legal_basis),
    )


def evaluate_stillbirth_funeral_benefit_eligibility(
    request: MaternityLeaveEligibilityRequest, rule: BenefitRuleVersion
) -> EligibilityResult:
    met_conditions: list[str] = []
    unmet_conditions: list[str] = []
    missing_data: list[str] = []
    solutions: list[PossibleSolution] = []
    warnings: list[str] = []

    if request.is_stillbirth_or_infant_death is None:
        missing_data.append("czy doszło do martwego urodzenia dziecka")
    elif request.is_stillbirth_or_infant_death:
        met_conditions.append(
            "martwe urodzenie dziecka (Poradnik ZUS 2026, zasiłek pogrzebowy formularz Z-12)"
        )
        warnings.append(
            "To pole obejmuje też zgon dziecka przed ukończeniem 8. tygodnia życia po "
            "żywym urodzeniu - ten silnik ocenia wyłącznie ścieżkę martwego urodzenia "
            "(formularz Z-12); zgon po żywym urodzeniu może wymagać innej procedury "
            "zasiłku pogrzebowego, która nie jest tu modelowana."
        )
    else:
        unmet_conditions.append("brak martwego urodzenia dziecka - świadczenie nie dotyczy")
        solutions.append(
            PossibleSolution(
                type=SolutionType.limitation,
                description=(
                    "To świadczenie dotyczy wyłącznie martwego urodzenia dziecka "
                    "(formularz Z-12). Zwykły zgon wymaga standardowego zasiłku "
                    "pogrzebowego, który nie jest jeszcze modelowany w tym silniku."
                ),
            )
        )

    if request.days_since_burial is None:
        missing_data.append("liczba dni, które upłynęły od dnia pochówku")
    elif request.days_since_burial > _STILLBIRTH_FUNERAL_DEADLINE_DAYS:
        unmet_conditions.append(
            f"minęło więcej niż {_STILLBIRTH_FUNERAL_DEADLINE_DAYS} dni (12 miesięcy) od "
            "pochówku - termin na złożenie wniosku Z-12 wygasł"
        )
        solutions.append(
            PossibleSolution(
                type=SolutionType.limitation,
                description=(
                    "Wniosek o zasiłek pogrzebowy (Z-12) trzeba złożyć w ciągu 12 "
                    "miesięcy od pochówku - po tym terminie prawo do świadczenia wygasa."
                ),
            )
        )
    else:
        met_conditions.append(
            f"termin 12 miesięcy od pochówku nie minął ({request.days_since_burial} dni)"
        )

    status = _decide_status(missing_data, unmet_conditions, solutions)

    is_standard_path_open = status == EligibilityStatus.likely_eligible or (
        status == EligibilityStatus.requires_verification and not unmet_conditions
    )
    plan = _build_stillbirth_funeral_benefit_plan(rule, request) if is_standard_path_open else None

    return EligibilityResult(
        benefit_code=STILLBIRTH_FUNERAL_BENEFIT_CODE,
        benefit_name=STILLBIRTH_FUNERAL_BENEFIT_NAME,
        status=status,
        met_conditions=met_conditions,
        unmet_conditions=unmet_conditions,
        missing_data=missing_data,
        possible_solutions=solutions,
        plan=plan,
        rules_version=rule.version,
        warnings=warnings,
    )
