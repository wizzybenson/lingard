"""Run Alembic migrations programmatically (``python -m lingard_db.migrate``)."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def migrate(database_url: str, schema: str | None = None, revision: str = "head") -> None:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = database_url
    config.attributes["schema"] = schema
    command.upgrade(config, revision)


if __name__ == "__main__":
    migrate(
        os.environ.get("DATABASE_URL", "postgresql+psycopg://lingard:lingard@localhost:55432/lingard"),
        os.environ.get("DATABASE_SCHEMA"),
    )
