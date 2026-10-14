import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.messages import BaseMessage

from agent_memory import Query
from lingard_contracts.assessment import ErrorTag, Span, TargetEvidence, UtteranceAssessment
from lingard_contracts.events import TurnEvent
from lingard_graphs.deps import GraphDeps
from lingard_graphs.graphs.day_planner import build_day_planner
from lingard_graphs.graphs.lesson_builder import build_lesson_builder
from lingard_graphs.graphs.night_consolidation import build_night_consolidation, world_namespace
from lingard_graphs.pedagogy.tickets import Example, Ticket
from lingard_graphs.store import MemoryStore, SceneRecord
from lingard_llm.testing import message_text

from .conftest import USER, Script


def draft_for(messages: list[BaseMessage]) -> dict[str, Any]:
    """A valid scene draft for whatever targets the compiler prompt lists."""
    system = message_text(messages[0])
    targets = [line.split()[1] for line in system.splitlines() if line.startswith("- fr.") or line.startswith("- en.")]
    return {
        "learner_goal": "Régler un petit problème",
        "elicitation": [
            {"target": t, "tactic": f"Create a situation that needs {t}"} for t in targets if ".pron." not in t
        ],
        "approved_facts": ["Le café ouvre à 7 h"],
        "success_conditions": ["Le problème est réglé"],
        "evidence_required": [],
        "exits": [{"key": "done", "trigger": "resolved", "consequence": "the day goes on"}],
        "max_turns": 14,
        "mood": "friendly",
    }


async def test_day_planner_builds_three_valid_scenes_with_ticket_share(deps: GraphDeps, script: Script) -> None:
    store = deps.store
    assert isinstance(store, MemoryStore)
    now = datetime.now(UTC)
    tickets = (
        "fr.grammar.conditionnel_present",
        "fr.func.complain_politely",
        "fr.grammar.pronoms_cod_coi",
        "fr.grammar.futur_simple",
        "fr.func.give_advice",
        "fr.grammar.relatifs_qui_que_ou",
    )
    for key in tickets:
        await store.save_ticket(
            USER, Ticket(key, priority=0.8, examples=[Example(now, "x", "rivemont.vieux_port.apartment_3b:s1")])
        )
    script.handlers["director of an ongoing life story"] = lambda m: {
        "beats": ["Beat one.", "Beat two.", "Beat three."]
    }
    script.handlers["You design one scene"] = draft_for
    session_id = uuid.uuid4()
    result = await build_day_planner(deps).ainvoke({"user_id": USER, "session_id": session_id, "city": "rivemont"})
    plan = result["plan"]
    assert len(plan.scenes) == 3 and len(result["contracts"]) == 3
    assert 0.4 <= plan.ticket_share() <= 0.6
    landlord = next(s for s in plan.scenes if s.location_key == "rivemont.vieux_port.apartment_3b")
    assert not set(landlord.ticket_targets), "tickets failed at the landlord's are never re-tried there"
    saved = [s for s in store.scenes.values() if s.session_id == session_id]
    assert len(saved) == 3 and store.plans[session_id] == plan


async def scene_with_assessments(deps: GraphDeps) -> uuid.UUID:
    from .test_scene_and_turn_graphs import good_draft

    store = deps.store
    assert isinstance(store, MemoryStore)
    session_id = uuid.uuid4()
    from lingard_contracts.scene import SceneContract

    draft = good_draft([])
    contract = SceneContract.model_validate(
        {
            "city": "rivemont",
            "location_key": "rivemont.vieux_port.apartment_3b",
            "cast": [{"npc_key": "landlord_martin", "role": "landlord", "voice_id": "v"}],
            "learner_goal": draft["learner_goal"],
            "targets": {"grammar": ["fr.grammar.si_imparfait"]},
            "elicitation": [{"target": "fr.grammar.si_imparfait", "tactic": "Ask what if"}],
            "approved_facts": draft["approved_facts"],
            "npc_language_band": 7,
            "accent_variety": ["fr-FR-standard"],
            "success_conditions": ["counter-offer made"],
            "max_turns": 12,
            "exits": draft["exits"],
        }
    )
    await store.save_scene(SceneRecord(contract.scene_id, USER, session_id, contract, status="live"))
    for i, (text, confirmed) in enumerate([("si je refuserais", True), ("si j'aurais su", False)]):
        event = TurnEvent(
            trace_id=uuid.uuid4(),
            user_id=USER,
            session_id=session_id,
            scene_id=contract.scene_id,
            turn_index=i,
            speaker="learner",
            language="fr-FR",
            transcript=text,
        )
        await store.save_turn(event)
        span = Span(start=0, end=len(text), text=text)
        await store.save_assessment(
            USER,
            UtteranceAssessment(
                turn_event_id=event.event_id,
                pack="tef_canada",
                dimensions=[],
                confidence=0.8,
                band_estimate=7,
                error_tags=[
                    ErrorTag(
                        node_key="fr.grammar.si_imparfait",
                        span=span,
                        correction="si je refusais",
                        confidence=0.9 if confirmed else 0.7,
                        second_check_agrees=confirmed or None,
                    )
                ],
                target_evidence=[TargetEvidence(node_key="fr.func.negotiate", correct=True, confidence=0.9)],
            ),
        )
    return session_id


async def test_night_consolidation_notebook_world_memory_and_rewards(deps: GraphDeps, script: Script) -> None:
    store = deps.store
    assert isinstance(store, MemoryStore)
    session_id = await scene_with_assessments(deps)
    store.profiles[USER].crs_inputs = {"age": 30, "education": "masters", "foreign_work_years": 3}
    script.handlers["night notebook"] = lambda m: {
        "items": [{"index": 0, "explanation": "Après « si », pas de conditionnel."}],
        "encouragement": "Belle négociation !",
    }
    script.handlers["keep the story world consistent"] = lambda m: {
        "story_flags": {"deposit_dispute": "ongoing"},
        "relationships": [{"npc_key": "landlord_martin", "affinity_delta": -0.1, "summary": "Disputed the deposit."}],
    }
    result = await build_night_consolidation(deps).ainvoke({"user_id": USER, "session_id": session_id})
    notebook = result["notebook"]
    assert [c.learner_said for c in notebook.corrections] == ["si je refuserais"], "unconfirmed tags never shown"
    assert notebook.corrections[0].explanation.startswith("Après")
    assert "fr.func.negotiate" in notebook.strengths
    assert store.notebooks[(USER, session_id)]["encouragement"] == "Belle négociation !"
    assert store.profiles[USER].language_bands["fr"] >= 6
    assert result["sim_crs"] is not None and result["coins_awarded"] >= 40
    assert (await store.world_state(USER, "rivemont"))["story_flags"] == {"deposit_dispute": "ongoing"}
    memories = await deps.memory.search(Query(namespace=world_namespace(USER, "rivemont")))
    assert [m.item.content for m in memories] == ["Disputed the deposit."]
    dumped = json.dumps([m.item.model_dump(mode="json") for m in memories])
    assert "si_imparfait" not in dumped and "refuserais" not in dumped, "world memory never holds pedagogy"
    again = await build_night_consolidation(deps).ainvoke({"user_id": USER, "session_id": session_id})
    assert again["coins_awarded"] == 0, "rewards are idempotent per scene and day"


async def test_lesson_builder_uses_real_mistakes_games_and_homework(deps: GraphDeps, script: Script) -> None:
    store = deps.store
    assert isinstance(store, MemoryStore)
    now = datetime.now(UTC)
    await store.save_ticket(
        USER,
        Ticket(
            "fr.grammar.si_imparfait",
            reopen_count=2,
            examples=[
                Example(
                    now - timedelta(days=1),
                    "Si j'aurais le temps, je viendrais.",
                    "rivemont.vieux_port.apartment_3b:s1",
                )
            ],
        ),
    )
    script.handlers["You are the teacher"] = lambda m: {
        "title": "Si + imparfait",
        "rule": "Après « si » : imparfait, puis conditionnel.",
        "examples": [
            {"learner_said": "Si j'aurais le temps, je viendrais.", "better": "Si j'avais le temps, je viendrais."},
            {"learner_said": "invented mistake", "better": "x"},
        ],
    }
    result = await build_lesson_builder(deps).ainvoke(
        {"user_id": USER, "node_key": "fr.grammar.si_imparfait", "city": "rivemont"}
    )
    lesson = result["lesson"]
    assert [e.learner_said for e in lesson.examples] == ["Si j'aurais le temps, je viendrais."]
    kinds = {g.kind for g in lesson.games}
    assert {"conjugation_duel", "spot_the_error", "sentence_race", "dictation"} <= kinds
    duel = next(g for g in lesson.games if g.kind == "conjugation_duel")
    assert all(("imparfait" in i.prompt) or ("conditionnel" in i.prompt) for i in duel.items)
    assert lesson.homework.targets == ["fr.grammar.si_imparfait"]
    assert lesson.homework.location_key != "rivemont.vieux_port.apartment_3b"
    assert 5 <= lesson.minutes <= 10 and result["lesson_id"] in store.lessons
