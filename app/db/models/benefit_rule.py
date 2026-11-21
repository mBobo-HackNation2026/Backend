"""Wersjonowane reguły świadczeń.

Konwencja wersjonowania (jedna linia na pole):
- ``version``: rosnący numer wersji reguły w obrębie jednego typu świadczenia.
- ``effective_from`` / ``effective_to``: zakres dat, w którym reguła obowiązuje
  (``effective_to`` = ``None`` oznacza brak końca obowiązywania).
- ``is_current``: znacznik wersji aktualnie używanej; co najwyżej jeden wiersz
  na ``benefit_type_id`` może mieć ``is_current=True`` (wymusza indeks częściowy).

Para ``(benefit_type_id, version)`` jest unikalna (wymusza ``UniqueConstraint``).

Czas trwania świadczenia jest wyrażany na jeden z dwóch sposobów (wzajemnie wykluczających się):
- ``weeks_by_child_count`` (słownik tygodni wg liczby dzieci) - typowy przypadek.
- ``duration_until_birth=True`` - świadczenie trwa "do dnia porodu"; wtedy
  ``weeks_by_child_count`` jest ``None``. Silnik (``app/eligibility/engine.py``) wybiera, które pole
  wypełnić w odpowiedzi na podstawie tej flagi.

``institution`` i ``deadlines`` są per-regule (nie per-silnik), ponieważ różne świadczenia mają różne
instytucje właściwe i różne terminy - np. "zasiłek w wysokości zasiłku macierzyńskiego" jest zawsze
wypłacany przez ZUS (nie pracodawcę), bo z definicji dotyczy sytuacji, w której stosunek pracy już
ustał.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
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
    __table_args__ = (
        UniqueConstraint("benefit_type_id", "version", name="uq_benefit_rule_version"),
        Index(
            "uq_benefit_rule_current",
            "benefit_type_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    benefit_type_id: Mapped[int] = mapped_column(ForeignKey("benefit_types.id"))
    version: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    rate_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    weeks_by_child_count: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_until_birth: Mapped[bool] = mapped_column(Boolean, default=False)
    institution: Mapped[str] = mapped_column(String(200), default="ZUS")
    deadlines: Mapped[list] = mapped_column(JSON, default=list)
    debt_threshold_percent_of_min_wage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    min_wage_reference_zl: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    legal_basis: Mapped[list] = mapped_column(JSON)
    required_documents: Mapped[list] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    benefit_type: Mapped[BenefitType] = relationship(back_populates="rule_versions")
