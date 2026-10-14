"""Application container built once at startup and reached through ``request.app.state.lingard``."""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from agent_memory.sql import SqlMemoryStore
from lingard_api.auth.pin import PinHasher
from lingard_api.auth.ratelimit import MemoryRateLimiter, RateLimiter, RedisRateLimiter
from lingard_api.auth.service import PinAuthService
from lingard_api.graph_runtime import InteractiveGraphs, open_saver
from lingard_api.jobs import JobQueue, MemoryJobQueue, RedisJobQueue
from lingard_api.settings import Settings
from lingard_curriculum.packs import PackLibrary
from lingard_curriculum.sql import SqlCurriculumGraph
from lingard_db.base import make_engine, session_factory
from lingard_db.models import curriculum_edges_table, curriculum_nodes_table, memory_items_table
from lingard_exam_packs.items import ItemBank
from lingard_graphs.deps import GraphDeps, MemoryHints
from lingard_graphs.pedagogy.config import load_pedagogy
from lingard_graphs.runtime import RedisHints
from lingard_graphs.sql_store import SqlStore
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry
from lingard_pronunciation.clone import ElevenLabsClone, VoiceboxClone, VoiceCloneProvider
from lingard_storage import MemoryObjectStore, ObjectStore, S3ObjectStore


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    auth: PinAuthService
    packs: PackLibrary
    curriculum: SqlCurriculumGraph
    redis: Redis | None
    jobs: JobQueue
    objects: ObjectStore
    clone_providers: dict[str, VoiceCloneProvider]
    graph_deps: GraphDeps
    interactive: InteractiveGraphs | None = None
    pronunciation: httpx.AsyncClient | None = None
    _stack: AsyncExitStack = field(default_factory=AsyncExitStack)

    @classmethod
    def build(cls, settings: Settings, llm: LLMRouter | None = None) -> AppState:
        engine = make_engine(settings.database_url, settings.database_schema)
        sessions = session_factory(engine)
        redis = Redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None
        limiter: RateLimiter = RedisRateLimiter(redis) if redis is not None else MemoryRateLimiter()
        hasher = PinHasher(settings.argon2_time_cost, settings.argon2_memory_kib, settings.argon2_parallelism)
        curriculum = SqlCurriculumGraph(engine, curriculum_nodes_table, curriculum_edges_table)
        packs = PackLibrary(settings.content_root)
        objects: ObjectStore = (
            S3ObjectStore(
                settings.object_store_url, settings.object_store_key, settings.object_store_secret.get_secret_value()
            )
            if settings.object_store_url
            else MemoryObjectStore()
        )
        providers: dict[str, VoiceCloneProvider] = {}
        if settings.voicebox_url:
            providers["voicebox"] = VoiceboxClone(settings.voicebox_url)
        if settings.elevenlabs_api_key:
            providers["elevenlabs"] = ElevenLabsClone(settings.elevenlabs_api_key.get_secret_value())
        deps = GraphDeps(
            store=SqlStore(sessions),
            curriculum=curriculum,
            router=llm or LLMRouter(LLMConfig.load(settings.config_root / "llm.yaml")),
            prompts=PromptRegistry(settings.prompts_root),
            packs=packs,
            pedagogy=load_pedagogy(settings.config_root / "pedagogy.yaml"),
            hints=RedisHints(redis) if redis is not None else MemoryHints(),
            content_root=settings.content_root,
            memory=SqlMemoryStore(engine, memory_items_table),
        )
        return cls(
            settings=settings,
            engine=engine,
            sessions=sessions,
            auth=PinAuthService(sessions, settings, hasher, limiter),
            packs=packs,
            curriculum=curriculum,
            redis=redis,
            jobs=RedisJobQueue(redis) if redis is not None else MemoryJobQueue(),
            objects=objects,
            clone_providers=providers,
            graph_deps=deps,
            pronunciation=(
                httpx.AsyncClient(base_url=settings.pronunciation_url, timeout=30.0)
                if settings.pronunciation_url
                else None
            ),
        )

    async def start(self) -> None:
        """Open long-lived resources (graph checkpointer) and compile the interactive graphs."""
        checkpoint_url = None if self.settings.env == "test" else self.settings.database_url
        saver = await open_saver(self._stack, checkpoint_url)
        self.interactive = InteractiveGraphs(self.graph_deps, ItemBank.load(self.settings.content_root), saver)

    async def close(self) -> None:
        await self._stack.aclose()
        await self.engine.dispose()
        if self.pronunciation is not None:
            await self.pronunciation.aclose()
        if self.redis is not None:
            await self.redis.aclose()
