"""users.ui_locale may be unset: a new learner's interface language is chosen, not assumed to be English

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "ui_locale", existing_type=sa.String(length=8), nullable=True, server_default=None)


def downgrade() -> None:
    op.execute("UPDATE users SET ui_locale = 'en' WHERE ui_locale IS NULL")
    op.alter_column("users", "ui_locale", existing_type=sa.String(length=8), nullable=False)
