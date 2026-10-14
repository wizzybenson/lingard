"""Fixed-window rate limits per IP and per name (SPEC §23.2). Redis in deployment, memory in tests."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Protocol

from redis.asyncio import Redis


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_s: int = 60) -> bool:
        """Record one attempt; False when the limit for the current window is exceeded."""
        ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, int], int] = defaultdict(int)

    async def hit(self, key: str, limit: int, window_s: int = 60) -> bool:
        window = int(time.time() // window_s)
        self._counts[(key, window)] += 1
        return self._counts[(key, window)] <= limit


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, limit: int, window_s: int = 60) -> bool:
        bucket = f"rl:{key}:{int(time.time() // window_s)}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(bucket)
            pipe.expire(bucket, window_s * 2)
            count, _ = await pipe.execute()
        return int(count) <= limit
