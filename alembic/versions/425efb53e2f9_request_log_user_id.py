"""request log user id

Nullable, opportunistic ownership column (zob. app/legal_feedback/ - zgłoszenie
feedbacku musi móc bezpiecznie sprawdzić, czy wpis request_log należy do
zgłaszającej sesji). Istniejące wiersze dostają user_id=NULL - nigdy nie są
retrofitowane do przypadkowego użytkownika (zob. brief Etap 2 Faza B, pkt 3).

Revision ID: 425efb53e2f9
Revises: 4e7573eced51
Create Date: 2026-11-22 08:01:41.941486

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "425efb53e2f9"
down_revision: str | Sequence[str] | None = "4e7573eced51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("request_log_entries") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("request_log_entries") as batch_op:
        batch_op.drop_column("user_id")
