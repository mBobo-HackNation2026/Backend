"""Modele SQLAlchemy ORM. Importować tutaj każdy nowy model, aby Base.metadata
go widział (potrzebne do tworzenia tabel / migracji).
"""

from app.db.models.benefit_rule import BenefitRuleVersion, BenefitType

__all__ = ["BenefitRuleVersion", "BenefitType"]
