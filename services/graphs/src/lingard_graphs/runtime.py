"""Build ``GraphDeps`` for a deployment and dispatch background graph jobs (``graph_jobs`` stream)."""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_memory.sql import SqlMemoryStore
from lingard_curriculum.packs import PackLibrary
from lingard_curriculum.sql import SqlCurriculumGraph
from lingard_db.base import session_factory
from lingard_db.models import curriculum_edges_table, curriculum_nodes_table, memory_items_table
from lingard_graphs.deps import GraphDeps, HintSink
from lingard_graphs.graphs.day_planner import build_day_planner
from lingard_graphs.graphs.lesson_builder import build_lesson_builder
from lingard_graphs.graphs.night_consolidation import build_night_consolidation
from lingard_graphs.graphs.writing_review import build_writing_review
from lingard_graphs.pedagogy.config import load_pedagogy
from lingard_graphs.settings import GraphSettings
from lingard_graphs.sql_store import SqlStore
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry

GRAPH_JOBS = "graph_jobs"
HINT_TTL_S = 600


class RedisHints:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def put(self, scene_id: str, hint: str) -> None:
        await self._redis.set(f"hint:{scene_id}", hint, ex=HINT_TTL_S)


def build_deps(settings: GraphSettings, engine: AsyncEngine, hints: HintSink) -> GraphDeps:
    return GraphDeps(
        store=SqlStore(session_factory(engine)),
        curriculum=SqlCurriculumGraph(engine, curriculum_nodes_table, curriculum_edges_table),
        router=LLMRouter(LLMConfig.load(settings.llm_config)),
        prompts=PromptRegistry(settings.prompts_root),
        packs=PackLibrary(settings.content_root),
        pedagogy=load_pedagogy(),
        hints=hints,
        content_root=settings.content_root,
        memory=SqlMemoryStore(engine, memory_items_table),
    )


class JobRunner:
    """Background graphs keyed by job kind. Each job runs on its own checkpoint thread (resumable after a crash)."""

    def __init__(self, deps: GraphDeps, saver: BaseCheckpointSaver[str] | None = None) -> None:
        self.graphs: dict[str, CompiledStateGraph[Any, Any, Any, Any]] = {
            "day_planner": build_day_planner(deps, saver),
            "night_consolidation": build_night_consolidation(deps, saver),
            "lesson_builder": build_lesson_builder(deps, saver),
            "writing_review": build_writing_review(deps, saver),
        }

    async def run(self, job: dict[str, Any]) -> dict[str, Any]:
        kind = job["kind"]
        payload = {k: v for k, v in job.items() if k not in ("kind", "job_id")}
        thread = str(job.get("job_id") or uuid.uuid4())
        result: dict[str, Any] = await self.graphs[kind].ainvoke(payload, {"configurable": {"thread_id": thread}})
        return result
