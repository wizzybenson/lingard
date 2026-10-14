"""Job dispatch from the API to workers over Redis Streams (planning → graphs, scenes → live)."""

from __future__ import annotations

import json
from typing import Any, Protocol

from redis.asyncio import Redis

GRAPH_JOBS = "graph_jobs"
LIVE_JOBS = "live_jobs"


class JobQueue(Protocol):
    async def enqueue(self, stream: str, payload: dict[str, Any]) -> str: ...


class RedisJobQueue:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def enqueue(self, stream: str, payload: dict[str, Any]) -> str:
        return str(await self._redis.xadd(stream, {"json": json.dumps(payload, default=str)}))


class MemoryJobQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, dict[str, Any]]] = []

    async def enqueue(self, stream: str, payload: dict[str, Any]) -> str:
        self.jobs.append((stream, payload))
        return str(len(self.jobs))
