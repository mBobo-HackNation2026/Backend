# Eligibility Engine v1 (Maternity Leave) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use it-subagent-driven-development (recommended) or it-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first end-to-end vertical slice of eBobo's core differentiator — an eligibility
engine that, for one benefit (zasiłek macierzyński za okres urlopu macierzyńskiego), returns a
structured assessment (status / uzasadnienie / możliwe rozwiązania / plan) instead of a yes/no
answer, including detection of the "ustanie ubezpieczenia w ciąży" alternative-benefit path (ustawa
zasiłkowa art. 30).

**Architecture:** Benefit rates/thresholds/legal citations live in two new versioned SQLAlchemy
tables (`benefit_types`, `benefit_rule_versions`) seeded once at startup. A new `app/eligibility/`
package holds pure, DB-free evaluation logic (`engine.py`) operating on Pydantic request/response
schemas, fed by a thin `rules_repository.py` that loads the current rule row. A new
`POST /api/v1/eligibility/check` endpoint wires DB → repository → engine → response. No auth
required (benefit lookups stay available without login, per the user's auth design).

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.1 (SQLite), pytest, Ruff — all already pinned in
`pyproject.toml`.

---

## Context for the engineer

Read these before starting — they explain *why* the rules below are what they are:

- `/Users/maksymilianpliszczynski/Backend/README.md` — project layout (`app/core`, `app/admin`,
  `app/auth`, `app/api/v1`, `app/schemas`, `app/services`, `app/rules`, `app/db`).
- `app/core/exceptions.py` — reuse `NotFoundError` for "rule not found", don't invent a new exception
  type.
- `app/db/base.py`, `app/db/session.py` — `Base`, `engine`, `SessionLocal`, `get_db()` dependency
  already exist. `Base.metadata.create_all(bind=engine)` already runs at import time in
  `session.py` — new models just need to be imported from `app/db/models/__init__.py` to be picked
  up by it.
- `app/auth/security.py` and `app/admin/security.py` — existing JWT dependency patterns, for
  reference only; this feature doesn't need auth.
- `pyproject.toml` → `[tool.ruff.lint.per-file-ignores]` — `"app/api/**"` already ignores `B008`
  (FastAPI's `Depends(...)` default-argument idiom), so the new endpoint file needs no new entry.

**Legal basis for the rules encoded below** (already verified against the source PDFs in
`resorces/`, see project memory `project-ebobo-legal-rules` for citations):
- Urlop macierzyński wymiar: 20/31/33/35/37 tygodni dla 1/2/3/4/5+ dzieci (Kodeks pracy art. 180 §1).
- Zasiłek macierzyński: 100% podstawy wymiaru za okres urlopu macierzyńskiego (ustawa zasiłkowa
  art. 31 ust. 1); prawo przysługuje ubezpieczonej, która w okresie ubezpieczenia chorobowego urodziła
  dziecko (art. 29 ust. 1 pkt 1) — **no waiting period** (okres wyczekiwania), unlike zasiłek
  chorobowy.
- Jeśli ubezpieczenie ustało w ciąży wskutek upadłości/likwidacji/śmierci pracodawcy, lub rozwiązania
  umowy z naruszeniem prawa stwierdzonym prawomocnym wyrokiem sądu → **zasiłek w wysokości zasiłku
  macierzyńskiego** (100% podstawy, do dnia porodu) jest dostępny jako odrębne świadczenie (ustawa
  zasiłkowa art. 30 ust. 1 i ust. 3). This is the "alternative benefit" path this engine surfaces.
- Zadłużenie składkowe > 1% minimalnego wynagrodzenia w dniu powstania prawa do świadczenia wyłącza
  prawo do zasiłku macierzyńskiego **tylko** dla osób prowadzących pozarolniczą działalność i
  współpracujących z nimi, duchownych, marynarzy (ustawa zasiłkowa art. 2a) — **not** for umowa o
  pracę or zlecenie. Spłata w ciągu 6 miesięcy od powstania prawa przywraca prawo (art. 2a ust. 2).

**Scope boundaries (don't build these now — they're later phases):**
- Only the mother's claim for urlop macierzyński itself. Father's claim, uzupełniający/rodzicielski
  leave, adoption/foster family, stillbirth, the 81,5% combined variant — all Phase 2.
- No `MockZUSProvider` data feed — all inputs are passed directly in the request body (Phase 4).
- No document upload — manual structured input only (Phase 5; note for later: the sample cases in
  `resorces/Sprawy/` are scanned image PDFs with no text layer, so that phase will need OCR, not
  plain PyMuPDF text extraction).
- No admin UI for editing the rule — the rule is seeded by code; admin CRUD is Phase 8.

---

## Task 1: Benefit rule DB models

**Files:**
- Create: `app/db/models/benefit_rule.py`
- Modify: `app/db/models/__init__.py`
- Test: `tests/test_benefit_rule_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_benefit_rule_models.py
from datetime import date
from decimal import Decimal

from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType
from app.db.session import SessionLocal


def test_create_and_query_benefit_rule_version() -> None:
    db = SessionLocal()
    try:
        benefit_type = BenefitType(
            code="test_benefit_type_roundtrip",
            name="Testowe świadczenie",
        )
        db.add(benefit_type)
        db.flush()

        rule = BenefitRuleVersion(
            benefit_type_id=benefit_type.id,
            version=1,
            is_current=True,
            effective_from=date(2026, 1, 1),
            rate_percentage=Decimal("100.00"),
            weeks_by_child_count={"1": 20},
            debt_threshold_percent_of_min_wage=Decimal("1.00"),
            min_wage_reference_zl=Decimal("4806.00"),
            legal_basis=["test"],
            required_documents=[{"code": "x", "name": "y", "when": "z"}],
        )
        db.add(rule)
        db.flush()

        fetched = (
            db.query(BenefitRuleVersion)
            .filter_by(benefit_type_id=benefit_type.id)
            .one()
        )
        assert fetched.weeks_by_child_count == {"1": 20}
        assert fetched.rate_percentage == Decimal("100.00")
        assert fetched.legal_basis == ["test"]
    finally:
        db.rollback()
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/maksymilianpliszczynski/Backend && export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_benefit_rule_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db.models.benefit_rule'`

- [ ] **Step 3: Write the model**

```python
# app/db/models/benefit_rule.py
from datetime import date, datetime, UTC
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BenefitType(Base):
    __tablename__ = "benefit_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    rule_versions: Mapped[list["BenefitRuleVersion"]] = relationship(back_populates="benefit_type")


class BenefitRuleVersion(Base):
    __tablename__ = "benefit_rule_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    benefit_type_id: Mapped[int] = mapped_column(ForeignKey("benefit_types.id"))
    version: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    rate_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    weeks_by_child_count: Mapped[dict] = mapped_column(JSON)
    debt_threshold_percent_of_min_wage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    min_wage_reference_zl: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    legal_basis: Mapped[list] = mapped_column(JSON)
    required_documents: Mapped[list] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    benefit_type: Mapped[BenefitType] = relationship(back_populates="rule_versions")
```

- [ ] **Step 4: Register the model so `Base.metadata` sees it**

In `app/db/models/__init__.py`, replace the full contents with:

```python
"""Modele SQLAlchemy ORM. Importować tutaj każdy nowy model, aby Base.metadata
go widział (potrzebne do tworzenia tabel / migracji).
"""

from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType

__all__ = ["BenefitRuleVersion", "BenefitType"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_benefit_rule_models.py -v`
Expected: PASS

- [ ] **Step 6: Lint**

Run: `uv run ruff check app/db/models/benefit_rule.py app/db/models/__init__.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add app/db/models/benefit_rule.py app/db/models/__init__.py tests/test_benefit_rule_models.py
git commit -m "Add versioned benefit rule DB models"
```

---

## Task 2: Seed data for the maternity leave benefit rule

**Files:**
- Create: `app/rules/seed.py`
- Modify: `app/db/session.py`
- Test: `tests/test_rules_seed.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rules_seed.py
from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType
from app.db.session import SessionLocal
from app.rules.seed import MATERNITY_LEAVE_BENEFIT_CODE, ensure_seeded


def test_ensure_seeded_creates_exactly_one_current_rule() -> None:
    db = SessionLocal()
    try:
        ensure_seeded(db)
        ensure_seeded(db)  # must be idempotent

        count = (
            db.query(BenefitRuleVersion)
            .join(BenefitType)
            .filter(
                BenefitType.code == MATERNITY_LEAVE_BENEFIT_CODE,
                BenefitRuleVersion.is_current.is_(True),
            )
            .count()
        )
        assert count == 1
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rules_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.rules.seed'`

- [ ] **Step 3: Write the seed function**

```python
# app/rules/seed.py
"""Dane startowe dla silnika uprawnień - jedno źródło prawdy dla stawek
i okresów, do czasu aż panel admina (Faza 8) nie przejmie ich edycji.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType

MATERNITY_LEAVE_BENEFIT_CODE = "zasilek_macierzynski_urlop_macierzynski"
MATERNITY_LEAVE_BENEFIT_NAME = "Zasiłek macierzyński za okres urlopu macierzyńskiego"


def ensure_seeded(db: Session) -> None:
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
        legal_basis=[
            "Kodeks pracy art. 180 §1 (wymiar urlopu macierzyńskiego wg liczby dzieci)",
            "ustawa zasiłkowa art. 29 ust. 1 pkt 1 (prawo do zasiłku macierzyńskiego)",
            "ustawa zasiłkowa art. 31 ust. 1 (wysokość zasiłku - 100% podstawy wymiaru)",
            "ustawa zasiłkowa art. 30 (zasiłek w wysokości zasiłku macierzyńskiego po ustaniu "
            "ubezpieczenia w ciąży)",
            "ustawa zasiłkowa art. 2a (wyłączenie prawa z powodu zadłużenia składkowego)",
        ],
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
            },
            {
                "code": "zaswiadczenie_z3",
                "name": "Zaświadczenie płatnika składek Z-3",
                "when": "gdy płatnikiem zasiłku jest ZUS, a nie pracodawca",
            },
            {
                "code": "akt_urodzenia",
                "name": "Skrócony odpis aktu urodzenia dziecka",
                "when": (
                    "po porodzie (niewymagany, jeśli płatnikiem jest ZUS - dane pozyskiwane są "
                    "z rejestru stanu cywilnego)"
                ),
            },
        ],
    )
    db.add(rule)
    db.commit()
```

- [ ] **Step 4: Call it at startup, right after table creation**

In `app/db/session.py`, the current end of the file reads:

```python
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

Change the import block at the top from:

```python
from app.core.config import get_settings
```

to:

```python
from app.core.config import get_settings
from app.db import models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base
from app.rules.seed import ensure_seeded
```

(no circular import here: `app.rules.seed` only imports from `app.db.models.benefit_rule`, which
only imports `app.db.base` — neither imports `app.db.session`)

and insert, right after `SessionLocal = sessionmaker(...)` and before `def get_db():`:

```python
Base.metadata.create_all(bind=engine)

with SessionLocal() as _seed_session:
    ensure_seeded(_seed_session)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `rm -f app.db && uv run pytest tests/test_rules_seed.py -v`
Expected: PASS

- [ ] **Step 6: Lint**

Run: `uv run ruff check app/rules/seed.py app/db/session.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add app/rules/seed.py app/db/session.py tests/test_rules_seed.py
git commit -m "Seed the maternity leave benefit rule at startup"
```

---

## Task 3: Eligibility request/response schemas

**Files:**
- Create: `app/eligibility/__init__.py`
- Create: `app/eligibility/schemas.py`
- Test: `tests/test_eligibility_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eligibility_schemas.py
import pytest
from pydantic import ValidationError

from app.eligibility.schemas import InsuranceTitle, MaternityLeaveEligibilityRequest


def test_children_count_must_be_at_least_one() -> None:
    with pytest.raises(ValidationError):
        MaternityLeaveEligibilityRequest(children_count=0)


def test_minimal_valid_request_defaults_optional_fields_to_none() -> None:
    request = MaternityLeaveEligibilityRequest(children_count=1)

    assert request.insured_at_birth is None
    assert request.insurance_title is None
    assert request.debt_amount_zl is None
    assert request.employment_ended_reason is None


def test_insurance_title_accepts_known_values() -> None:
    request = MaternityLeaveEligibilityRequest(
        children_count=1, insurance_title=InsuranceTitle.dzialalnosc_gospodarcza
    )

    assert request.insurance_title == InsuranceTitle.dzialalnosc_gospodarcza
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eligibility_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.eligibility'`

- [ ] **Step 3: Create the package**

```python
# app/eligibility/__init__.py
"""Silnik oceny uprawnień do świadczeń (Faza 1: jedno świadczenie - zasiłek
macierzyński za okres urlopu macierzyńskiego).

Wynik oceny ma zawsze 4 części: status, uzasadnienie (spełnione/niespełnione
warunki, brakujące dane), możliwe rozwiązania (dopuszczalne działania,
świadczenia alternatywne, ograniczenia) i plan (wnioski, załączniki,
instytucja, terminy, podstawa prawna). Nigdy nie udajemy decyzji ZUS - co
najwyżej wstępną ocenę.
"""
```

- [ ] **Step 4: Write the schemas**

```python
# app/eligibility/schemas.py
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class InsuranceTitle(StrEnum):
    umowa_o_prace = "umowa_o_prace"
    zlecenie = "zlecenie"
    dzialalnosc_gospodarcza = "dzialalnosc_gospodarcza"
    inny = "inny"


class EmploymentEndedReason(StrEnum):
    upadlosc_likwidacja_smierc_pracodawcy = "upadlosc_likwidacja_smierc_pracodawcy"
    naruszenie_prawa_wyrokiem_sadu = "naruszenie_prawa_wyrokiem_sadu"


class MaternityLeaveEligibilityRequest(BaseModel):
    children_count: int = Field(ge=1, description="Liczba dzieci urodzonych przy jednym porodzie")
    insured_at_birth: bool | None = Field(
        default=None,
        description=(
            "Czy wnioskodawczyni była objęta ubezpieczeniem chorobowym w dniu porodu. "
            "None = nieznane."
        ),
    )
    insurance_title: InsuranceTitle | None = Field(
        default=None, description="Tytuł ubezpieczenia, jeśli znany."
    )
    debt_amount_zl: Decimal | None = Field(
        default=None,
        description="Zadłużenie składkowe na dzień powstania prawa do zasiłku, jeśli dotyczy.",
    )
    employment_ended_reason: EmploymentEndedReason | None = Field(
        default=None,
        description=(
            "Jeśli insured_at_birth=False: powód ustania ubezpieczenia w okresie ciąży, "
            "o ile wystąpił."
        ),
    )


class EligibilityStatus(StrEnum):
    likely_eligible = "likely_eligible"
    not_eligible = "not_eligible"
    requires_verification = "requires_verification"


class SolutionType(StrEnum):
    alternative_benefit = "alternative_benefit"
    corrective_action = "corrective_action"
    limitation = "limitation"


class PossibleSolution(BaseModel):
    type: SolutionType
    description: str
    legal_basis: str | None = None


class RequiredDocument(BaseModel):
    code: str
    name: str
    when: str


class BenefitPlan(BaseModel):
    weeks: int
    rate_percentage: Decimal
    institution: str
    required_documents: list[RequiredDocument]
    deadlines: list[str]
    legal_basis: list[str]


class EligibilityResult(BaseModel):
    benefit_code: str
    benefit_name: str
    status: EligibilityStatus
    met_conditions: list[str]
    unmet_conditions: list[str]
    missing_data: list[str]
    possible_solutions: list[PossibleSolution]
    plan: BenefitPlan | None
    rules_version: int
    data_source: str = "user"
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_eligibility_schemas.py -v`
Expected: PASS

- [ ] **Step 6: Lint**

Run: `uv run ruff check app/eligibility/`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add app/eligibility/__init__.py app/eligibility/schemas.py tests/test_eligibility_schemas.py
git commit -m "Add eligibility request/response schemas"
```

---

## Task 4: Eligibility engine logic

**Files:**
- Create: `app/eligibility/engine.py`
- Test: `tests/test_eligibility_engine.py`

This is the core domain logic — a pure function, no DB or HTTP involved, so every scenario below is
a direct unit test.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_eligibility_engine.py
from datetime import date
from decimal import Decimal

from app.db.models.benefit_rule import BenefitRuleVersion
from app.eligibility.engine import evaluate_maternity_leave_eligibility
from app.eligibility.schemas import (
    EligibilityStatus,
    EmploymentEndedReason,
    InsuranceTitle,
    MaternityLeaveEligibilityRequest,
    SolutionType,
)


def _make_rule() -> BenefitRuleVersion:
    return BenefitRuleVersion(
        version=1,
        is_current=True,
        effective_from=date(2026, 1, 1),
        rate_percentage=Decimal("100.00"),
        weeks_by_child_count={"1": 20, "2": 31, "3": 33, "4": 35, "5+": 37},
        debt_threshold_percent_of_min_wage=Decimal("1.00"),
        min_wage_reference_zl=Decimal("4806.00"),
        legal_basis=["ustawa zasiłkowa art. 29"],
        required_documents=[{"code": "x", "name": "Wniosek", "when": "przed urlopem"}],
    )


def test_insured_mother_one_child_is_likely_eligible() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=True)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible
    assert result.plan is not None
    assert result.plan.weeks == 20
    assert result.plan.rate_percentage == Decimal("100.00")
    assert not result.unmet_conditions
    assert not result.missing_data


def test_insured_mother_twins_gets_31_weeks() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=2, insured_at_birth=True)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.plan is not None
    assert result.plan.weeks == 31


def test_not_insured_with_no_special_reason_is_not_eligible() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=False)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert result.plan is None
    assert any(s.type == SolutionType.limitation for s in result.possible_solutions)


def test_not_insured_due_to_employer_liquidation_requires_verification() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=False,
        employment_ended_reason=EmploymentEndedReason.upadlosc_likwidacja_smierc_pracodawcy,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert any(
        s.type == SolutionType.alternative_benefit and "art. 30" in (s.legal_basis or "")
        for s in result.possible_solutions
    )


def test_unknown_insurance_status_requires_verification_with_missing_data() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(children_count=1, insured_at_birth=None)

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.missing_data


def test_self_employed_with_debt_over_threshold_is_not_eligible() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        debt_amount_zl=Decimal("100.00"),
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.not_eligible
    assert any(s.type == SolutionType.corrective_action for s in result.possible_solutions)


def test_self_employed_with_debt_under_threshold_is_eligible() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        debt_amount_zl=Decimal("10.00"),
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.likely_eligible


def test_self_employed_missing_debt_info_requires_verification() -> None:
    rule = _make_rule()
    request = MaternityLeaveEligibilityRequest(
        children_count=1,
        insured_at_birth=True,
        insurance_title=InsuranceTitle.dzialalnosc_gospodarcza,
        debt_amount_zl=None,
    )

    result = evaluate_maternity_leave_eligibility(request, rule)

    assert result.status == EligibilityStatus.requires_verification
    assert result.missing_data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_eligibility_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.eligibility.engine'`

- [ ] **Step 3: Write the engine**

```python
# app/eligibility/engine.py
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

BENEFIT_CODE = "zasilek_macierzynski_urlop_macierzynski"
BENEFIT_NAME = "Zasiłek macierzyński za okres urlopu macierzyńskiego"

_SELF_EMPLOYED_LIKE_TITLES = {InsuranceTitle.dzialalnosc_gospodarcza}


def _weeks_for_children_count(weeks_by_child_count: dict, children_count: int) -> int:
    key = str(children_count) if children_count < 5 else "5+"
    return weeks_by_child_count[key]


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
        elif request.employment_ended_reason == EmploymentEndedReason.naruszenie_prawa_wyrokiem_sadu:
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

    if missing_data:
        status = EligibilityStatus.requires_verification
    elif unmet_conditions and has_alternative:
        status = EligibilityStatus.requires_verification
    elif unmet_conditions:
        status = EligibilityStatus.not_eligible
    else:
        status = EligibilityStatus.likely_eligible

    plan = None
    if status != EligibilityStatus.not_eligible:
        weeks = _weeks_for_children_count(rule.weeks_by_child_count, request.children_count)
        plan = BenefitPlan(
            weeks=weeks,
            rate_percentage=rule.rate_percentage,
            institution=(
                "Pracodawca (jeśli zgłasza powyżej 20 ubezpieczonych do ubezpieczenia "
                "chorobowego) albo ZUS"
            ),
            required_documents=[RequiredDocument(**doc) for doc in rule.required_documents],
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
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_eligibility_engine.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Lint**

Run: `uv run ruff check app/eligibility/engine.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add app/eligibility/engine.py tests/test_eligibility_engine.py
git commit -m "Add maternity leave eligibility evaluation engine"
```

---

## Task 5: Rules repository (DB lookup)

**Files:**
- Create: `app/eligibility/rules_repository.py`
- Test: `tests/test_rules_repository.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rules_repository.py
import pytest

from app.core.exceptions import NotFoundError
from app.db.session import SessionLocal
from app.eligibility.engine import BENEFIT_CODE
from app.eligibility.rules_repository import get_current_rule


def test_get_current_rule_returns_seeded_rule() -> None:
    db = SessionLocal()
    try:
        rule = get_current_rule(db, BENEFIT_CODE)
        assert rule.is_current is True
    finally:
        db.close()


def test_get_current_rule_raises_not_found_for_unknown_code() -> None:
    db = SessionLocal()
    try:
        with pytest.raises(NotFoundError):
            get_current_rule(db, "nieistniejace_swiadczenie")
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rules_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.eligibility.rules_repository'`

- [ ] **Step 3: Write the repository**

```python
# app/eligibility/rules_repository.py
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType


def get_current_rule(db: Session, benefit_code: str) -> BenefitRuleVersion:
    rule = (
        db.query(BenefitRuleVersion)
        .join(BenefitType)
        .filter(BenefitType.code == benefit_code, BenefitRuleVersion.is_current.is_(True))
        .one_or_none()
    )
    if rule is None:
        raise NotFoundError(f"Brak aktualnych reguł dla świadczenia '{benefit_code}'")
    return rule
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rules_repository.py -v`
Expected: PASS

- [ ] **Step 5: Lint**

Run: `uv run ruff check app/eligibility/rules_repository.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add app/eligibility/rules_repository.py tests/test_rules_repository.py
git commit -m "Add benefit rule repository with NotFoundError handling"
```

---

## Task 6: API endpoint

**Files:**
- Create: `app/api/v1/endpoints/eligibility.py`
- Modify: `app/api/v1/router.py`
- Test: `tests/test_eligibility_endpoint.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_eligibility_endpoint.py
from fastapi.testclient import TestClient


def test_check_eligibility_returns_likely_eligible_for_insured_mother(client: TestClient) -> None:
    response = client.post(
        "/api/v1/eligibility/check",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] == 20
    assert body["benefit_code"] == "zasilek_macierzynski_urlop_macierzynski"


def test_check_eligibility_requires_verification_when_insurance_status_missing(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/eligibility/check", json={"children_count": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_verification"
    assert body["missing_data"]


def test_check_eligibility_rejects_zero_children_count(client: TestClient) -> None:
    response = client.post("/api/v1/eligibility/check", json={"children_count": 0})

    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_eligibility_endpoint.py -v`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Write the endpoint**

```python
# app/api/v1/endpoints/eligibility.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.eligibility.engine import BENEFIT_CODE, evaluate_maternity_leave_eligibility
from app.eligibility.rules_repository import get_current_rule
from app.eligibility.schemas import EligibilityResult, MaternityLeaveEligibilityRequest

router = APIRouter(prefix="/eligibility", tags=["eligibility"])


@router.post(
    "/check",
    response_model=EligibilityResult,
    summary="Oceń uprawnienie do zasiłku macierzyńskiego za okres urlopu macierzyńskiego",
)
async def check_eligibility(
    payload: MaternityLeaveEligibilityRequest, db: Session = Depends(get_db)
) -> EligibilityResult:
    rule = get_current_rule(db, BENEFIT_CODE)
    return evaluate_maternity_leave_eligibility(payload, rule)
```

- [ ] **Step 4: Wire it into the v1 router**

In `app/api/v1/router.py`, change:

```python
from app.api.v1.endpoints import admin, health

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(admin.router)

# Kolejne moduły API będą podpinane tutaj w miarę implementacji:
# - calculator    -> kalkulator świadczeń (rodzaje zasiłków, kwoty, okresy)
# - eligibility   -> weryfikacja uprawnień wnioskodawcy
# - documents     -> upload i analiza PDF (PyMuPDF)
# - integrations  -> symulowane integracje ZUS / mObywatel
```

to:

```python
from app.api.v1.endpoints import admin, eligibility, health

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(admin.router)
api_router.include_router(eligibility.router)

# Kolejne moduły API będą podpinane tutaj w miarę implementacji:
# - calculator    -> kalkulator świadczeń (rodzaje zasiłków, kwoty, okresy)
# - documents     -> upload i analiza PDF (PyMuPDF)
# - integrations  -> symulowane integracje ZUS / mObywatel
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_eligibility_endpoint.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Lint**

Run: `uv run ruff check app/api/v1/endpoints/eligibility.py app/api/v1/router.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add app/api/v1/endpoints/eligibility.py app/api/v1/router.py tests/test_eligibility_endpoint.py
git commit -m "Add POST /api/v1/eligibility/check endpoint"
```

---

## Task 7: Full verification and README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full test suite**

Run: `rm -f app.db && uv run pytest -q`
Expected: all tests pass (skeleton + eligibility tests combined)

- [ ] **Step 2: Run the full lint suite**

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 3: Manual smoke test against a live server**

```bash
pkill -f "uvicorn app.main:app" 2>/dev/null
rm -f app.db
export PATH="$HOME/.local/bin:$PATH"
nohup uv run uvicorn app.main:app --port 8000 > /tmp/ebobo-dev-server.log 2>&1 &
disown
sleep 3
curl -s -X POST http://127.0.0.1:8000/api/v1/eligibility/check \
  -H "Content-Type: application/json" \
  -d '{"children_count": 1, "insured_at_birth": true}'
```

Expected: a JSON body with `"status":"likely_eligible"` and `"plan":{"weeks":20,...}`.

Then stop the server: `pkill -f "uvicorn app.main:app"`

- [ ] **Step 4: Update README**

In `README.md`, find this paragraph under `## Status`:

```markdown
Obecnie gotowy jest szkielet aplikacji: konfiguracja, CORS, obsługa błędów,
Swagger oraz `GET /api/v1/health`. Moduły domenowe (kalkulator świadczeń,
weryfikacja uprawnień, upload/analiza PDF, integracje ZUS/mObywatel) będą
dodawane iteracyjnie w `app/services`, `app/rules` i `app/api/v1/endpoints`.
```

Replace it with:

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

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "Document the eligibility engine in README"
```

---

## Self-review checklist (for whoever executes this plan)

- [ ] Every task's tests reference only types/fields defined in that task or an earlier one (no
  forward references).
- [ ] `EligibilityStatus`, `SolutionType`, `InsuranceTitle`, `EmploymentEndedReason` are spelled
  identically everywhere they're used (schemas, engine, tests) — they're `StrEnum`, so a typo would
  silently produce a different string value instead of a `NameError`.
- [ ] `rule.weeks_by_child_count` keys are strings (`"1"`..`"4"`, `"5+"`) everywhere, because SQLite's
  JSON column round-trips through actual JSON, which only allows string object keys.
- [ ] No task hardcodes a benefit rate or legal citation outside of `app/rules/seed.py` — if Task 4's
  engine ever needs a new number, it must come from the `rule` argument, not a literal.
