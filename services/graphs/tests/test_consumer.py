import uuid

import pytest
from redis.asyncio import Redis

from lingard_contracts.events import TURNS_STREAM, TurnEvent
from lingard_graphs.consumer import DEAD_LETTER, TurnConsumer


def event() -> TurnEvent:
    return TurnEvent(
        trace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        scene_id=uuid.uuid4(),
        turn_index=0,
        speaker="learner",
        language="fr-FR",
        transcript="Bonjour",
    )


@pytest.fixture
async def redis(redis_url: str) -> Redis:
    client = Redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    return client


async def test_at_least_once_retries_then_dead_letters(redis: Redis) -> None:
    seen: list[uuid.UUID] = []
    attempts = {"n": 0}

    async def handler(e: TurnEvent) -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        seen.append(e.event_id)

    consumer = TurnConsumer(redis, "g", "c1", handler, max_attempts=3, backoff_s=0.01)
    await consumer.ensure_group()
    first = event()
    await redis.xadd(TURNS_STREAM, first.stream_fields())
    assert await consumer.poll_once(block_ms=100) == 1
    assert seen == [first.event_id] and attempts["n"] == 2
    assert (await redis.xpending(TURNS_STREAM, "g"))["pending"] == 0

    async def always_fails(e: TurnEvent) -> None:
        raise RuntimeError("permanent")

    failing = TurnConsumer(redis, "g", "c1", always_fails, max_attempts=2, backoff_s=0.01)
    await redis.xadd(TURNS_STREAM, event().stream_fields())
    await failing.poll_once(block_ms=100)
    assert await redis.xlen(DEAD_LETTER) == 1
    await redis.aclose()


async def test_crash_recovery_reprocesses_unacked(redis: Redis) -> None:
    processed: list[uuid.UUID] = []

    async def handler(e: TurnEvent) -> None:
        processed.append(e.event_id)

    consumer = TurnConsumer(redis, "g2", "c1", handler)
    await consumer.ensure_group()
    e = event()
    await redis.xadd(TURNS_STREAM, e.stream_fields())
    await redis.xreadgroup("g2", "c1", {TURNS_STREAM: ">"}, count=1)  # delivered, then "crash" before ack
    await consumer.poll_once(block_ms=100)
    assert processed == [e.event_id]
    await redis.aclose()
