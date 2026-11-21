"""Wersjonowane reguły świadczeń.

Konwencja wersjonowania (jedna linia na pole):
- ``version``: rosnący numer wersji reguły w obrębie jednego typu świadczenia.
- ``effective_from`` / ``effective_to``: zakres dat, w którym reguła obowiązuje
  (``effective_to`` = ``None`` oznacza brak końca obowiązywania).
- ``is_current``: znacznik wersji aktualnie używanej; co najwyżej jeden wiersz
  na ``benefit_type_id`` może mieć ``is_current=True`` (wymusza indeks częściowy).

Para ``(benefit_type_id, version)`` jest unikalna (wymusza ``UniqueConstraint``).
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
    weeks_by_child_count: Mapped[dict] = mapped_column(JSON)
    debt_threshold_percent_of_min_wage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    min_wage_reference_zl: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    legal_basis: Mapped[list] = mapped_column(JSON)
    required_documents: Mapped[list] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    benefit_type: Mapped[BenefitType] = relationship(back_populates="rule_versions")
