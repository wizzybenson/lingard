import uuid
from typing import Any

import pytest
from langchain_core.messages import BaseMessage

from lingard_contracts.events import NpcContext, TurnEvent
from lingard_contracts.planning import SceneBrief
from lingard_graphs.agents.assessor import heard_in, locate
from lingard_graphs.agents.scene_compiler import CompileError, SceneCompiler
from lingard_graphs.deps import GraphDeps, MemoryHints
from lingard_graphs.graphs.turn_assessment import TurnState, build_turn_assessment
from lingard_graphs.store import MemoryStore, SceneRecord
from lingard_llm.testing import message_text

from .conftest import CONSISTENCY, USER, Script

TARGETS = ["fr.func.negotiate", "fr.grammar.si_imparfait", "fr.lex.housing.deposit_repairs"]


def good_draft(_: list[BaseMessage]) -> dict[str, Any]:
    return {
        "learner_goal": "Récupérer votre dépôt de garantie",
        "elicitation": [
            {"target": "fr.func.negotiate", "tactic": "Offer to return half the deposit and wait for a counter-offer"},
            {
                "target": "fr.grammar.si_imparfait",
                "tactic": "Ask what the tenant would do if he kept the whole deposit",
            },
            {"target": "fr.lex.housing.deposit_repairs", "tactic": "Point at the crack and list repair costs"},
        ],
        "approved_facts": [
            "Le dépôt était de 900 dollars",
            "Le mur du salon a une fissure",
            "Le bail a pris fin le 30 septembre",
            "Martin veut garder 300 dollars pour réparer la fissure",
            "Martin n'a pas encore de devis du peintre",
            "Le bail prévoit que le dépôt est rendu dans les trente jours",
            "Martin rend le reste du dépôt par chèque",
            "Il n'y a pas eu d'état des lieux écrit à l'entrée",
            "Martin accepte de discuter du montant",
            "Martin ne sait pas combien le peintre demandera",
        ],
        "success_conditions": ["Le locataire fait une contre-proposition"],
        "evidence_required": [{"target": "fr.grammar.si_imparfait", "min_uses": 1}],
        "exits": [{"key": "deal", "trigger": "they agree on an amount", "consequence": "part of the deposit returned"}],
        "max_turns": 16,
        "mood": "defensive",
    }


def compiler(deps: GraphDeps) -> SceneCompiler:
    rules = deps.pedagogy.scenes
    return SceneCompiler(
        deps.router,
        deps.prompts,
        deps.curriculum,
        deps.content_root,
        facts_range=(rules.approved_facts_min, rules.approved_facts_max),
    )


def brief() -> SceneBrief:
    return SceneBrief(
        city="rivemont",
        location_key="rivemont.vieux_port.apartment_3b",
        npc_keys=["landlord_martin"],
        story_beat="End of lease; Martin is keeping the deposit.",
        targets=TARGETS,
        learner_band=6,
        intensity="tense",
        pack_alignment=["tef_canada.eo.section_b"],
    )


async def test_compiler_builds_a_valid_contract(deps: GraphDeps, script: Script) -> None:
    script.handlers["You design one scene"] = good_draft
    contract = await compiler(deps).compile(brief())
    assert contract.npc_language_band == 7 and contract.cast[0].voice_id == "fr_m_58_martin"
    assert contract.targets.grammar == ["fr.grammar.si_imparfait"]
    assert contract.accent_variety == ["fr-FR-standard"]


async def test_compiler_feeds_issues_back_then_succeeds(deps: GraphDeps, script: Script) -> None:
    attempts: list[int] = []

    def flaky(messages: list[BaseMessage]) -> dict[str, Any]:
        attempts.append(1)
        draft = good_draft(messages)
        if len(attempts) == 1:
            draft["elicitation"] = draft["elicitation"][:1]  # missing tactics
        else:
            assert "missing_tactic" in message_text(messages[-2])
        return draft

    script.handlers["You design one scene"] = flaky
    await compiler(deps).compile(brief())
    assert len(attempts) == 2


async def test_a_second_reading_sends_contradictions_back_to_the_writer(deps: GraphDeps, script: Script) -> None:
    """The goal puts the router in the living room and an objective puts it on the desk: the writer is told."""
    feedback: list[str] = []
    checked: list[str] = []

    def writer(messages: list[BaseMessage]) -> dict[str, Any]:
        feedback.append(message_text(messages[-2]))
        return good_draft(messages)

    def reader(messages: list[BaseMessage]) -> dict[str, Any]:
        checked.append(" ".join(message_text(m) for m in messages))
        return {"problems": ["The goal puts the router in the living room; objective 2 puts it on the desk."]}

    script.handlers["You design one scene"] = writer
    script.handlers[CONSISTENCY] = lambda m: reader(m) if not checked else {"problems": []}
    await compiler(deps).compile(brief())
    assert len(feedback) == 2 and "inconsistent: The goal puts the router" in feedback[1]
    assert "Approved facts:" in checked[0] and "Prize (best ending):" in checked[0]

    script.handlers[CONSISTENCY] = reader  # never fixed: the scene is dropped rather than played inconsistent
    with pytest.raises(CompileError, match="inconsistent"):
        await compiler(deps).compile(brief())


async def test_compiler_states_the_register_and_coherence_standard(deps: GraphDeps, script: Script) -> None:
    """Goals in a learning app must not switch between « vous » and « tu »; the model is told the standard."""
    systems: list[str] = []

    def record(messages: list[BaseMessage]) -> dict[str, Any]:
        systems.append(message_text(messages[0]))
        return good_draft(messages)

    script.handlers["You design one scene"] = record
    await compiler(deps).compile(brief())
    assert "vouvoiement" in systems[0], "the register comes from content/languages/fr.yaml"
    assert "Keep one register throughout the scene" in systems[0]


async def test_compiler_asks_again_for_a_thin_scene(deps: GraphDeps, script: Script) -> None:
    seen: list[str] = []
    systems: list[str] = []

    def thin_then_rich(messages: list[BaseMessage]) -> dict[str, Any]:
        draft = good_draft(messages)
        seen.append(message_text(messages[-2]))
        systems.append(message_text(messages[0]))
        if len(seen) == 1:
            draft["approved_facts"] = draft["approved_facts"][:3]
        return draft

    script.handlers["You design one scene"] = thin_then_rich
    contract = await compiler(deps).compile(brief())
    assert "thin_facts" in seen[1] and len(contract.approved_facts) >= deps.pedagogy.scenes.approved_facts_min
    assert "Bail du 1er octobre" in systems[0], "the compiler sees what is written in the place"


async def test_compiler_rejects_unreviewed_targets(deps: GraphDeps) -> None:
    await deps.curriculum.unmark_reviewed("fr.grammar.si_imparfait")
    with pytest.raises(CompileError):
        await compiler(deps).compile(brief())


def test_locate_requires_real_span() -> None:
    text = "si j'aurais su je serais venu"
    span = locate(text, "Si j'aurais")
    assert span is not None and (span.start, span.end) == (0, 11)
    assert locate(text, "si j'avais") is None


def assessor_answer(messages: list[BaseMessage]) -> dict[str, Any]:
    return {
        "dimensions": [
            {"dimension": "fluency", "score": 6, "confidence": 0.6},
            {"dimension": "grammatical_control", "score": 5, "confidence": 0.7},
            {"dimension": "invented_dimension", "score": 9, "confidence": 1.0},
        ],
        "errors": [
            {
                "node_key": "fr.grammar.si_imparfait",
                "span": "si je refuserais",
                "correction": "si je refusais",
                "explanation": "no conditional after si",
                "severity": "major",
                "confidence": 0.93,
            },
            {"node_key": "fr.grammar.articles_gender", "span": "not in transcript", "confidence": 0.99},
            {"node_key": "fr.grammar.negation", "span": "je vais", "confidence": 0.5},
        ],
        "target_evidence": [
            {"node_key": "fr.grammar.si_imparfait", "correct": False, "span": "si je refuserais", "confidence": 0.9}
        ],
        "band_estimate": 6,
        "confidence": 0.7,
    }


def event(scene_id: uuid.UUID, text: str) -> TurnEvent:
    return TurnEvent(
        trace_id=uuid.uuid4(),
        user_id=USER,
        session_id=uuid.uuid4(),
        scene_id=scene_id,
        turn_index=1,
        speaker="learner",
        language="fr-FR",
        transcript=text,
        npc_context=NpcContext(npc_id="landlord_martin", last_npc_line="Et si je refusais ?"),
        targets_active=TARGETS,
    )


async def setup_scene(deps: GraphDeps, script: Script) -> SceneRecord:
    script.handlers["You design one scene"] = good_draft
    contract = await compiler(deps).compile(brief())
    record = SceneRecord(scene_id=contract.scene_id, user_id=USER, session_id=uuid.uuid4(), contract=contract)
    await deps.store.save_scene(record)
    return record


async def test_turn_assessment_filters_tags_checks_and_updates_evidence(deps: GraphDeps, script: Script) -> None:
    scene = await setup_scene(deps, script)
    script.handlers["silent, rigorous examiner"] = assessor_answer
    script.handlers["Independent check"] = lambda m: {"is_error": True, "confidence": 0.95}
    graph = build_turn_assessment(deps)
    first = event(scene.scene_id, "Bon, si je refuserais votre offre, je vais au tribunal.")
    result = await graph.ainvoke(TurnState(event=first))
    assessment = result["assessment"]
    assert [t.node_key for t in assessment.error_tags] == ["fr.grammar.si_imparfait", "fr.grammar.negation"]
    top = assessment.error_tags[0]
    assert top.span.text == "si je refuserais" and top.showable
    assert not assessment.error_tags[1].showable, "below 0.85 → evidence only, no second check"
    assert {d.dimension for d in assessment.dimensions} == {"fluency", "grammatical_control"}
    store = deps.store
    assert isinstance(store, MemoryStore)
    mastery = await store.mastery(USER, ["fr.grammar.si_imparfait"])
    assert mastery["fr.grammar.si_imparfait"].p_mastery < deps.pedagogy.bkt.p_init
    assert "fr.grammar.si_imparfait" in await store.fsrs(USER)

    second = event(scene.scene_id, "Alors si je refuserais encore, vous gardez tout ?")
    result = await graph.ainvoke(TurnState(event=second))
    assert "opened:fr.grammar.si_imparfait" in result["ticket_events"]
    assert "fr.grammar.si_imparfait" in await store.tickets(USER)

    calls_before = len(script.calls)
    again = await graph.ainvoke(TurnState(event=second))
    assert again["skip"] is True and len(script.calls) == calls_before, "redelivered event is a no-op"


def test_a_span_counts_as_heard_only_when_the_other_recogniser_has_the_same_words() -> None:
    assert heard_in("Bon, si je refuserais votre offre…", "si je refuserais")
    assert heard_in("bon si je REFUSERAIS votre offre", "Si je refuserais"), "case and punctuation don't matter"
    assert not heard_in("Bon, si je refusais votre offre", "si je refuserais")
    assert not heard_in("si je votre refuserais", "si je refuserais"), "together and in order"


async def test_a_mishearing_is_not_the_learners_mistake(deps: GraphDeps, script: Script) -> None:
    """Measured live 2026-10-20: the learner said "nouvel arrivant", streaming STT heard "nouvelle arrivée", and the
    notebook corrected it. A tag whose words the second hearing lacks is dropped: not shown, not evidence."""
    scene = await setup_scene(deps, script)
    script.handlers["silent, rigorous examiner"] = assessor_answer
    script.handlers["Independent check"] = lambda m: {"is_error": True, "confidence": 0.95}
    graph = build_turn_assessment(deps)
    misheard = event(scene.scene_id, "Bon, si je refuserais votre offre, je vais au tribunal.").model_copy(
        update={"transcript_alternatives": ["Bon, si je refusais votre offre, je vais au tribunal."]}
    )
    result = await graph.ainvoke(TurnState(event=misheard))
    assert "fr.grammar.si_imparfait" not in [t.node_key for t in result["assessment"].error_tags]
    store = deps.store
    assert isinstance(store, MemoryStore)
    assert "fr.grammar.si_imparfait" not in await store.tickets(USER)

    heard_twice = event(scene.scene_id, "Bon, si je refuserais votre offre, je vais au tribunal.").model_copy(
        update={"transcript_alternatives": ["bon si je refuserais votre offre je vais au tribunal"]}
    )
    result = await graph.ainvoke(TurnState(event=heard_twice))
    assert result["assessment"].error_tags[0].showable, "both recognisers heard it: a real mistake"


async def test_steering_hint_every_four_turns_without_corrections(deps: GraphDeps, script: Script) -> None:
    scene = await setup_scene(deps, script)
    script.handlers["silent, rigorous examiner"] = lambda m: {
        "dimensions": [],
        "errors": [],
        "target_evidence": [],
        "confidence": 0.5,
    }
    graph = build_turn_assessment(deps)
    hints = deps.hints
    assert isinstance(hints, MemoryHints)
    for i in range(4):
        await graph.ainvoke(TurnState(event=event(scene.scene_id, f"Je voudrais mon dépôt, numéro {i}.")))
        if i < 3:
            assert str(scene.scene_id) not in hints.hints
    hint = hints.hints[str(scene.scene_id)]
    assert "Hypothèse irréelle" in hint and "turns left" in hint
    assert len(hint) <= deps.pedagogy.steering.max_hint_chars


async def test_errors_far_above_band_do_not_open_tickets(deps: GraphDeps, script: Script) -> None:
    scene = await setup_scene(deps, script)
    far = "fr.grammar.voix_passive"  # band 8: assessed (≤ band + 2) but two bands above the band-6 learner
    script.handlers["silent, rigorous examiner"] = lambda m: {
        "dimensions": [],
        "target_evidence": [],
        "confidence": 0.8,
        "errors": [
            {"node_key": far, "span": "la loi a été voté", "confidence": 0.95, "correction": "la loi a été votée"}
        ],
    }
    graph = build_turn_assessment(deps)
    for i in range(3):
        await graph.ainvoke(TurnState(event=event(scene.scene_id, f"Bon, la loi a été voté hier, numéro {i}.")))
    store = deps.store
    assert isinstance(store, MemoryStore)
    assert far not in await store.tickets(USER, active_only=False)
    assert (await store.mastery(USER, [far]))[far].evidence_count == 3, "mastery still learns from stretch errors"
