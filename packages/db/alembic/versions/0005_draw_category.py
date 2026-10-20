"""draws.category: Draw Day follows the round kind that fits the learner's exams (French-language rounds for TEF,
Canadian Experience Class for IELTS only); existing rows were French-language rounds

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("draws", sa.Column("category", sa.String(length=32), nullable=False, server_default="french"))


def downgrade() -> None:
    op.drop_column("draws", "category")
