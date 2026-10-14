"""Alembic environment: async engine, metadata from ``lingard_db.models``, optional schema for tests."""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection

from lingard_db import models  # noqa: F401  (registers tables)
from lingard_db.base import Base, make_engine

config = context.config
url = config.attributes.get("database_url") or os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://lingard:lingard@localhost:55432/lingard"
)
schema = config.attributes.get("schema") or os.environ.get("DATABASE_SCHEMA")


def run_with(connection: Connection) -> None:
    # With a schema (tests, previews) the version table lives there too, so an already-migrated public schema
    # is never mistaken for this one.
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_type=True, version_table_schema=schema
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = make_engine(url, schema)
    async with engine.connect() as connection:
        if schema:
            await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            await connection.commit()
        await connection.run_sync(run_with)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
