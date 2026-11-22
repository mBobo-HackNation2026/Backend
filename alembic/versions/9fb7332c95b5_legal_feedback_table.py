"""legal feedback table

eBobo Legal Intelligence, Etap 2 Faza A: app/legal_feedback/ (zob.
app/db/models/legal_feedback.py dla pełnego opisu pól).

Revision ID: 9fb7332c95b5
Revises: 425efb53e2f9
Create Date: 2026-11-22 08:02:10.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9fb7332c95b5"
down_revision: str | Sequence[str] | None = "425efb53e2f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FEEDBACK_TYPES = (
    "incorrect_result",
    "missing_case",
    "incorrect_explanation",
    "zus_discrepancy",
    "missing_input",
)
_FEEDBACK_STATUSES = (
    "new",
    "under_review",
    "confirmed_issue",
    "not_an_issue",
    "needs_more_information",
    "closed",
)


def upgrade() -> None:
    op.create_table(
        "legal_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "request_log_entry_id",
            sa.Integer(),
            sa.ForeignKey("request_log_entries.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("benefit_code", sa.String(length=100), nullable=True),
        sa.Column(
            "feedback_type",
            sa.Enum(*_FEEDBACK_TYPES, name="legalfeedbacktype", native_enum=False, length=30),
            nullable=False,
        ),
        sa.Column("user_comment", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.String(length=30), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*_FEEDBACK_STATUSES, name="legalfeedbackstatus", native_enum=False, length=30),
            nullable=False,
            server_default="new",
        ),
        sa.Column("rules_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("legal_feedback")
