# Lifted from simupatient@69e1bd5:backend/app/agents/checkpointing.py
"""LangGraph checkpointer: Postgres in deployment, in-memory under test (SPEC §11)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


def _plain_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@asynccontextmanager
async def checkpointer(database_url: str | None) -> AsyncIterator[BaseCheckpointSaver[str]]:
    if database_url is None:
        yield InMemorySaver()
        return
    async with AsyncPostgresSaver.from_conn_string(_plain_url(database_url)) as saver:
        yield saver


async def setup_checkpointer(database_url: str) -> None:
    async with AsyncPostgresSaver.from_conn_string(_plain_url(database_url)) as saver:
        await saver.setup()
