# Eligibility Engine v2 (benefit_code + alternative benefit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use it-subagent-driven-development (recommended) or it-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize `/api/v1/eligibility/check` so it can evaluate more than one benefit type
(`POST /api/v1/eligibility/check/{benefit_code}`), and use that generalization to give the art. 30
"zasiłek w wysokości zasiłku macierzyńskiego" (the alternative benefit the Phase 1 engine already
*describes* in `possible_solutions`) its own `BenefitRuleVersion` and a real `plan` - closing the gap
where that alternative path was only ever text, never an actionable plan.

**Architecture:** `BenefitRuleVersion` gains a `duration_until_birth` flag (for benefits paid "until
the day of birth" instead of a fixed week count by child count) plus `institution`/`deadlines`
columns, so these are no longer hardcoded per-benefit-type literals inside the engine. A new
`app/eligibility/registry.py` maps `benefit_code -> evaluator function`; the endpoint becomes a thin
dispatcher over that registry. A second evaluator, `evaluate_alternative_maternity_benefit_eligibility`,
is added to `app/eligibility/engine.py` alongside the existing one, sharing the same request schema
(both evaluate the same underlying biographical facts) and two small extracted helpers (`_build_plan`,
`_decide_status`).

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.1 (SQLite), pytest, Ruff - all already pinned in
`pyproject.toml`. No new dependencies.

---

## Context for the engineer

Read these before starting:

- `docs/plans/2026-11-21-eligibility-engine-v1-maternity-leave.md` - the Phase 1 plan this one
  extends. Read it for the original design rationale; don't re-implement anything it already built.
- `app/eligibility/engine.py`, `app/eligibility/schemas.py`, `app/rules/seed.py`,
  `app/eligibility/rules_repository.py`, `app/api/v1/endpoints/eligibility.py` - the Phase 1 code this
  plan modifies. Read all five in full before starting Task 1; several tasks touch more than one of
  them and later tasks assume you remember the shape of the earlier edits.
- `app/db/models/benefit_rule.py` - the model this plan adds columns to.
- `tests/test_benefit_rule_models.py`, `tests/test_rules_seed.py`, `tests/test_eligibility_schemas.py`,
  `tests/test_eligibility_engine.py`, `tests/test_rules_repository.py`, `tests/test_eligibility_endpoint.py`
  - the existing test suite this plan extends. `tests/conftest.py` defines the `client` fixture
    (`TestClient(app)`) used by endpoint tests.

**This is a known, intentional breaking API change.** `POST /api/v1/eligibility/check` (no code in the
URL) stops existing; every caller must switch to `POST /api/v1/eligibility/check/{benefit_code}`. This
was flagged as required future work in the Phase 1 final review ("API shape will not survive a second
benefit type"). Task 8 updates the README to document the new shape - if there's a separate frontend
team consuming this API, they need to be told about this breaking change directly, not just via the
README.

**Legal basis for the new benefit (already verified in project memory `project-ebobo-legal-rules`,
cross-checked 2026-11-21 against an external review that caught a real fabrication risk in a different
part of this feature - see the `Z-3b` warning already in `app/rules/seed.py` for context on how
seriously this project takes "don't invent documented facts"):**
- Zasiłek w wysokości zasiłku macierzyńskiego: 100% podstawy wymiaru, **do dnia porodu** (not a fixed
  week count by child count - this is the whole reason `duration_until_birth` exists) - ustawa
  zasiłkowa art. 30 ust. 1 i ust. 3.
- Przysługuje wyłącznie, gdy ubezpieczenie chorobowe ustało w okresie ciąży wskutek: (a) upadłości,
  likwidacji lub śmierci pracodawcy (art. 30 ust. 1 pkt 1), lub (b) rozwiązania umowy z naruszeniem
  przepisów prawa stwierdzonym prawomocnym wyrokiem sądu (art. 30 ust. 1 pkt 2).
- The `EmploymentEndedReason` enum (`app/eligibility/schemas.py`) already has exactly these two
  members and no others - every branch in the new evaluator that checks this enum is exhaustive by
  construction; don't add a `else: unmet` fallback branch for "some other reason", because there is no
  third enum value that could reach it (an untestable/unreachable branch is a plan violation, not a
  safety net).
- Because this benefit's precondition is "the employer relationship ended", it does not carry a
  self-employed/Z-3-vs-nothing document distinction or an art. 2a debt-threshold check the way the
  standard maternity-leave benefit does (that debt rule applies to people still running pozarolnicza
  działalność, which is a different scenario from "my employer went bankrupt"). Do not port the debt
  logic or the self-employed document filtering into the new evaluator - it doesn't apply here.
- No specific deadline (number of days) for filing is documented anywhere in the source material for
  this benefit - cite ustawa zasiłkowa art. 67 (przedawnienie roszczeń) topically, without inventing a
  day count, exactly as shown in Task 4's code.

**Scope boundaries (don't build these now - they're later phases/slices):**
- No automatic chaining between the two evaluators (e.g. the endpoint calling both and merging
  results). `related_benefit_code` on `PossibleSolution` is a pointer the *frontend* follows with a
  second request; the cross-benefit orchestration itself is Phase 3's job ("check the other parent" /
  alternative-path layer), not this branch's.
- No other Phase 2 benefit (urlop ojcowski, zasiłek chorobowy w ciąży, urlop rodzicielski, etc.) - this
  branch only adds the one benefit that Phase 1's engine already half-described.
- No admin UI for editing rules (Phase 8).

---

## Task 1: Generalize `BenefitRuleVersion` - nullable weeks, duration_until_birth, institution, deadlines

**Files:**
- Modify: `app/db/models/benefit_rule.py`
- Test: `tests/test_benefit_rule_models.py`

- [ ] **Step 1: Write the failing test**

Add this to the end of `tests/test_benefit_rule_models.py` (new imports are not needed - the file
already imports `BenefitRuleVersion`, `BenefitType`, `SessionLocal`, `date`, `Decimal`):

```python
def test_new_columns_have_safe_defaults_when_not_specified() -> None:
    db = SessionLocal()
    try:
        benefit_type = BenefitType(code="test_benefit_type_defaults", name="Test")
        db.add(benefit_type)
        db.flush()

        rule = BenefitRuleVersion(
            benefit_type_id=benefit_type.id,
            version=1,
            is_current=True,
            effective_from=date(2026, 1, 1),
            rate_percentage=Decimal("100.00"),
            weeks_by_child_count=None,
            debt_threshold_percent_of_min_wage=Decimal("1.00"),
            min_wage_reference_zl=Decimal("4806.00"),
            legal_basis=["test"],
            required_documents=[],
        )
        db.add(rule)
        db.flush()

        fetched = db.query(BenefitRuleVersion).filter_by(benefit_type_id=benefit_type.id).one()
        assert fetched.weeks_by_child_count is None
        assert fetched.duration_until_birth is False
        assert fetched.institution == "ZUS"
        assert fetched.deadlines == []
    finally:
        db.rollback()
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rm -f app.db && uv run pytest tests/test_benefit_rule_models.py::test_new_columns_have_safe_defaults_when_not_specified -v`
Expected: FAIL - either a `NOT NULL constraint failed: benefit_rule_versions.weeks_by_child_count`
error (weeks is still non-nullable) or an `AttributeError`/`TypeError` (the new columns don't exist
yet).

- [ ] **Step 3: Generalize the model**

In `app/db/models/benefit_rule.py`, change this line:

```python
    weeks_by_child_count: Mapped[dict] = mapped_column(JSON)
```

to:

```python
    weeks_by_child_count: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

Then add three new columns right after it (same class, `BenefitRuleVersion`):

```python
    duration_until_birth: Mapped[bool] = mapped_column(Boolean, default=False)
    institution: Mapped[str] = mapped_column(String(200), default="ZUS")
    deadlines: Mapped[list] = mapped_column(JSON, default=list)
```

Update the module docstring at the top of the file to document the new convention (append this
paragraph after the existing one):

```python
Czas trwania świadczenia jest wyrażany na jeden z dwóch sposobów (wzajemnie wykluczających się):
- ``weeks_by_child_count`` (słownik tygodni wg liczby dzieci) - typowy przypadek.
- ``duration_until_birth=True`` - świadczenie trwa "do dnia porodu"; wtedy
  ``weeks_by_child_count`` jest ``None``. Silnik (``app/eligibility/engine.py``) wybiera, które pole
  wypełnić w odpowiedzi na podstawie tej flagi.

``institution`` i ``deadlines`` są per-regule (nie per-silnik), ponieważ różne świadczenia mają różne
instytucje właściwe i różne terminy - np. "zasiłek w wysokości zasiłku macierzyńskiego" jest zawsze
wypłacany przez ZUS (nie pracodawcę), bo z definicji dotyczy sytuacji, w której stosunek pracy już
ustał.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rm -f app.db && uv run pytest tests/test_benefit_rule_models.py -v`
Expected: all tests in the file PASS, including the new one and the three pre-existing ones (they
don't set the new columns, so they must fall back to the defaults without error - this is exactly what
the new test and the model defaults together guarantee).

- [ ] **Step 5: Run the full test suite to check for unrelated breakage**

Run: `rm -f app.db && uv run pytest -q`
Expected: PASS (nothing else touches these columns yet, so no other test should be affected).

- [ ] **Step 6: Commit**

```bash
git add app/db/models/benefit_rule.py tests/test_benefit_rule_models.py
git commit -m "Generalize BenefitRuleVersion for non-weekly-duration benefits"
```

---

## Task 2: Carry institution/deadlines in the existing seed data

**Files:**
- Modify: `app/rules/seed.py`
- Test: `tests/test_rules_seed.py`

- [ ] **Step 1: Write the failing test**

Add this to `tests/test_rules_seed.py` (reuses the file's existing imports):

```python
def test_seeded_maternity_leave_rule_has_institution_and_deadlines() -> None:
    db = SessionLocal()
    try:
        ensure_seeded(db)

        rule = (
            db.query(BenefitRuleVersion)
            .join(BenefitType)
            .filter(
                BenefitType.code == MATERNITY_LEAVE_BENEFIT_CODE,
                BenefitRuleVersion.is_current.is_(True),
            )
            .one()
        )

        assert "Pracodawca" in rule.institution
        assert rule.deadlines
        assert rule.duration_until_birth is False
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rm -f app.db && uv run pytest tests/test_rules_seed.py::test_seeded_maternity_leave_rule_has_institution_and_deadlines -v`
Expected: FAIL with an `AttributeError` (the seeded rule has no explicit `institution`/`deadlines` set,
so it would currently fall back to the Task 1 defaults - `"ZUS"` doesn't contain `"Pracodawca"`, so the
first assertion fails).

- [ ] **Step 3: Add institution/deadlines to the seeded rule**

In `app/rules/seed.py`, inside the `BenefitRuleVersion(...)` call in `ensure_seeded`, add these two
keyword arguments (anywhere among the existing ones - e.g. right after `min_wage_reference_zl=...,`):

```python
        institution=(
            "Pracodawca (jeśli zgłasza powyżej 20 ubezpieczonych do ubezpieczenia "
            "chorobowego) albo ZUS"
        ),
        deadlines=[
            "Wniosek o urlop macierzyński - przed rozpoczęciem korzystania z urlopu (lub "
            "łącznie z wnioskiem o urlop rodzicielski)",
        ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rm -f app.db && uv run pytest tests/test_rules_seed.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/rules/seed.py tests/test_rules_seed.py
git commit -m "Carry institution and deadlines in the seeded maternity-leave rule"
```

---

## Task 3: Generalize `BenefitPlan`/`PossibleSolution` schemas and extract `_build_plan`/`_decide_status`

**Files:**
- Modify: `app/eligibility/schemas.py`
- Modify: `app/eligibility/engine.py`
- Test: `tests/test_eligibility_schemas.py`
- Test: `tests/test_eligibility_engine.py`

This task is a pure refactor plus a schema widening - it must not change any existing test's expected
output. Its job is to make room for Task 5's new evaluator without duplicating plan-building /
status-decision logic.

- [ ] **Step 1: Write the failing schema test**

Add this to `tests/test_eligibility_schemas.py` (reuses existing imports):

```python
def test_benefit_plan_supports_duration_description_instead_of_weeks() -> None:
    plan = BenefitPlan(
        weeks=None,
        duration_description="do dnia porodu",
        rate_percentage=Decimal("100"),
        institution="ZUS",
        required_documents=[],
        deadlines=["Niezwłocznie po ustaniu ubezpieczenia"],
        legal_basis=["ustawa zasiłkowa art. 30"],
    )

    payload = plan.model_dump_json()
    restored = BenefitPlan.model_validate_json(payload)

    assert restored.weeks is None
    assert restored.duration_description == "do dnia porodu"


def test_possible_solution_supports_related_benefit_code() -> None:
    solution = PossibleSolution(
        type=SolutionType.alternative_benefit,
        description="Sprawdź świadczenie X.",
        related_benefit_code="swiadczenie_x",
    )

    assert solution.related_benefit_code == "swiadczenie_x"


def test_possible_solution_related_benefit_code_defaults_to_none() -> None:
    solution = PossibleSolution(
        type=SolutionType.limitation,
        description="Brak podstawy.",
    )

    assert solution.related_benefit_code is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_eligibility_schemas.py -v`
Expected: FAIL with `pydantic.ValidationError` (`weeks` is still required / `duration_description` and
`related_benefit_code` are unknown fields, depending on Pydantic's extra-field behavior - either way,
not passing).

- [ ] **Step 3: Widen the schemas**

In `app/eligibility/schemas.py`, change `BenefitPlan.weeks`:

```python
    weeks: int = Field(description="Liczba tygodni, na które przysługuje świadczenie.")
```

to:

```python
    weeks: int | None = Field(
        default=None,
        description=(
            "Liczba tygodni, na które przysługuje świadczenie. Null, gdy czas trwania nie jest "
            "wyrażony w tygodniach - patrz duration_description."
        ),
    )
    duration_description: str | None = Field(
        default=None,
        description=(
            "Opis czasu trwania, gdy nie wyraża się go w tygodniach (np. 'do dnia porodu'). "
            "Null, gdy obowiązuje weeks."
        ),
    )
```

(Keep `weeks`'s position in the class as-is; add `duration_description` directly below it.)

In `PossibleSolution`, add a new field after `legal_basis`:

```python
    related_benefit_code: str | None = Field(
        default=None,
        description=(
            "Kod świadczenia, które warto sprawdzić osobno przez "
            "POST /eligibility/check/{benefit_code}, jeśli to rozwiązanie wskazuje na inne "
            "świadczenie niż to, którego dotyczy bieżąca ocena."
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_eligibility_schemas.py -v`
Expected: all PASS, including the pre-existing `test_eligibility_result_round_trips_through_json` (it
passes `weeks=20` explicitly, which still works since the field is now optional-with-default, not
removed).

- [ ] **Step 5: Write the failing engine refactor tests**

These tests describe the two extracted helpers' behavior through the existing public function (no new
public helper is exported - `_build_plan`/`_decide_status` are private, tested indirectly via
`evaluate_maternity_leave_eligibility`, exactly like every other branch in that function already is).
Add this to `tests/test_eligibility_engine.py` (reuses the file's existing `_make_rule()` fixture and
imports):

```python
def test_plan_institution_and_deadlines_come_from_the_rule_not_a_literal() -> None:
    rule = _make_rule()
    rule.institution = "Testowa instytucja"
    rule.deadlines = ["Testowy termin"]
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=True)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.plan.institution == "Testowa instytucja"
    assert result.plan.deadlines == ["Testowy termin"]
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_eligibility_engine.py::test_plan_institution_and_deadlines_come_from_the_rule_not_a_literal -v`
Expected: FAIL - `result.plan.institution` is currently the hardcoded "Pracodawca (...) albo ZUS"
literal, not `"Testowa instytucja"`.

- [ ] **Step 7: Extract `_decide_status` and `_build_plan`, source institution/deadlines from the rule**

In `app/eligibility/engine.py`, add these two functions directly after `_document_applies` (before
`evaluate_maternity_leave_eligibility`):

```python
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
```

Now replace the status-decision and plan-building block inside `evaluate_maternity_leave_eligibility`.
Find this (the tail end of the function, from `has_alternative = ...` through the `plan = BenefitPlan(...)` assignment, right before `return EligibilityResult(...)`):

```python
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
```

Replace it with:

```python
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
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `rm -f app.db && uv run pytest -q`
Expected: all tests PASS (33 pre-existing + the 4 new ones from this task = 37). This refactor must
not change behavior for any existing scenario - if any pre-existing `test_eligibility_engine.py` or
`test_eligibility_endpoint.py` test starts failing, you introduced a behavior change; fix the refactor,
not the test.

- [ ] **Step 9: Run lint**

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 10: Commit**

```bash
git add app/eligibility/schemas.py app/eligibility/engine.py tests/test_eligibility_schemas.py tests/test_eligibility_engine.py
git commit -m "Extract plan-building/status-decision helpers; widen BenefitPlan for non-weekly durations"
```

---

## Task 4: Seed the alternative benefit ("zasiłek w wysokości zasiłku macierzyńskiego")

**Files:**
- Modify: `app/rules/seed.py`
- Test: `tests/test_rules_seed.py`

- [ ] **Step 1: Write the failing test**

Add this to `tests/test_rules_seed.py`:

```python
def test_ensure_seeded_creates_alternative_benefit_rule() -> None:
    db = SessionLocal()
    try:
        ensure_seeded(db)
        ensure_seeded(db)  # must be idempotent, same as the maternity-leave rule

        rule = (
            db.query(BenefitRuleVersion)
            .join(BenefitType)
            .filter(
                BenefitType.code == ALTERNATIVE_BENEFIT_CODE,
                BenefitRuleVersion.is_current.is_(True),
            )
            .one()
        )

        assert rule.duration_until_birth is True
        assert rule.weeks_by_child_count is None
        assert rule.institution == "ZUS"
        assert rule.rate_percentage == Decimal("100.00")
        doc_codes = {doc["code"] for doc in rule.required_documents}
        assert "zaswiadczenie_z3" not in doc_codes
        assert "zaswiadczenie_z3a" not in doc_codes
    finally:
        db.close()
```

Add `ALTERNATIVE_BENEFIT_CODE` to the file's existing import line:

```python
from app.rules.seed import ALTERNATIVE_BENEFIT_CODE, MATERNITY_LEAVE_BENEFIT_CODE, ensure_seeded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rm -f app.db && uv run pytest tests/test_rules_seed.py::test_ensure_seeded_creates_alternative_benefit_rule -v`
Expected: FAIL with `ImportError: cannot import name 'ALTERNATIVE_BENEFIT_CODE'`.

- [ ] **Step 3: Refactor `ensure_seeded` into one-helper-per-benefit, add the alternative benefit**

In `app/rules/seed.py`, add the two new module-level constants right after the existing ones:

```python
ALTERNATIVE_BENEFIT_CODE = "zasilek_w_wysokosci_zasilku_macierzynskiego"
ALTERNATIVE_BENEFIT_NAME = "Zasiłek w wysokości zasiłku macierzyńskiego (po ustaniu ubezpieczenia w ciąży)"
```

Rename the existing `ensure_seeded` function to `_ensure_maternity_leave_seeded` (its signature line
changes from `def ensure_seeded(db: Session) -> None:` to
`def _ensure_maternity_leave_seeded(db: Session) -> None:` - the body below that line, everything from
`benefit_type = db.query(...)` through the final `db.commit()`, stays byte-for-byte identical; do not
retype it, just rename the `def` line in place). Then add a new top-level `ensure_seeded` directly
above it, and `_ensure_alternative_benefit_seeded` directly below it:

```python
def ensure_seeded(db: Session) -> None:
    _ensure_maternity_leave_seeded(db)
    _ensure_alternative_benefit_seeded(db)


def _ensure_alternative_benefit_seeded(db: Session) -> None:
    benefit_type = db.query(BenefitType).filter_by(code=ALTERNATIVE_BENEFIT_CODE).one_or_none()
    if benefit_type is None:
        benefit_type = BenefitType(
            code=ALTERNATIVE_BENEFIT_CODE,
            name=ALTERNATIVE_BENEFIT_NAME,
            description=(
                "Świadczenie przysługujące, gdy ubezpieczenie chorobowe ustało w okresie ciąży "
                "wskutek upadłości, likwidacji lub śmierci pracodawcy, albo rozwiązania umowy z "
                "naruszeniem przepisów prawa stwierdzonym prawomocnym wyrokiem sądu."
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
            "ustawa zasiłkowa art. 30 ust. 1 i ust. 3 (zasiłek w wysokości zasiłku "
            "macierzyńskiego po ustaniu ubezpieczenia w ciąży)",
            "ustawa zasiłkowa art. 31 ust. 1 (wysokość zasiłku - 100% podstawy wymiaru)",
        ],
        deadlines=[
            "Wniosek ZAM - jak najszybciej po ustaniu ubezpieczenia; roszczenie o zasiłek "
            "przedawnia się zgodnie z ustawą zasiłkową (art. 67) - sprawdź dokładny termin "
            "indywidualnie, nie jest on podany w dostępnych materiałach źródłowych.",
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
                    "Dokument potwierdzający przyczynę ustania ubezpieczenia (np. świadectwo "
                    "pracy ze wskazaniem przyczyny, prawomocny wyrok sądu)"
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rm -f app.db && uv run pytest tests/test_rules_seed.py -v`
Expected: all tests PASS, including the pre-existing `test_ensure_seeded_creates_exactly_one_current_rule`
(it only checks the maternity-leave benefit's count, unaffected by the new benefit existing alongside
it).

- [ ] **Step 5: Run the full suite**

Run: `rm -f app.db && uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/rules/seed.py tests/test_rules_seed.py
git commit -m "Seed zasiłek w wysokości zasiłku macierzyńskiego as its own benefit rule"
```

---

## Task 5: Implement `evaluate_alternative_maternity_benefit_eligibility`

**Files:**
- Modify: `app/eligibility/engine.py`
- Test: `tests/test_eligibility_engine.py`

- [ ] **Step 1: Write the failing tests**

Add these to `tests/test_eligibility_engine.py`. They need a rule fixture with
`duration_until_birth=True`; add this helper near the top of the file, right after `_make_rule()`:

```python
def _make_alternative_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count=None,
        duration_until_birth=True,
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        institution="ZUS",
        legal_basis=["ustawa zasiłkowa art. 30"],
        deadlines=["Jak najszybciej po ustaniu ubezpieczenia"],
        required_documents=[
            {"code": "wniosek_zam", "name": "Wniosek ZAM", "when": "...", "applies_to": None},
        ],
    )
```

**Correction (made after Task 4's review cross-checked the actual source PDF):** ustawa zasiłkowa
art. 30 ust. 3 - the legal basis for *this* benefit - only lists death/upadłość/likwidacja pracodawcy
as triggers. It does NOT include "rozwiązanie umowy z naruszeniem przepisów prawa stwierdzonym
prawomocnym orzeczeniem sądu" - that reason (art. 30 ust. 1 pkt 2) instead grants the *standard*
zasiłek macierzyński (the other, already-implemented benefit), not this "do dnia porodu" one. So
`naruszenie_prawa_wyrokiem_sadu` must NOT grant this benefit - it must be treated as not applicable
to it, with a `possible_solution` pointing back at the standard benefit's code instead. Test the two
reasons accordingly - one eligible, one not:

```python
def test_alternative_benefit_eligible_for_employer_liquidation() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.upadlosc_likwidacja_smierc_pracodawcy,
    )

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks is None
    assert result.plan.duration_description == "do dnia porodu"
    assert any("innego zatrudnienia" in w for w in result.warnings)


def test_alternative_benefit_not_applicable_for_unlawful_dismissal() -> None:
    """art. 30 ust. 3 (this benefit) does not list unlawful-termination-by-court-ruling as a
    trigger - only art. 30 ust. 1 pkt 2 does, which grants the *standard* benefit instead."""
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.naruszenie_prawa_wyrokiem_sadu,
    )

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.plan is None
    assert any(
        s.related_benefit_code == BENEFIT_CODE and s.type == SolutionType.alternative_benefit
        for s in result.possible_solutions
    )


def test_alternative_benefit_requires_verification_when_insured_status_unknown() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=None)

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.missing_data
    assert result.plan is None


def test_alternative_benefit_requires_verification_when_reason_unknown() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1, insured_at_birth=False, employment_ended_reason=None
    )

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.missing_data
    assert result.plan is None


def test_alternative_benefit_points_back_to_standard_benefit_when_still_insured() -> None:
    rule = _make_alternative_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=True)

    result = evaluate_alternative_maternity_benefit_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.plan is None
    assert any(
        s.related_benefit_code == BENEFIT_CODE and s.type == SolutionType.alternative_benefit
        for s in result.possible_solutions
    )
```

Update the file's existing `from app.eligibility.engine import ...` line to also import
`BENEFIT_CODE` and `evaluate_alternative_maternity_benefit_eligibility`:

```python
from app.eligibility.engine import (
    BENEFIT_CODE,
    evaluate_alternative_maternity_benefit_eligibility,
    evaluate_maternity_leave_eligibility,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_eligibility_engine.py -k alternative_benefit -v`
Expected: FAIL with `ImportError: cannot import name 'evaluate_alternative_maternity_benefit_eligibility'`.

- [ ] **Step 3: Implement the evaluator**

In `app/eligibility/engine.py`, add the new benefit's code/name constants to the existing import block
from `app.rules.seed` (change the two separate single-name imports into one block with four names):

```python
from app.rules.seed import (
    ALTERNATIVE_BENEFIT_CODE,
    ALTERNATIVE_BENEFIT_NAME,
    MATERNITY_LEAVE_BENEFIT_CODE as BENEFIT_CODE,
    MATERNITY_LEAVE_BENEFIT_NAME as BENEFIT_NAME,
)
```

Then add the new function at the end of the file (after `evaluate_maternity_leave_eligibility`):

```python
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
        warnings.append(
            "Świadczenie przysługuje dodatkowo tylko, gdy nie zapewniono innego zatrudnienia "
            "(ustawa zasiłkowa art. 30 ust. 3) - ta ocena nie weryfikuje tego warunku."
        )

    status = _decide_status(missing_data, unmet_conditions, solutions)

    is_standard_path_open = status == EligibilityStatus.likely_eligible or (
        status == EligibilityStatus.requires_verification and not unmet_conditions
    )
    plan = _build_plan(rule, request) if is_standard_path_open else None

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_eligibility_engine.py -v`
Expected: all tests PASS (existing + 5 new ones from this task).

- [ ] **Step 5: Run the full suite and lint**

Run: `rm -f app.db && uv run pytest -q && uv run ruff check .`
Expected: all PASS, `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add app/eligibility/engine.py tests/test_eligibility_engine.py
git commit -m "Add evaluate_alternative_maternity_benefit_eligibility"
```

---

## Task 6: Point the standard benefit's art. 30 solutions at the right benefit code

**Correction (made after Task 4/5's review cross-checked the actual source PDF):** the two art. 30
branches in `evaluate_maternity_leave_eligibility` are NOT both about the same alternative benefit.
`upadlosc_likwidacja_smierc_pracodawcy` (art. 30 ust. 3) genuinely grants the new "do dnia porodu"
benefit added in Task 4/5 - its solution should point there. `naruszenie_prawa_wyrokiem_sadu` (art. 30
ust. 1 pkt 2) grants the *standard* zasiłek macierzyński itself (the very benefit this function
evaluates) despite the ended insurance - its existing description text ("Zasiłek w wysokości zasiłku
macierzyńskiego... przysługuje, gdy rozwiązanie umowy...") is factually wrong (it names the *other*
benefit) and must be corrected to describe the standard benefit instead; it must NOT link to
`ALTERNATIVE_BENEFIT_CODE`, since that benefit's own evaluator (Task 5) now correctly treats this exact
reason as not applicable to it. (Whether this branch should eventually change `evaluate_maternity_leave_eligibility`'s *own* status from `unmet_conditions` to `met_conditions` - since art. 30 ust. 1
pkt 2 arguably means the standard condition IS met via this alternative legal basis - is a deeper
redesign deliberately deferred to a future task; this task only fixes the factually wrong text in the
solution it already includes, without changing the status-decision logic.)

**Files:**
- Modify: `app/eligibility/engine.py`
- Test: `tests/test_eligibility_engine.py`

- [ ] **Step 1: Write the failing tests**

Add these to `tests/test_eligibility_engine.py`:

```python
def test_employer_liquidation_solution_points_at_alternative_benefit_code() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.upadlosc_likwidacja_smierc_pracodawcy,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    solution = next(
        s for s in result.possible_solutions if s.type == SolutionType.alternative_benefit
    )
    assert solution.related_benefit_code == ALTERNATIVE_BENEFIT_CODE


def test_unlawful_dismissal_solution_does_not_point_at_alternative_benefit_code() -> None:
    """art. 30 ust. 1 pkt 2 (unlawful dismissal) grants the standard benefit itself, not the
    separate "do dnia porodu" benefit - its solution must not link to that other benefit's
    code, and must no longer claim that other benefit is what applies."""
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.naruszenie_prawa_wyrokiem_sadu,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    solution = next(
        s for s in result.possible_solutions if s.type == SolutionType.alternative_benefit
    )
    assert solution.related_benefit_code is None
    assert "zasiłku macierzyńskiego za okres urlopu macierzyńskiego" in solution.description
    assert ALTERNATIVE_BENEFIT_CODE not in solution.description
```

Add `ALTERNATIVE_BENEFIT_CODE` to the file's engine import block (added in Task 5's Step 1):

```python
from app.eligibility.engine import (
    ALTERNATIVE_BENEFIT_CODE,
    BENEFIT_CODE,
    evaluate_alternative_maternity_benefit_eligibility,
    evaluate_maternity_leave_eligibility,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_eligibility_engine.py -k "alternative_benefit_code" -v`
Expected: FAIL - the first test fails because `solution.related_benefit_code` is currently `None` (not
set in the `upadlosc_likwidacja_smierc_pracodawcy` branch's `PossibleSolution(...)` call). The second
test fails because the `naruszenie_prawa_wyrokiem_sadu` branch's description currently says "Zasiłek w
wysokości zasiłku macierzyńskiego..." (the wrong benefit's name) rather than describing the standard
benefit.

- [ ] **Step 3: Fix both art. 30 solutions**

In `app/eligibility/engine.py`, inside `evaluate_maternity_leave_eligibility`, find the
`upadlosc_likwidacja_smierc_pracodawcy` branch's `PossibleSolution(...)` call and add
`related_benefit_code=ALTERNATIVE_BENEFIT_CODE` as the last keyword argument:

```python
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
```

Then find the `naruszenie_prawa_wyrokiem_sadu` branch's `PossibleSolution(...)` call and replace it
entirely - its description was factually wrong (naming the other benefit) and it must not link to
`ALTERNATIVE_BENEFIT_CODE`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_eligibility_engine.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/eligibility/engine.py tests/test_eligibility_engine.py
git commit -m "Point each art. 30 solution at its actual applicable benefit"
```

---

## Task 7: Registry + generalized `/eligibility/check/{benefit_code}` endpoint

**Files:**
- Create: `app/eligibility/registry.py`
- Modify: `app/api/v1/endpoints/eligibility.py`
- Test: `tests/test_eligibility_endpoint.py` (full rewrite)
- Test: `tests/test_rules_repository.py`

- [ ] **Step 1: Write the failing tests (full rewrite of the endpoint test file)**

Replace the entire contents of `tests/test_eligibility_endpoint.py` with:

```python
from fastapi.testclient import TestClient

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"
ALTERNATIVE_BENEFIT_CODE = "zasilek_w_wysokosci_zasilku_macierzynskiego"


def test_check_eligibility_returns_likely_eligible_for_insured_mother(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] == 20
    assert body["benefit_code"] == MATERNITY_LEAVE_CODE


def test_check_eligibility_requires_verification_when_insurance_status_missing(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}", json={"children_count": 1}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_verification"
    assert body["missing_data"]


def test_check_eligibility_rejects_zero_children_count(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}", json={"children_count": 0}
    )

    assert response.status_code == 422


def test_check_eligibility_unknown_benefit_code_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/eligibility/check/nieistniejace_swiadczenie",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 404


def test_check_eligibility_alternative_benefit_for_employer_liquidation(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{ALTERNATIVE_BENEFIT_CODE}",
        json={
            "children_count": 1,
            "insured_at_birth": False,
            "employment_ended_reason": "upadlosc_likwidacja_smierc_pracodawcy",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] is None
    assert body["plan"]["duration_description"] == "do dnia porodu"
    assert body["benefit_code"] == ALTERNATIVE_BENEFIT_CODE
```

Also add one new test to `tests/test_rules_repository.py`. Add this new import line alongside its
existing imports (`ALTERNATIVE_BENEFIT_CODE` comes from `app.rules.seed`, a different module from the
file's existing `BENEFIT_CODE` import, so this is a separate `import` line, not an edit to the existing
one):

```python
from app.rules.seed import ALTERNATIVE_BENEFIT_CODE
```

Then append this test:

```python
def test_get_current_rule_returns_alternative_benefit_rule() -> None:
    db = SessionLocal()
    try:
        rule = get_current_rule(db, ALTERNATIVE_BENEFIT_CODE)
        assert rule.is_current is True
        assert rule.duration_until_birth is True
    finally:
        db.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rm -f app.db && uv run pytest tests/test_eligibility_endpoint.py tests/test_rules_repository.py -v`
Expected: FAIL - every `test_eligibility_endpoint.py` test gets a 404 (the route is still `/check`, not
`/check/{benefit_code}`), so the status-code assertions fail.

- [ ] **Step 3: Build the registry**

Create `app/eligibility/registry.py`:

```python
"""Rejestr dostępnych świadczeń: mapowanie kodu świadczenia na funkcję oceny.

Rozszerzenie silnika o nowe świadczenie (kolejne części Fazy 2) = dodanie wpisu tutaj,
po zaimplementowaniu funkcji oceny w ``app/eligibility/engine.py`` i zasileniu reguły w
``app/rules/seed.py``. Każdy zarejestrowany kod musi mieć odpowiadającą, aktualną wersję
reguły w bazie (patrz ``app/eligibility/rules_repository.py``) - w przeciwnym razie
``get_current_rule`` zgłosi ``NotFoundError`` mimo zarejestrowanego kodu.
"""

from collections.abc import Callable

from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.engine import (
    ALTERNATIVE_BENEFIT_CODE,
    BENEFIT_CODE,
    evaluate_alternative_maternity_benefit_eligibility,
    evaluate_maternity_leave_eligibility,
)
from app.eligibility.schemas import EligibilityResult, MaternityLeaveEligibilityRequest

EligibilityEvaluator = Callable[
    [MaternityLeaveEligibilityRequest, BenefitRuleVersion], EligibilityResult
]

ELIGIBILITY_EVALUATORS: dict[str, EligibilityEvaluator] = {
    BENEFIT_CODE: evaluate_maternity_leave_eligibility,
    ALTERNATIVE_BENEFIT_CODE: evaluate_alternative_maternity_benefit_eligibility,
}
```

- [ ] **Step 4: Generalize the endpoint**

Replace the full contents of `app/api/v1/endpoints/eligibility.py` with:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.eligibility.registry import ELIGIBILITY_EVALUATORS
from app.eligibility.rules_repository import get_current_rule
from app.eligibility.schemas import EligibilityResult, MaternityLeaveEligibilityRequest

router = APIRouter(prefix="/eligibility", tags=["eligibility"])


@router.post(
    "/check/{benefit_code}",
    response_model=EligibilityResult,
    summary="Oceń uprawnienie do wskazanego świadczenia",
)
async def check_eligibility(
    benefit_code: str, payload: MaternityLeaveEligibilityRequest, db: Session = Depends(get_db)
) -> EligibilityResult:
    evaluate = ELIGIBILITY_EVALUATORS.get(benefit_code)
    if evaluate is None:
        raise NotFoundError(f"Nieznany kod świadczenia: '{benefit_code}'")
    rule = get_current_rule(db, benefit_code)
    return evaluate(payload, rule)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `rm -f app.db && uv run pytest tests/test_eligibility_endpoint.py tests/test_rules_repository.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full suite and lint**

Run: `rm -f app.db && uv run pytest -q && uv run ruff check .`
Expected: all PASS, `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add app/eligibility/registry.py app/api/v1/endpoints/eligibility.py tests/test_eligibility_endpoint.py tests/test_rules_repository.py
git commit -m "Generalize eligibility endpoint to POST /eligibility/check/{benefit_code}"
```

---

## Task 8: Full verification, docstring update, and README update

**Files:**
- Modify: `app/eligibility/__init__.py`
- Modify: `README.md`

- [ ] **Step 1: Run the full test suite**

Run: `rm -f app.db && uv run pytest -q`
Expected: all tests pass (Phase 1's 35 + this plan's new tests).

- [ ] **Step 2: Run the full lint suite**

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 3: Update the package docstring**

In `app/eligibility/__init__.py`, replace:

```python
"""Silnik oceny uprawnień do świadczeń (Faza 1: jedno świadczenie - zasiłek
macierzyński za okres urlopu macierzyńskiego).
```

with:

```python
"""Silnik oceny uprawnień do świadczeń. Każde świadczenie ma własną funkcję oceny w
``engine.py`` i własny wpis w ``registry.py`` (kod świadczenia -> funkcja oceny), zasilany
własną wersją reguły w bazie (``app/rules/seed.py``). Obecnie obsługiwane: zasiłek
macierzyński za okres urlopu macierzyńskiego i zasiłek w wysokości zasiłku macierzyńskiego
(po ustaniu ubezpieczenia w ciąży, ustawa zasiłkowa art. 30).
```

(Keep the rest of the docstring - the paragraph about the 4-part result structure - unchanged.)

- [ ] **Step 4: Manual smoke test against a live server**

```bash
pkill -f "uvicorn app.main:app" 2>/dev/null
rm -f app.db
export PATH="$HOME/.local/bin:$PATH"
nohup uv run uvicorn app.main:app --port 8000 > /tmp/ebobo-dev-server.log 2>&1 &
disown
sleep 3
curl -s -X POST http://127.0.0.1:8000/api/v1/eligibility/check/zasilek_w_wysokosci_zasilku_macierzynskiego \
  -H "Content-Type: application/json" \
  -d '{"children_count": 1, "insured_at_birth": false, "employment_ended_reason": "upadlosc_likwidacja_smierc_pracodawcy"}'
```

Expected: a JSON body with `"status":"likely_eligible"`, `"plan":{"weeks":null,"duration_description":"do dnia porodu",...}`.

Also confirm the main benefit's solution now points at the new code:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/eligibility/check/zasilek_macierzynski_urlop_macierzynski \
  -H "Content-Type: application/json" \
  -d '{"children_count": 1, "insured_at_birth": false, "employment_ended_reason": "upadlosc_likwidacja_smierc_pracodawcy"}'
```

Expected: `"possible_solutions"` contains an entry with
`"related_benefit_code":"zasilek_w_wysokosci_zasilku_macierzynskiego"`.

Then stop the server: `pkill -f "uvicorn app.main:app"`

- [ ] **Step 5: Update README**

In `README.md`, find this paragraph under `## Status`:

```markdown
Obecnie gotowy jest szkielet aplikacji (konfiguracja, CORS, obsługa błędów,
Swagger, `GET /api/v1/health`) oraz pierwszy silnik uprawnień:
`POST /api/v1/eligibility/check` ocenia uprawnienie do zasiłku
macierzyńskiego za okres urlopu macierzyńskiego i zwraca ustrukturyzowaną
odpowiedź (status / uzasadnienie / możliwe rozwiązania / plan), zamiast
prostego tak/nie - łącznie z wykrywaniem alternatywnej ścieżki (zasiłek w
wysokości zasiłku macierzyńskiego) z ustawy zasiłkowej art. 30. Kolejne
świadczenia i moduły (kalkulator, upload/analiza PDF, integracje
ZUS/mObywatel) będą dodawane iteracyjnie w `app/services`, `app/eligibility`,
`app/rules` i `app/api/v1/endpoints`.
```

Replace it with:

```markdown
Obecnie gotowy jest szkielet aplikacji (konfiguracja, CORS, obsługa błędów,
Swagger, `GET /api/v1/health`) oraz silnik uprawnień obsługujący dwa
świadczenia przez wspólny, generyczny endpoint:
`POST /api/v1/eligibility/check/{benefit_code}` (**uwaga: zmiana kształtu
API względem wcześniejszej wersji** - poprzednio `POST /api/v1/eligibility/check`
bez kodu świadczenia w URL). Obsługiwane kody: `zasilek_macierzynski_urlop_macierzynski`
(zasiłek macierzyński za okres urlopu macierzyńskiego) i
`zasilek_w_wysokosci_zasilku_macierzynskiego` (alternatywna ścieżka z ustawy
zasiłkowej art. 30, dostępna gdy ubezpieczenie ustało w ciąży wskutek
upadłości/likwidacji/śmierci pracodawcy lub niezgodnego z prawem zwolnienia
potwierdzonego wyrokiem sądu). Każda odpowiedź ma tę samą ustrukturyzowaną
postać (status / uzasadnienie / możliwe rozwiązania / plan) zamiast prostego
tak/nie; `possible_solutions` może teraz wskazywać `related_benefit_code`
innego świadczenia do sprawdzenia osobno. Kolejne świadczenia i moduły
(kalkulator, upload/analiza PDF, integracje ZUS/mObywatel) będą dodawane
iteracyjnie w `app/services`, `app/eligibility`, `app/rules` i
`app/api/v1/endpoints`.
```

- [ ] **Step 6: Commit**

```bash
git add app/eligibility/__init__.py README.md
git commit -m "Document the generalized eligibility endpoint and alternative benefit"
```

---

## Self-review checklist (for whoever executes this plan)

- [ ] Every task's tests reference only types/fields defined in that task or an earlier one (no
  forward references).
- [ ] `ALTERNATIVE_BENEFIT_CODE`/`ALTERNATIVE_BENEFIT_NAME` are spelled identically everywhere they're
  used (seed.py, engine.py, registry.py, tests) - typos would silently produce a 404 at runtime
  instead of a Python-level error, since benefit codes are plain strings matched against DB rows.
- [ ] `evaluate_alternative_maternity_benefit_eligibility` does NOT port over the debt-threshold /
  self-employed document-filtering logic from `evaluate_maternity_leave_eligibility` - that logic
  belongs only to the standard benefit (see "Context for the engineer" above for why).
- [ ] No task hardcodes `institution`, `deadlines`, a rate, or a legal citation outside of
  `app/rules/seed.py` - if a task's engine code ever needs one of these values, it must come from the
  `rule` argument.
- [ ] The breaking URL change (`/check` -> `/check/{benefit_code}`) is called out explicitly in the
  final commit/README, not buried as an incidental diff.

## Known limitations (carried forward, not fixed by this plan)

- **`naruszenie_prawa_wyrokiem_sadu` status classification in `evaluate_maternity_leave_eligibility`
  (Task 6).** Art. 30 ust. 1 pkt 2 arguably means the standard benefit's condition IS met via this
  alternative legal basis (not merely "unmet, with an alternative solution"), since ust. 1 explicitly
  says the standard zasiłek macierzyński "przysługuje również" (still applies) for this reason. Today
  this still lands in `unmet_conditions` + a `SolutionType.alternative_benefit` entry whose `type`
  value is itself slightly misleading now that its description says "to jest to samo świadczenie"
  (the same benefit, not an alternative one) - flagged by Task 6's code quality review. Reclassifying
  this correctly would mean: (a) moving this branch to `met_conditions` instead of
  `unmet_conditions`/a solution entry, and (b) reconsidering whether `SolutionType` needs a value
  other than `alternative_benefit` for "this same benefit, via a less common legal basis, needs
  separate confirmation." This is a genuine redesign of `evaluate_maternity_leave_eligibility`'s
  status-decision logic (not just its `PossibleSolution` text) and was deliberately deferred to a
  future task rather than rushed into this one, per an explicit user decision made while executing
  this plan (chose "minimal fix now" over "full correction now" when this was first discovered during
  Task 4's review).
