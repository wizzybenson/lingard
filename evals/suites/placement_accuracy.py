"""``placement_accuracy`` (SPEC §20, Phase 2 gate): synthetic learners at known bands place within ±1 band.

Offline: Rasch-simulated answers on the real seed bank through the real placement graph; writing and speaking
scored by an oracle at the learner's true level (live mode replaces the oracle with real scorers).
"""

from __future__ import annotations

import math
import random
import re
import uuid
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from evals.framework import ROOT, Gate, Mode, SuiteResult, suite
from evals.synthetic_learners.harness import build_deps
from lingard_exam_packs.items import ItemBank, band_to_logit
from lingard_graphs.graphs.placement import build_placement
from lingard_graphs.store import LearnerProfileView, MemoryStore
from lingard_llm import LLMConfig, LLMRouter, ModelSpec
from lingard_llm.testing import ScriptedChatModel, message_text

BANDS = [4.5, 5.5, 6.5, 7.5, 8.5]


def _oracle(true_band: float) -> Any:
    def answer(messages: list[BaseMessage]) -> str:
        import json

        system = message_text(messages[0])
        if "strict examiner" in system:
            criteria = re.findall(r"^- (\w+):", system, flags=re.MULTILINE)
            return json.dumps(
                {"dimensions": [{"dimension": c, "score": true_band} for c in criteria], "errors": [], "rewrite": ""}
            )
        level = int(re.search(r"Task level (\d+)", system).group(1))  # type: ignore[union-attr]
        return json.dumps({"met": level <= true_band, "level_estimate": round(true_band)})

    return answer


@suite(
    "placement_accuracy",
    watches=(
        "services/graphs/src/lingard_graphs/graphs/placement.py",
        "packages/exam_packs/",
        "content/packs/",
        "content/placement/",
    ),
)
async def run(mode: Mode) -> SuiteResult:
    if mode == "live":
        return SuiteResult("placement_accuracy", mode, {}, [], notes=["live mode needs founder/friends vs later mocks"])
    bank = ItemBank.load(ROOT / "content")
    errors: list[float] = []
    samples: list[dict[str, object]] = []
    for language in ("fr", "en"):
        for true_band in BANDS:
            for repeat in range(3):
                deps = await build_deps()
                model = ScriptedChatModel(responder=_oracle(true_band))

                def factory(spec: ModelSpec, model: BaseChatModel = model) -> BaseChatModel:
                    return model

                tiers = {
                    t: {"retries": 0, "models": [{"provider": "scripted", "model": "o"}]} for t in ("mid", "frontier")
                }
                deps.router = LLMRouter(LLMConfig.model_validate({"tiers": tiers}), factory=factory)
                user_id = uuid.uuid4()
                store = deps.store
                assert isinstance(store, MemoryStore)
                store.profiles[user_id] = LearnerProfileView(user_id, "sim", "ar", "tense", {}, {}, {})
                graph = build_placement(deps, bank, InMemorySaver())
                config = {"configurable": {"thread_id": str(user_id)}}
                rng = random.Random(f"{language}{true_band}{repeat}")  # noqa: S311
                result = await graph.ainvoke({"user_id": user_id, "language": language, "path": "quick"}, config)
                while result.get("__interrupt__"):
                    request = result["__interrupt__"][0].value
                    if request["kind"] == "item":
                        item = bank.get(request["item"]["item_id"])
                        p = 1 / (1 + math.exp(-(band_to_logit(true_band) - item.difficulty)))
                        options = request["item"]["options"]
                        right = options.index(item.options[item.answer])
                        resume: Any = right if rng.random() < p else (right + 1) % len(options)
                    elif request["kind"] == "read_aloud":
                        resume = {"audio_ref": "none"}
                    else:
                        resume = "réponse " * 130
                    result = await graph.ainvoke(Command(resume=resume), config)
                placed = store.profiles[user_id].language_bands[language]
                errors.append(abs(placed - true_band))
                samples.append({"language": language, "true": true_band, "placed": placed})
    within = sum(1 for e in errors if e <= 1.0) / len(errors)
    return SuiteResult(
        suite="placement_accuracy",
        mode=mode,
        metrics={
            "learners": len(errors),
            "within_one_band": round(within, 3),
            "mean_abs_error": round(sum(errors) / len(errors), 3),
        },
        gates=[Gate("within_one_band", ">=", 0.9)],
        samples=samples,
    )
