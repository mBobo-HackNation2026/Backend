"""eBobo Legal Intelligence, Etap 3: wewnętrzny monitoring jakości silnika i kolejka
przypadków do weryfikacji przez pracownika - niezależny od tego, czy użytkownik
cokolwiek zgłosił (zob. pamięć projektu `project-ebobo-legal-intelligence-two-tier-
direction`: wolumen zgłoszeń użytkowników to sygnał, nigdy dowód błędu prawnego;
silnik i wewnętrzny monitoring mają też same identyfikować sytuacje do przeglądu).

Każdy ``EngineQualityCase`` to jeden, grupowany sygnał (``group_key`` = typ sygnału +
świadczenie + wersja reguły - nigdy dane osobowe) - powtarzające się wystąpienia tego
samego sygnału nie tworzą nowych wierszy, tylko inkrementują ``occurrence_count`` na
już istniejącym, otwartym przypadku (zob. ``app/engine_quality/service.py:record_signal``).
Nigdy nie duplikuje danych z ``request_log``/``legal_feedback`` - tylko referencje
(``request_log_entry_id``/``legal_feedback_id``, oba nullable).
"""

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Statusy traktowane jako "zamknięte" - sygnał, który wróci po zamknięciu/odrzuceniu
# sprawy, zaczyna nową grupę zamiast cicho nadpisywać decyzję pracownika (zob.
# app/engine_quality/service.py:record_signal).
_CLOSED_STATUSES_SQL = "'not_an_issue','closed'"


class EngineQualitySignalType(enum.StrEnum):
    missing_legal_knowledge = "missing_legal_knowledge"
    """Brak fragmentów app/legal_knowledge dla danego świadczenia."""
    unsupported_case = "unsupported_case"
    """Silnik jawnie wskazuje nieobsługiwany przypadek (np. nieznany kod świadczenia)."""
    repeated_unresolved_case = "repeated_unresolved_case"
    """Podobna sytuacja powtarza się wielokrotnie bez rozstrzygnięcia - realizowane jako
    automatyczna eskalacja priorytetu przy przekroczeniu progu occurrence_count, zob.
    app/engine_quality/service.py, nie jako osobno wyzwalany sygnał."""
    user_reported_discrepancy = "user_reported_discrepancy"
    """Istniejące zgłoszenie użytkownika (app/legal_feedback, Etap 2 Faza A)."""
    legal_source_validation_failure = "legal_source_validation_failure"
    """Analiza prawna (Legal Advisor albo Faza B) nie przeszła walidacji źródeł -
    MVP Etap 3 definiuje ten typ, ale celowo NIE podłącza jeszcze żadnego wyzwalacza
    (brief §8: "pozostałe rodzaje dodawaj dopiero po sprawdzeniu jakości sygnałów z MVP")."""


class EngineQualityCasePriority(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class EngineQualityCaseStatus(enum.StrEnum):
    new = "new"
    under_review = "under_review"
    confirmed_issue = "confirmed_issue"
    not_an_issue = "not_an_issue"
    closed = "closed"


class EngineQualityCase(Base):
    __tablename__ = "engine_quality_cases"
    __table_args__ = (
        # Zabezpieczenie przed wyścigiem żądań (Etap 3.1 §3): dwa równoczesne żądania,
        # które oba nie widzą jeszcze istniejącego przypadku, nie mogą obie wstawić
        # wiersza z tym samym group_key dla wciąż otwartej sprawy - baza odrzuci drugą
        # próbę (app/engine_quality/service.py łapie to i dogrywa jako update).
        # Zamknięte/odrzucone sprawy (not_an_issue/closed) są wyłączone z tego
        # ograniczenia, żeby powrót tego samego sygnału mógł zacząć nową grupę.
        Index(
            "uq_engine_quality_case_open_group_key",
            "group_key",
            unique=True,
            sqlite_where=text(f"status NOT IN ({_CLOSED_STATUSES_SQL})"),
            postgresql_where=text(f"status NOT IN ({_CLOSED_STATUSES_SQL})"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_type: Mapped[EngineQualitySignalType] = mapped_column(
        Enum(EngineQualitySignalType, native_enum=False, length=40)
    )
    benefit_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rules_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Stabilny identyfikator KONKRETNEGO problemu, gdy dostępny (np.
    # LegalLimitationMarker.rule_id) - rozróżnia różne problemy w obrębie tego samego
    # świadczenia/wersji reguły, które inaczej zlałyby się w jedną grupę (Etap 3.1 §3).
    # Null, gdy sygnał nie ma takiego drobniejszego podziału (np. unsupported_case dla
    # nieznanego kodu świadczenia - sam kod już jednoznacznie identyfikuje problem).
    problem_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    request_log_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("request_log_entries.id"), nullable=True
    )
    legal_feedback_id: Mapped[int | None] = mapped_column(
        ForeignKey("legal_feedback.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text)
    # signal_type:benefit_code:rules_version:problem_id - deterministyczny klucz
    # grupowania, nigdy dane osobowe. Zob. app/engine_quality/service.py:_compute_group_key.
    group_key: Mapped[str] = mapped_column(String(250))
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[EngineQualityCasePriority] = mapped_column(
        Enum(EngineQualityCasePriority, native_enum=False, length=10),
        default=EngineQualityCasePriority.medium,
    )
    status: Mapped[EngineQualityCaseStatus] = mapped_column(
        Enum(EngineQualityCaseStatus, native_enum=False, length=20),
        default=EngineQualityCaseStatus.new,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class EngineQualityCaseHistory(Base):
    """Jeden wiersz na każdą zmianę statusu albo priorytetu - audytowalność (brief §5)."""

    __tablename__ = "engine_quality_case_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("engine_quality_cases.id"))
    field_changed: Mapped[str] = mapped_column(String(20))  # "status" | "priority"
    old_value: Mapped[str] = mapped_column(String(40))
    new_value: Mapped[str] = mapped_column(String(40))
    changed_by: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class EngineQualityCaseAnalysis(Base):
    """Niezmienny wynik jednego uruchomienia analizy AI dla sprawy - ten sam kształt i te
    same zasady co ``LegalFeedbackAnalysis`` (Etap 2 Faza B), celowo osobna tabela: sprawa
    może w ogóle nie mieć powiązanego zgłoszenia użytkownika (np. missing_legal_knowledge
    wykryte wyłącznie przez silnik)."""

    __tablename__ = "engine_quality_case_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engine_quality_case_id: Mapped[int] = mapped_column(ForeignKey("engine_quality_cases.id"))
    analysis_status: Mapped[str] = mapped_column(String(20))  # "completed" | "failed"
    classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    potential_issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_information: Mapped[list | None] = mapped_column(JSON, nullable=True)
    verified_source_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recommended_admin_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
