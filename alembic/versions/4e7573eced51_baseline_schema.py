"""baseline schema

Odtwarza schemat bazy dokładnie w takim kształcie, w jakim istniał PRZED dodaniem
kolumny ``request_log_entries.user_id`` (migracja ``0002``) - czyli dokładnie
"starą" bazę, która dziś spowodowała ``no such column: request_log_entries.user_id``
przy ręcznej, bezmigracyjnej zmianie modelu. Celowo pisana ręcznie (nie
autogenerate), żeby migracje 0001-0002 dawały razem realny test "stara baza z
danymi przeżywa aktualizację schematu" (zob. tests/test_db_migrations.py).

Revision ID: 4e7573eced51
Revises:
Create Date: 2026-11-22 08:01:07.400314

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e7573eced51"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "benefit_types",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "benefit_rule_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "benefit_type_id", sa.Integer(), sa.ForeignKey("benefit_types.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("rate_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("lump_sum_amount_zl", sa.Numeric(10, 2), nullable=True),
        sa.Column("weeks_by_child_count", sa.JSON(), nullable=True),
        sa.Column("weeks_by_child_count_za_zyciem", sa.JSON(), nullable=True),
        sa.Column("duration_until_birth", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("institution", sa.String(length=200), nullable=False, server_default="ZUS"),
        sa.Column("deadlines", sa.JSON(), nullable=False),
        sa.Column("debt_threshold_percent_of_min_wage", sa.Numeric(5, 2), nullable=False),
        sa.Column("min_wage_reference_zl", sa.Numeric(10, 2), nullable=False),
        sa.Column("legal_basis", sa.JSON(), nullable=False),
        sa.Column("required_documents", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("benefit_type_id", "version", name="uq_benefit_rule_version"),
    )
    op.create_index(
        "uq_benefit_rule_current",
        "benefit_rule_versions",
        ["benefit_type_id"],
        unique=True,
        sqlite_where=sa.text("is_current = 1"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "status",
            sa.Enum("anonymous", "authenticated", name="authstatus", native_enum=False, length=20),
            nullable=False,
            server_default="anonymous",
        ),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("pesel", sa.String(length=11), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("authenticated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "request_log_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("endpoint", sa.String(length=100), nullable=False),
        sa.Column("benefit_code", sa.String(length=100), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("request_log_entries")
    op.drop_table("users")
    op.drop_index("uq_benefit_rule_current", table_name="benefit_rule_versions")
    op.drop_table("benefit_rule_versions")
    op.drop_table("benefit_types")
