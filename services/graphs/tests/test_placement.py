import math
import random
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from lingard_exam_packs.items import ItemBank, band_to_logit
from lingard_graphs.deps import GraphDeps
from lingard_graphs.graphs.placement import build_placement
from lingard_graphs.store import MemoryStore

from .conftest import USER, Script

ROOT = Path(__file__).resolve().parents[3]


def writing_scores(level: float) -> Any:
    def answer(_: list[BaseMessage]) -> dict[str, Any]:
        criteria = ["task_fulfilment", "coherence_cohesion", "lexical_resource", "grammatical_control"]
        return {
            "dimensions": [{"dimension": c, "score": level} for c in criteria],
            "errors": [
                {
                    "node_key": "fr.grammar.articles_gender",
                    "span": "des appartement",
                    "confidence": 0.9,
                    "correction": "des appartements",
                }
            ],
            "rewrite": "…",
        }

    return answer


async def run_placement(deps: GraphDeps, script: Script, true_band: float, speaking_ok_until: int) -> dict[str, Any]:
    script.handlers["experienced, strict examiner"] = writing_scores(true_band)
    script.handlers["Placement check"] = lambda m: {
        "met": int(re.search(r"Task level (\d+)", str(m[0].content)).group(1)) <= speaking_ok_until,  # type: ignore[union-attr]
        "level_estimate": speaking_ok_until,
    }
    bank = ItemBank.load(ROOT / "content")
    graph = build_placement(deps, bank, InMemorySaver())
    config = {"configurable": {"thread_id": f"placement-{true_band}"}}
    rng = random.Random(11)
    result = await graph.ainvoke({"user_id": USER, "language": "fr", "path": "quick"}, config)
    prompts_seen: list[str] = []
    for _ in range(80):
        pending = result.get("__interrupt__")
        if not pending:
            break
        request = pending[0].value
        prompts_seen.append(request["kind"])
        if request["kind"] == "item":
            item = bank.get(request["item"]["item_id"])
            p = 1 / (1 + math.exp(-(band_to_logit(true_band) - item.difficulty)))
            correct_text = item.options[item.answer]
            options = request["item"]["options"]
            choice = (
                options.index(correct_text) if rng.random() < p else (options.index(correct_text) + 1) % len(options)
            )
            resume: Any = choice
        elif request["kind"] == "writing":
            resume = "Bonjour, je cherche des appartement près du centre pour le mois de mars. " * 3
        elif request["kind"] == "speaking":
            resume = "Je viens de Casablanca, c'est une grande ville au bord de la mer."
        else:
            resume = {"audio_ref": "s3://audio/x.opus", "consent_clone": True}
        result = await graph.ainvoke(Command(resume=resume), config)
    result["prompts_seen"] = prompts_seen
    return result


async def test_quick_placement_lands_near_true_band_and_seeds_model(deps: GraphDeps, script: Script) -> None:
    result = await run_placement(deps, script, true_band=7, speaking_ok_until=7)
    assert result["status"] == "done" and result["start_district"] == "rivemont.vieux_port"
    kinds = result["prompts_seen"]
    assert kinds.count("item") <= 30 and "writing" in kinds and kinds[-1] == "read_aloud"
    assert kinds.count("speaking") == 6, "levels 4–7 pass, 8 and 9 fail → stop after two consecutive failures"
    estimates = result["estimates"]
    assert abs(estimates["listening"] - 7) <= 1.5 and abs(estimates["reading"] - 7) <= 1.5
    assert estimates["speaking"] == 7
    store = deps.store
    assert isinstance(store, MemoryStore)
    assert 6 <= store.profiles[USER].language_bands["fr"] <= 8
    assert len(await store.posteriors(USER)) == 4


async def test_skip_path_uses_wide_priors(deps: GraphDeps) -> None:
    bank = ItemBank.load(ROOT / "content")
    graph = build_placement(deps, bank, InMemorySaver())
    result = await graph.ainvoke(
        {"user_id": USER, "language": "en", "path": "skip"}, {"configurable": {"thread_id": "skip"}}
    )
    assert result["status"] == "done" and result["start_district"] == "ashford.station_quarter"
    store = deps.store
    assert isinstance(store, MemoryStore)
    posteriors = await store.posteriors(USER)
    assert all(p.observations == 0 and p.variance >= 4 for (pack, _), p in posteriors.items() if pack == "ielts_gt")
