"""Graph worker process: one process type running every graph (SPEC §5.2 ``services/graphs``).

Consumes the ``turns`` stream (turn assessment) and the ``graph_jobs`` stream (planning, consolidation, lessons,
writing review) concurrently.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import cast

from langchain_core.runnables import RunnableConfig
from redis.asyncio import Redis
from redis.exceptions import ResponseError

import lingard_telemetry as telemetry
from lingard_contracts.events import TurnEvent
from lingard_db.base import make_engine
from lingard_graphs.checkpointing import checkpointer
from lingard_graphs.consumer import TurnConsumer
from lingard_graphs.graphs.turn_assessment import TurnState, build_turn_assessment
from lingard_graphs.runtime import GRAPH_JOBS, JobRunner, RedisHints, build_deps
from lingard_graphs.settings import GraphSettings

logger = logging.getLogger(__name__)
JOB_GROUP = "graph-workers"


async def consume_jobs(redis: Redis, runner: JobRunner, consumer: str) -> None:
    try:
        await redis.xgroup_create(GRAPH_JOBS, JOB_GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    while True:
        raw = await redis.xreadgroup(JOB_GROUP, consumer, {GRAPH_JOBS: ">"}, count=4, block=5000)
        entries = cast(list[tuple[str, list[tuple[str, dict[str, str]]]]], raw or [])
        for _, messages in entries:
            for message_id, fields in messages:
                job = json.loads(fields["json"])
                with telemetry.span(f"graph.{job['kind']}", trace_id=str(job.get("trace_id") or "")):
                    try:
                        await runner.run({**job, "job_id": message_id})
                    except Exception:
                        logger.exception("graph job %s failed", job.get("kind"))
                await redis.xack(GRAPH_JOBS, JOB_GROUP, message_id)


async def main() -> None:
    telemetry.setup("graphs")
    settings = GraphSettings()
    engine = make_engine(settings.database_url)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    deps = build_deps(settings, engine, RedisHints(redis))
    name = f"graphs-{uuid.uuid4().hex[:6]}"
    async with checkpointer(settings.database_url) as saver:
        graph = build_turn_assessment(deps, saver)

        async def handle(event: TurnEvent) -> None:
            with telemetry.span("graph.turn_assessment", trace_id=str(event.trace_id)):
                config = RunnableConfig(configurable={"thread_id": str(event.event_id)})
                await graph.ainvoke(TurnState(event=event), config=config)

        turns = TurnConsumer(redis, "turn_assessment", name, handle, max_attempts=settings.max_attempts)
        await asyncio.gather(turns.run(), consume_jobs(redis, JobRunner(deps, saver), name))


if __name__ == "__main__":
    asyncio.run(main())
