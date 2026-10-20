"""ledger.idempotency_key is unique per learner, not across learners: a day's streak reward (``streak:<day>``) was
paid to the first learner whose night ran and refused for everyone else

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_ledger_idempotency_key", "ledger", type_="unique")
    op.create_unique_constraint("uq_ledger_user_id_idempotency_key", "ledger", ["user_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_ledger_user_id_idempotency_key", "ledger", type_="unique")
    op.create_unique_constraint("uq_ledger_idempotency_key", "ledger", ["idempotency_key"])
