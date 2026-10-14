"""Live worker: consumes ``live_jobs`` from Redis and runs one ``LiveLoop`` per scene on LiveKit.

A job carries the compiled contract plus identity; the worker never reads pedagogical memory (SPEC §14).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import cast

from dotenv import load_dotenv
from pydantic import BaseModel
from redis.asyncio import Redis

import lingard_telemetry as telemetry
from lingard_contracts.common import CITY_LOCALE
from lingard_contracts.live import LiveSessionConfig, personalised_turn_policy
from lingard_contracts.scene import SceneContract
from lingard_live.actor import NpcActor
from lingard_live.events import RedisBus
from lingard_live.guard import ContractGuard
from lingard_live.languages import LanguageIdentifier, load_language
from lingard_live.livekit_transport import LiveKitTransport
from lingard_live.loop import LiveLoop, SceneIdentity
from lingard_live.scene import build_scene
from lingard_live.settings import LiveSettings, build_stt, build_tts
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry

logger = logging.getLogger(__name__)
JOBS_STREAM = "live_jobs"
GROUP = "live-workers"


class LiveJob(BaseModel):
    room: str
    user_id: uuid.UUID
    session_id: uuid.UUID
    trace_id: uuid.UUID
    learner_name: str
    learner_band: int
    intra_pauses_ms: list[int] = []
    relationship: str | None = None
    scene_vocabulary: list[str] = []
    contract: SceneContract


async def run_job(job: LiveJob, settings: LiveSettings, redis: Redis) -> None:
    runtime = build_scene(
        job.contract,
        settings.content_root,
        learner_name=job.learner_name,
        relationship=job.relationship,
        scene_vocabulary=job.scene_vocabulary,
    )
    languages = [load_language(settings.content_root, "fr"), load_language(settings.content_root, "en")]
    identifier = LanguageIdentifier(languages)
    router = LLMRouter(LLMConfig.load(settings.llm_config))
    actor = NpcActor(router, PromptRegistry(settings.prompts_root).get("npc_actor"))
    policy = personalised_turn_policy(job.learner_band, job.intra_pauses_ms)
    transport = LiveKitTransport(
        settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret.get_secret_value()
    )
    session = await transport.open(
        LiveSessionConfig(
            session_id=job.session_id,
            user_id=job.user_id,
            scene_id=job.contract.scene_id,
            room=job.room,
            locale=CITY_LOCALE[job.contract.city],
            policy=policy,
        )
    )
    bus = RedisBus(redis)
    loop = LiveLoop(
        session=session,
        state=runtime.state,
        identity=SceneIdentity(job.user_id, job.session_id, job.trace_id, job.learner_band),
        actor=actor,
        guard=ContractGuard(identifier),
        guard_ctx=runtime.guard_ctx,
        language=runtime.language,
        identifier=identifier,
        stt=build_stt(settings),
        tts=build_tts(settings),
        publisher=bus,
        hints=bus,
    )
    with telemetry.span("live.scene", trace_id=str(job.trace_id), scene=str(job.contract.scene_id)):
        try:
            await loop.opening()
            await loop.run()
        finally:
            await session.close()


async def main() -> None:
    load_dotenv()
    telemetry.setup("live")
    settings = LiveSettings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.xgroup_create(JOBS_STREAM, GROUP, id="0", mkstream=True)
    except Exception:  # group exists
        logger.debug("consumer group present")
    consumer = f"live-{uuid.uuid4().hex[:6]}"
    running: set[asyncio.Task[None]] = set()
    while True:
        raw = await redis.xreadgroup(GROUP, consumer, {JOBS_STREAM: ">"}, count=1, block=5000)
        entries = cast(list[tuple[str, list[tuple[str, dict[str, str]]]]], raw or [])
        for _, messages in entries:
            for message_id, fields in messages:
                job = LiveJob.model_validate(json.loads(fields["json"]))
                task = asyncio.create_task(run_job(job, settings, redis))
                running.add(task)
                task.add_done_callback(running.discard)
                await redis.xack(JOBS_STREAM, GROUP, message_id)


if __name__ == "__main__":
    asyncio.run(main())
