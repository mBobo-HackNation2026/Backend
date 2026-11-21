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
                f"{total_pool} tygodni (ustawa zasiłkowa art. 31 ust. 3)"
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
                "rodzica (Kodeks pracy art. 1821a)"
            )
        else:
            met_conditions.append(
                f"dostępne {weeks_for_applicant} tyg. urlopu rodzicielskiego po "
                "uwzględnieniu nieprzenoszalnych 9 tygodni drugiego rodzica (Kodeks "
                "pracy art. 1821a)"
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
            "wniosek o pełny wymiar złożony w ciągu 21 dni po porodzie - stawka 81,5% "
            "łącznie z zasiłkiem macierzyńskim (ustawa zasiłkowa art. 31 ust. 3g)"
        )
        warnings.append(
            "Stawka 81,5% dotyczy łącznego rozliczenia z zasiłkiem macierzyńskim za cały "
            "okres i nie obejmuje nieprzenoszalnych 9 tygodni drugiego rodzica, które są "
            "zawsze płatne 70% - zweryfikuj dokładne rozliczenie z ZUS/pracodawcą."
        )
    else:
        rate_percentage = rule.rate_percentage
        met_conditions.append(
            "stawka standardowa 70% podstawy wymiaru (ustawa zasiłkowa art. 31 ust. 3)"
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
    if (
        is_standard_path_open
        and weeks_for_applicant is not None
        and rate_percentage is not None
    ):
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
_SICKNESS_PREGNANCY_MAX_DURATION_DESCRIPTION = (
    "do 270 dni niezdolności do pracy w okresie ciąży"
)


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


# --- STUB BENEFITS (Faza 2, not yet implemented) -----------------------------------
# These three evaluators (supplementary maternity leave, adoption/foster care leave,
# stillbirth funeral benefit) always return the same static result regardless of input.
# They exist so the frontend can build UI against a stable API shape before the real
# eligibility logic is written (explicit product decision - see project memory
# `project-ebobo-stub-benefits-debt`). Each one's `warnings` entry says so plainly;
# `status` is deliberately always `requires_verification`, never `likely_eligible`, so a
# stub can never falsely tell a real user they qualify for something nobody has actually
# evaluated. Parental leave (urlop rodzicielski) and sickness benefit during pregnancy
# (zasiłek chorobowy w ciąży) used to be in this group - see
# evaluate_parental_leave_eligibility and evaluate_sickness_benefit_during_pregnancy_eligibility
# above for their real logic.
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
