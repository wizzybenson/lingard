import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from lingard_curriculum.graph import InMemoryCurriculumGraph
from lingard_curriculum.packs import PackLibrary
from lingard_curriculum.seed import load_seed, seed_graph
from lingard_graphs.deps import GraphDeps, MemoryHints
from lingard_graphs.pedagogy.config import load_pedagogy
from lingard_graphs.store import LearnerProfileView, MemoryStore
from lingard_llm import LLMConfig, LLMRouter, ModelSpec, PromptRegistry
from lingard_llm.testing import ScriptedChatModel, message_text

ROOT = Path(__file__).resolve().parents[3]
USER = uuid.UUID("00000000-0000-0000-0000-000000000001")


class Script:
    """Routes scripted LLM answers by prompt: ``handlers[prompt_marker] = fn(messages) -> dict``."""

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[list[BaseMessage]], dict[str, Any]]] = {}
        self.calls: list[str] = []

    def __call__(self, messages: list[BaseMessage]) -> str:
        system = message_text(messages[0])
        for marker, handler in self.handlers.items():
            if marker in system:
                self.calls.append(marker)
                return json.dumps(handler(messages), ensure_ascii=False)
        raise AssertionError(f"no scripted handler for prompt starting {system[:80]!r}")


@pytest.fixture
def script() -> Script:
    return Script()


@pytest.fixture
async def deps(script: Script) -> GraphDeps:
    model = ScriptedChatModel(responder=script)
    tiers = {t: {"retries": 0, "models": [{"provider": "scripted", "model": "s"}]} for t in ("fast", "mid", "frontier")}

    def factory(spec: ModelSpec) -> BaseChatModel:
        return model

    curriculum = InMemoryCurriculumGraph()
    for language in ("fr", "en"):
        await seed_graph(curriculum, load_seed(ROOT / "content", language))  # type: ignore[arg-type]
    store = MemoryStore()
    store.profiles[USER] = LearnerProfileView(
        user_id=USER,
        display_name="Ernest",
        l1="ar",
        intensity_cap="tense",
        target_bands={"tef_canada": {"speaking": 7}},
        crs_inputs={},
        language_bands={"fr": 6, "en": 8},
    )
    return GraphDeps(
        store=store,
        curriculum=curriculum,
        router=LLMRouter(LLMConfig.model_validate({"tiers": tiers}), factory=factory),
        prompts=PromptRegistry(ROOT / "prompts"),
        packs=PackLibrary(ROOT / "content"),
        pedagogy=load_pedagogy(),
        hints=MemoryHints(),
        content_root=ROOT / "content",
    )
