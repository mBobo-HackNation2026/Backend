"""Zgłoszenia wątpliwości co do wyniku oceny silnika uprawnień (eBobo Legal
Intelligence, Etap 2). Każde zgłoszenie odnosi się do dokładnie jednego,
niezmiennego wpisu w ``request_log_entries`` (``request_log_entry_id``) - nigdy nie
modyfikujemy tamtego wpisu, historia ocen zostaje nienaruszona.

Etap 2 Faza B dodaje dwa osobne, powiązane rekordy (nigdy nie nadpisywane pola na
``LegalFeedback`` samym):
- ``LegalFeedbackAnalysis`` - niezmienny wynik jednego uruchomienia analizy AI
  (``POST /admin/legal-feedback/{id}/analyze``). Można uruchomić wielokrotnie - każde
  uruchomienie to NOWY wiersz, pełna historia zostaje widoczna administratorowi.
  Samo powstanie analizy (nawet "completed") nigdy nie zmienia ``LegalFeedback.status``
  - to wyłącznie hipoteza do weryfikacji, status zmienia tylko administrator przez
  PATCH .../status.
- ``LegalFeedbackStatusHistory`` - jeden wiersz na każdą zmianę ``LegalFeedback.status``,
  z uzasadnieniem i tym, kto ją wykonał - audytowalność wymagana przez brief.
"""

import enum
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LegalFeedbackType(enum.StrEnum):
    incorrect_result = "incorrect_result"
    """Podejrzenie błędnej oceny."""
    missing_case = "missing_case"
    """Sytuacja nieobsługiwana przez silnik."""
    incorrect_explanation = "incorrect_explanation"
    """Problem z wyjaśnieniem prawnym (Legal Advisor)."""
    zus_discrepancy = "zus_discrepancy"
    """Rozbieżność z rzeczywistym rozstrzygnięciem/informacją ZUS."""
    missing_input = "missing_input"
    """Brak możliwości podania istotnej informacji."""


class LegalFeedbackStatus(enum.StrEnum):
    new = "new"
    under_review = "under_review"
    confirmed_issue = "confirmed_issue"
    not_an_issue = "not_an_issue"
    needs_more_information = "needs_more_information"
    closed = "closed"


class LegalFeedbackAnalysisStatus(enum.StrEnum):
    completed = "completed"
    """Model odpowiedział, odpowiedź przeszła walidację schematu."""
    failed = "failed"
    """Dostawca AI niedostępny, zły JSON, albo odpowiedź nie przeszła walidacji -
    ``classification``/``summary``/... zostają puste, nigdy nie są zmyślane."""


class LegalFeedbackAnalysisClassification(enum.StrEnum):
    missing_user_data = "missing_user_data"
    possible_rule_gap = "possible_rule_gap"
    possible_rule_error = "possible_rule_error"
    outdated_legal_source = "outdated_legal_source"
    possible_user_misunderstanding = "possible_user_misunderstanding"
    insufficient_evidence = "insufficient_evidence"


class LegalFeedback(Base):
    __tablename__ = "legal_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nigdy nie modyfikowany wpis, którego dotyczy zgłoszenie - własność zgłaszającego
    # jest wymuszona na poziomie serwisu (app/legal_feedback/service.py), nie tutaj.
    request_log_entry_id: Mapped[int] = mapped_column(ForeignKey("request_log_entries.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    benefit_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feedback_type: Mapped[LegalFeedbackType] = mapped_column(
        Enum(LegalFeedbackType, native_enum=False, length=30)
    )
    user_comment: Mapped[str] = mapped_column(Text)
    # Wyłącznie opinia zgłaszającego, nigdy nowa ocena uprawnienia - przechowywane jako
    # zwykły string (wartość EligibilityStatus, walidowana w app/legal_feedback/schemas.py),
    # nie powiązane z silnikiem w żaden inny sposób.
    expected_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[LegalFeedbackStatus] = mapped_column(
        Enum(LegalFeedbackStatus, native_enum=False, length=30), default=LegalFeedbackStatus.new
    )
    # Wersja reguł zastosowana przy ORYGINALNEJ ocenie (z request_log_entry.response_payload),
    # nie w momencie zgłoszenia feedbacku - potrzebne do oceny, czy problem dotyczy już
    # nieaktualnej wersji reguły.
    rules_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class LegalFeedbackAnalysis(Base):
    __tablename__ = "legal_feedback_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legal_feedback_id: Mapped[int] = mapped_column(ForeignKey("legal_feedback.id"))
    analysis_status: Mapped[LegalFeedbackAnalysisStatus] = mapped_column(
        Enum(LegalFeedbackAnalysisStatus, native_enum=False, length=20)
    )
    classification: Mapped[LegalFeedbackAnalysisClassification | None] = mapped_column(
        Enum(LegalFeedbackAnalysisClassification, native_enum=False, length=40), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    potential_issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_information: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Wyłącznie id fragmentów z app/legal_knowledge faktycznie zweryfikowane przez
    # backend (istniejące i dotyczące tego świadczenia) - niezweryfikowane cytaty AI są
    # tu po prostu pomijane, ten sam mechanizm co w app/legal_advisor/service.py.
    verified_source_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recommended_admin_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Zawsze True dla "completed" - wymuszane przez backend niezależnie od tego, co
    # zwróci model (hipoteza AI nigdy nie jest samopotwierdzającym się faktem).
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Bezpieczny komunikat diagnostyczny (nie surowy wyjątek/stack trace) - wyłącznie
    # dla analysis_status="failed".
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class LegalFeedbackStatusHistory(Base):
    __tablename__ = "legal_feedback_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legal_feedback_id: Mapped[int] = mapped_column(ForeignKey("legal_feedback.id"))
    old_status: Mapped[LegalFeedbackStatus] = mapped_column(
        Enum(LegalFeedbackStatus, native_enum=False, length=30)
    )
    new_status: Mapped[LegalFeedbackStatus] = mapped_column(
        Enum(LegalFeedbackStatus, native_enum=False, length=30)
    )
    changed_by: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
