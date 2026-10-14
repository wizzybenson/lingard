"""Turn events out (Redis Stream ``turns``) and steering hints in. The live loop never waits on either."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from redis.asyncio import Redis

from lingard_contracts.events import TURNS_STREAM, TurnEvent

logger = logging.getLogger(__name__)
HINT_KEY = "hint:{scene_id}"


class TurnPublisher(Protocol):
    async def publish(self, event: TurnEvent) -> None: ...


class HintSource(Protocol):
    async def take(self, scene_id: str) -> str | None: ...


class MemoryBus:
    """In-process publisher and hint source for tests and offline evals."""

    def __init__(self) -> None:
        self.events: list[TurnEvent] = []
        self.hints: dict[str, str] = {}

    async def publish(self, event: TurnEvent) -> None:
        self.events.append(event)

    async def take(self, scene_id: str) -> str | None:
        return self.hints.pop(scene_id, None)


class RedisBus:
    def __init__(self, redis: Redis, maxlen: int = 100_000) -> None:
        self._redis = redis
        self._maxlen = maxlen

    async def publish(self, event: TurnEvent) -> None:
        await self._redis.xadd(TURNS_STREAM, event.stream_fields(), maxlen=self._maxlen, approximate=True)  # type: ignore[arg-type]

    async def take(self, scene_id: str) -> str | None:
        value = await self._redis.getdel(HINT_KEY.format(scene_id=scene_id))
        return str(value) if value is not None else None


def fire_and_forget(publisher: TurnPublisher, event: TurnEvent, pending: set[asyncio.Task[None]]) -> None:
    """Publish without blocking the turn; failures are logged and the stream consumer catches up later."""

    async def run() -> None:
        try:
            await publisher.publish(event)
        except Exception:
            logger.exception("turn event publish failed (event %s)", event.event_id)

    task = asyncio.create_task(run())
    pending.add(task)
    task.add_done_callback(pending.discard)
