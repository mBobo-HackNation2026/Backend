"""Zgłoszenia wątpliwości co do wyniku oceny silnika uprawnień (eBobo Legal
Intelligence, Etap 2). Każde zgłoszenie odnosi się do dokładnie jednego,
niezmiennego wpisu w ``request_log_entries`` (``request_log_entry_id``) - nigdy nie
modyfikujemy tamtego wpisu, historia ocen zostaje nienaruszona. Analiza AI i
decyzja administratora (Etap 2, Faza B - jeszcze niezaimplementowana) będą
osobnymi, powiązanymi rekordami, nie polami nadpisywanymi na tym."""

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
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
