"""At-least-once consumption of the ``turns`` stream (SPEC §5.3). Handlers must be idempotent on ``event_id``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from lingard_contracts.events import TURNS_STREAM, TurnEvent

logger = logging.getLogger(__name__)
Handler = Callable[[TurnEvent], Awaitable[None]]
DEAD_LETTER = "turns:dead"


class TurnConsumer:
    def __init__(
        self,
        redis: Redis,
        group: str,
        consumer: str,
        handler: Handler,
        *,
        max_attempts: int = 4,
        backoff_s: float = 0.5,
    ) -> None:
        self._redis = redis
        self._group = group
        self._consumer = consumer
        self._handler = handler
        self._max_attempts = max_attempts
        self._backoff = backoff_s

    async def ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(TURNS_STREAM, self._group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _handle(self, message_id: str, fields: dict[str, str]) -> None:
        event = TurnEvent.from_stream_fields(fields)
        for attempt in range(1, self._max_attempts + 1):
            try:
                await self._handler(event)
                break
            except Exception:
                logger.exception("turn %s failed (attempt %d)", event.event_id, attempt)
                if attempt == self._max_attempts:
                    dead: dict[Any, Any] = dict(fields)
                    dead["error_attempts"] = attempt
                    await self._redis.xadd(DEAD_LETTER, dead)
                    break
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
        await self._redis.xack(TURNS_STREAM, self._group, message_id)

    async def poll_once(self, block_ms: int = 1000, count: int = 16) -> int:
        """Process pending (crash-recovered) entries first, then new ones. Returns how many were handled."""
        handled = 0
        for start in ("0", ">"):
            raw = await self._redis.xreadgroup(
                self._group,
                self._consumer,
                {TURNS_STREAM: start},
                count=count,
                block=None if start == "0" else block_ms,
            )
            entries = cast(list[tuple[str, list[tuple[str, dict[str, str]]]]], raw or [])
            for _, messages in entries:
                for message_id, fields in messages:
                    if fields:
                        await self._handle(message_id, fields)
                        handled += 1
        return handled

    async def run(self) -> None:
        await self.ensure_group()
        while True:
            await self.poll_once()
