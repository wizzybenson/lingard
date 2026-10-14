import itertools
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from lingard_exam_packs.items import ItemBank
from lingard_graphs.deps import GraphDeps
from lingard_graphs.graphs.exam_hall import build_exam_hall
from lingard_graphs.store import MemoryStore
from lingard_llm.testing import message_text

from .conftest import USER, Script

ROOT = Path(__file__).resolve().parents[3]
counter = itertools.count()


def generated_items(messages: list[BaseMessage]) -> dict[str, Any]:
    count = int(re.search(r"Write (\d+) ORIGINAL", message_text(messages[0])).group(1))  # type: ignore[union-attr]
    items = []
    for _ in range(count):
        n = next(counter)
        items.append(
            {
                "stimulus": f"Document numéro {n} : la salle {n} est fermée.",
                "question": f"Quelle salle {n} ?",
                "options": [f"La salle {n}", f"La salle {n + 1}", f"Le hall {n}", f"Le bureau {n}"],
                "answer": 0,
            }
        )
    return {"items": items}


def criteria_scores(level: float) -> Any:
    def answer(messages: list[BaseMessage]) -> dict[str, Any]:
        criteria = re.findall(r"^- (\w+):", message_text(messages[0]), flags=re.MULTILINE)
        return {"dimensions": [{"dimension": c, "score": level} for c in criteria], "errors": [], "rewrite": "…"}

    return answer


async def test_full_tef_mock_official_order_timing_and_scores(deps: GraphDeps, script: Script) -> None:
    script.handlers["items for practice in the format"] = generated_items
    script.handlers["Write ORIGINAL exam tasks"] = lambda m: {
        "writing": [
            {"task_id": "section_a", "prompt": "Continuez cet article…"},
            {"task_id": "section_b", "prompt": "Donnez votre opinion…"},
        ],
        "speaking": [
            {"part_id": "section_a", "prompt": "Vous appelez une école…"},
            {"part_id": "section_b", "prompt": "Convainquez un ami…"},
        ],
    }
    script.handlers["strict examiner for"] = criteria_scores(7)
    script.handlers["speaking examiner"] = criteria_scores(8)
    bank = ItemBank.load(ROOT / "content")
    graph = build_exam_hall(deps, bank, InMemorySaver())
    config = {"configurable": {"thread_id": "mock-1"}}
    result = await graph.ainvoke({"user_id": USER, "pack": "tef_canada"}, config)
    sections_seen: list[str] = []
    late_answers = 0
    while result.get("__interrupt__"):
        request = result["__interrupt__"][0].value
        if not sections_seen or sections_seen[-1] != request["section"]:
            sections_seen.append(request["section"])
        if request["kind"] == "item":
            item = bank.get(request["item"]["item_id"])
            options = request["item"]["options"]
            right = options.index(item.options[item.answer])
            elapsed = 9999 if late_answers < 5 and request["section"] == "comprehension_orale" else 60
            late_answers += elapsed == 9999
            resume: Any = {"choice": right if item.band <= 7 else (right + 1) % 4, "elapsed_s": elapsed}
        elif request["kind"] == "writing":
            resume = {"text": "Texte assez long. " * 60, "elapsed_s": 1200}
        else:
            resume = {"transcript": "Bonjour, je voudrais des renseignements sur les cours du soir."}
        result = await graph.ainvoke(Command(resume=resume), config)
    assert sections_seen == ["comprehension_ecrite", "comprehension_orale", "expression_ecrite", "expression_orale"]
    assert (
        len(result["item_ids"]["comprehension_ecrite"]) == 40 and len(result["item_ids"]["comprehension_orale"]) == 40
    )
    assert result["overall"] is None, "TEF reports modules separately"
    assert 6 <= result["levels"]["reading"] <= 8, "items up to band 7 right, above wrong → about NCLC 7"
    assert result["levels"]["writing"] == 7 and result["levels"]["speaking"] == 8
    raw = (await deps.store.mocks(USER))[0]["raw_scores"]
    assert raw["comprehension_orale"] < raw["comprehension_ecrite"], "late answers are scored as wrong"
    store = deps.store
    assert isinstance(store, MemoryStore)
    assert (await store.posteriors(USER))[("tef_canada", "speaking")].observations == 1
    assert (await store.wallet(USER))[0] >= 80
