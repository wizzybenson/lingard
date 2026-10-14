"""Dependencies shared by every graph (one worker process type, many graphs)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from agent_memory import Embedder, HashingEmbedder, InMemoryStore
from agent_memory import MemoryStore as AgentMemory
from lingard_contracts.common import Language
from lingard_curriculum.graph import CurriculumGraph
from lingard_curriculum.models import CurriculumNode
from lingard_curriculum.packs import PackLibrary
from lingard_graphs.pedagogy.config import Pedagogy
from lingard_graphs.store import LearnerStore
from lingard_llm import LLMRouter, PromptRegistry


class HintSink(Protocol):
    async def put(self, scene_id: str, hint: str) -> None: ...


class MemoryHints:
    def __init__(self) -> None:
        self.hints: dict[str, str] = {}

    async def put(self, scene_id: str, hint: str) -> None:
        self.hints[scene_id] = hint

    async def take(self, scene_id: str) -> str | None:
        return self.hints.pop(scene_id, None)


@dataclass
class GraphDeps:
    store: LearnerStore
    curriculum: CurriculumGraph
    router: LLMRouter
    prompts: PromptRegistry
    packs: PackLibrary
    pedagogy: Pedagogy
    hints: HintSink
    content_root: Path
    memory: AgentMemory = field(default_factory=InMemoryStore)
    embedder: Embedder = field(default_factory=lambda: HashingEmbedder(384))
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    """Injectable for simulations (synthetic learners live many days in one run)."""

    async def nodes_for(
        self, language: Language, keys: list[str] | None = None, max_band: int | None = None
    ) -> dict[str, CurriculumNode]:
        nodes = await self.curriculum.nodes(language, max_band=max_band)
        return {n.key: n for n in nodes if keys is None or n.key in keys}
