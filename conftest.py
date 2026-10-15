"""Shared fixtures. Integration fixtures skip cleanly when docker services are not running."""

from __future__ import annotations

import os
import socket
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from urllib.parse import urlparse

import pytest

PROVIDER_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ELEVENLABS_API_KEY",
    "DEEPGRAM_API_KEY",
    "VOICEBOX_URL",
)


@pytest.fixture(autouse=True)
def _no_real_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never reach a paid provider, even with a filled-in .env on the machine (CI never calls one either)."""
    for variable in PROVIDER_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    for variable in [v for v in os.environ if v.startswith("LLM_")]:  # model overrides: tests see the shipped tiers
        monkeypatch.delenv(variable)


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://lingard:lingard@localhost:55432/lingard")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:56379/15")


def _reachable(url: str) -> bool:
    parsed = urlparse(url.replace("+psycopg", ""))
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 5432), timeout=0.5):
            return True
    except OSError:
        return False


@asynccontextmanager
async def temp_pg_schema() -> AsyncIterator[tuple[str, str]]:
    """A fresh Postgres schema: yields (database_url, schema_name) and drops it afterwards."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    schema = f"t_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield TEST_DATABASE_URL, schema
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


PgSchemaFactory = Callable[[], AbstractAsyncContextManager[tuple[str, str]]]


@pytest.fixture
def pg_schema_factory() -> PgSchemaFactory:
    """Factory for per-test schemas; usable from async fixtures without nesting event loops."""
    if not _reachable(TEST_DATABASE_URL):
        pytest.skip("postgres not running (docker compose up -d postgres)")
    return temp_pg_schema


@pytest.fixture
def redis_url() -> str:
    if not _reachable(TEST_REDIS_URL):
        pytest.skip("redis not running (docker compose up -d redis)")
    return TEST_REDIS_URL
