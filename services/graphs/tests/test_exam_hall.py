import itertools
import re
import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from lingard_contracts.events import TurnEvent
from lingard_exam_packs.items import Item, ItemBank
from lingard_graphs.deps import GraphDeps
from lingard_graphs.graphs.exam_hall import ExamState, build_exam_hall
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


def right_answer(item: Item, served: dict[str, Any]) -> Any:
    if item.response == "text":
        return item.accepted[0]
    if isinstance(item.answer, list):
        return [served["options"].index(item.options[k]) for k in item.answer]
    assert item.answer is not None
    return served["options"].index(item.options[item.answer])


def wrong_answer(item: Item, served: dict[str, Any]) -> Any:
    if item.response == "text":
        return "nothing like it"
    right = right_answer(item, served)
    return [0] if isinstance(right, list) else (right + 1) % len(served["options"])


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
    config: RunnableConfig = {"configurable": {"thread_id": "mock-1"}}
    result = await graph.ainvoke(ExamState(user_id=USER, pack="tef_canada"), config)
    sections_seen: list[str] = []
    live_scenes: list[uuid.UUID] = []
    late_answers = 0
    credited = {"comprehension_ecrite": 0, "comprehension_orale": 0}
    late_right = 0
    while result.get("__interrupt__"):
        request = result["__interrupt__"][0].value
        if not sections_seen or sections_seen[-1] != request["section"]:
            sections_seen.append(request["section"])
        if request["kind"] == "set":
            served = request["set"]
            answerable = any(bank.get(q["item_id"]).band <= 7 for q in served["questions"])
            late = late_answers < 2 and request["section"] == "comprehension_orale" and answerable
            elapsed = 9999 if late else 60
            late_answers += elapsed == 9999
            given = []
            for question in served["questions"]:
                item = bank.get(question["item_id"])
                right = right_answer(item, question)
                given.append(right if item.band <= 7 else wrong_answer(item, question))
                if item.band <= 7 and elapsed == 9999:
                    late_right += 1
                elif item.band <= 7:
                    credited[request["section"]] += 1
            resume: Any = {"answers": given, "elapsed_s": elapsed}
        elif request["kind"] == "writing":
            resume = {"text": "Texte assez long. " * 60, "elapsed_s": 1200}
        elif "scene_id" in request:
            scene_id = uuid.UUID(request["scene_id"])
            record = await deps.store.scene(scene_id)
            assert record is not None and record.contract.cast[0].npc_key == "examinatrice_claire"
            assert record.contract.approved_facts and record.contract.learner_goal == request["prompt"]
            live_scenes.append(scene_id)
            for i, (speaker, text) in enumerate(
                [("npc", "Bonjour, je vous écoute."), ("learner", "Bonjour, à quelle heure partent les sorties ?")]
            ):
                await deps.store.save_turn(
                    TurnEvent(
                        trace_id=scene_id,
                        user_id=USER,
                        session_id=record.session_id,
                        scene_id=scene_id,
                        turn_index=i,
                        speaker=speaker,
                        language="fr-FR",
                        transcript=text,
                    )
                )
            resume = {"scene_id": request["scene_id"]}
        else:
            resume = {"transcript": "Bonjour, je voudrais des renseignements sur les cours du soir."}
        result = await graph.ainvoke(Command(resume=resume), config)
    assert sections_seen == ["comprehension_ecrite", "comprehension_orale", "expression_ecrite", "expression_orale"]
    for section, count in (("comprehension_ecrite", 40), ("comprehension_orale", 40)):
        parts = [bank.get(i).part for i in result["item_ids"][section]]
        blueprint = {p.id: p.items for p in deps.packs.pack("tef_canada").section(section).part_list()}
        assert len(parts) == count and {p: parts.count(p) for p in blueprint} == blueprint, "the official blueprint"
    assert (
        len(result["item_ids"]["comprehension_ecrite"]) == 40 and len(result["item_ids"]["comprehension_orale"]) == 40
    )
    assert result["overall"] is None, "TEF reports modules separately"
    assert len(live_scenes) == 2 and len(set(live_scenes)) == 2, "each speaking part is a live examiner scene"
    assert "Candidate: Bonjour, à quelle heure partent les sorties ?" in result["speaking"]["section_a"]
    assert "Examiner: Bonjour, je vous écoute." in result["speaking"]["section_a"]
    assert 6 <= result["levels"]["reading"] <= 8, "items up to band 7 right, above wrong → about NCLC 7"
    assert result["levels"]["writing"] == 7 and result["levels"]["speaking"] == 8
    raw = (await deps.store.mocks(USER))[0]["raw_scores"]
    assert late_right, "the late sets held answers that would have been right"
    assert raw["comprehension_orale"] == credited["comprehension_orale"], "late answers are scored as wrong"
    assert raw["comprehension_ecrite"] == credited["comprehension_ecrite"]
    store = deps.store
    assert isinstance(store, MemoryStore)
    assert (await store.posteriors(USER))[("tef_canada", "speaking")].observations == 1
    assert (await store.wallet(USER))[0] >= 80


def test_ielts_part_3_discusses_the_theme_of_the_part_2_cue_card() -> None:
    import random

    import yaml

    from lingard_graphs.graphs.exam_hall import choose_speaking

    prompts = yaml.safe_load((ROOT / "content" / "packs" / "ielts_gt" / "speaking_prompts.yaml").read_text())
    assert {e["topic"] for e in prompts["long_turn"]} == {e["topic"] for e in prompts["discussion"]}
    for seed in range(20):
        pick, topics = random.Random(seed), set[str]()
        choose_speaking(prompts["interview"], topics, pick)
        cue = choose_speaking(prompts["long_turn"], topics, pick)
        talk = choose_speaking(prompts["discussion"], topics, pick)
        topic = next(e["topic"] for e in prompts["long_turn"] if e["prompt"] == cue["prompt"])
        assert any(e["topic"] == topic and e["prompt"] == talk["prompt"] for e in prompts["discussion"])
        assert "topic" not in cue and "topic" not in talk
