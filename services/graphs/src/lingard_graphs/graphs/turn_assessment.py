"""``turn_assessment`` graph (SPEC §11): turn event → assessment, evidence updates, maybe a steering hint."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict

from lingard_contracts.assessment import UtteranceAssessment
from lingard_contracts.common import CITY_LANGUAGE, LANGUAGE_PACK, node_language
from lingard_contracts.events import TurnEvent
from lingard_curriculum.models import CurriculumNode
from lingard_graphs.agents.assessor import UtteranceAssessor
from lingard_graphs.deps import GraphDeps
from lingard_graphs.pedagogy.mastery import MasteryState, apply_evidence
from lingard_graphs.pedagogy.review import new_card, review
from lingard_graphs.pedagogy.tickets import Example, Success, record_error, record_success
from lingard_graphs.store import SceneRecord
from lingard_world import load_city

INTENSITY_DIFFICULTY = {"calm": 0.4, "tense": 0.6, "heated": 0.8}


def _ticketable(node: CurriculumNode | None, learner_band: int, max_bands_above: int) -> bool:
    """Errors on stretch material well above the learner's band are expected exposure, not weaknesses to ticket."""
    return node is None or node.band <= learner_band + max_bands_above


class TurnState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    event: TurnEvent
    skip: bool = False
    scene: SceneRecord | None = None
    learner_band: int = 5
    nodes: dict[str, CurriculumNode] = {}
    assessment: UtteranceAssessment | None = None
    ticket_events: list[str] = []
    hint: str | None = None


def build_turn_assessment(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver[str] | None = None
) -> CompiledStateGraph[TurnState, Any, TurnState, TurnState]:
    assessor = UtteranceAssessor(deps.router, deps.prompts, deps.pedagogy.corrections.min_confidence)

    async def fetch_context(state: TurnState) -> dict[str, Any]:
        event = state.event
        if event.speaker != "learner" or await deps.store.assessment_exists(event.event_id):
            return {"skip": True}  # idempotent on event_id (at-least-once delivery)
        await deps.store.save_turn(event)
        scene = await deps.store.scene(event.scene_id)
        if scene is None:
            return {"skip": True}
        language = CITY_LANGUAGE[scene.contract.city]
        profile = await deps.store.profile(event.user_id)
        band = profile.language_bands.get(language, 5)
        nodes = await deps.nodes_for(language, max_band=band + 2)
        for key in scene.contract.targets.all():
            node = await deps.curriculum.get(key)
            if node is not None:
                nodes[key] = node
        return {"scene": scene, "learner_band": band, "nodes": nodes}

    async def score_dimensions(state: TurnState) -> dict[str, Any]:
        assert state.scene is not None
        contract = state.scene.contract
        language = CITY_LANGUAGE[contract.city]
        city = load_city(deps.content_root, contract.city)
        assessment = await assessor.assess(
            state.event,
            pack=deps.packs.pack(LANGUAGE_PACK[language]),
            language=language,
            learner_band=state.learner_band,
            npc_name=city.npc(contract.cast[0].npc_key).name,
            nodes=state.nodes,
            trace_id=str(state.event.trace_id),
        )
        return {"assessment": assessment}

    async def tag_errors(state: TurnState) -> dict[str, Any]:
        """Low-confidence tags stay as evidence only; nothing here is shown to the learner (Coach decides later)."""
        assert state.assessment is not None
        return {}

    async def map_to_nodes(state: TurnState) -> dict[str, Any]:
        assert state.assessment is not None and state.scene is not None
        language = CITY_LANGUAGE[state.scene.contract.city]
        kept = [t for t in state.assessment.error_tags if node_language(t.node_key) == language]
        return {"assessment": state.assessment.model_copy(update={"error_tags": kept})}

    async def update_evidence(state: TurnState) -> dict[str, Any]:
        assert state.assessment is not None and state.scene is not None
        user_id, now = state.event.user_id, deps.clock()
        context = f"{state.scene.contract.location_key}:{state.scene.scene_id}"
        difficulty = INTENSITY_DIFFICULTY[state.scene.contract.intensity]
        rules = deps.pedagogy
        await deps.store.save_assessment(user_id, state.assessment)

        # One observation per node per turn; an error tag outranks a "correct" evidence claim for the same node.
        by_node: dict[str, tuple[bool, float, str]] = {
            e.node_key: (e.correct, e.confidence, e.span.text if e.span else "")
            for e in state.assessment.target_evidence
        }
        for tag in state.assessment.error_tags:
            by_node[tag.node_key] = (
                False,
                max(tag.confidence, by_node.get(tag.node_key, (False, 0.0, ""))[1]),
                tag.span.text,
            )
        observations = [(key, *value) for key, value in by_node.items()]
        keys = sorted({o[0] for o in observations})
        mastery = await deps.store.mastery(user_id, keys)
        tickets = await deps.store.tickets(user_id, active_only=False)
        fsrs = await deps.store.fsrs(user_id)
        events: list[str] = []
        for key, correct, confidence, text in observations:
            state_m = mastery.setdefault(key, MasteryState(key, rules.bkt.p_init))
            apply_evidence(
                state_m, correct, confidence=confidence, difficulty=difficulty, context=context, params=rules.bkt
            )
            ticket = tickets.get(key)
            if correct:
                if ticket is not None:
                    events += [e.kind for e in record_success(ticket, Success(now, context), rules.tickets)]
                    await deps.store.save_ticket(user_id, ticket)
            elif ticket is not None or _ticketable(
                state.nodes.get(key), state.learner_band, rules.tickets.max_bands_above
            ):
                recent = await deps.store.recent_errors(user_id, key)
                await deps.store.record_error_time(user_id, key, now)
                severity = (
                    0.8 if any(t.severity != "minor" for t in state.assessment.error_tags if t.node_key == key) else 0.5
                )
                ticket, new_events = record_error(
                    ticket, key, Example(now, text, context), severity, recent, rules.tickets
                )
                events += [f"{e.kind}:{e.node_key}" for e in new_events]
                if ticket is not None:
                    tickets[key] = ticket
                    await deps.store.save_ticket(user_id, ticket)
            card = review(fsrs.get(key) or new_card(), correct, now=now)
            await deps.store.save_fsrs(user_id, key, card)
        await deps.store.save_mastery(user_id, list(mastery.values()), now)
        return {"ticket_events": events}

    async def maybe_steer(state: TurnState) -> dict[str, Any]:
        """One hint at most every N learner turns, naming an unmet target and a tactic; never a correction."""
        assert state.scene is not None
        contract = state.scene.contract
        turns = [t for t in await deps.store.turns(contract.scene_id) if t.speaker == "learner"]
        every = deps.pedagogy.steering.every_learner_turns
        if not turns or len(turns) % every:
            return {}
        assessments = await deps.store.assessments_for_scene(contract.scene_id)
        evidenced: dict[str, int] = {}
        for a in assessments:
            for e in a.target_evidence:
                if e.correct or e.span is not None:
                    evidenced[e.node_key] = evidenced.get(e.node_key, 0) + 1
        missing = [spec for spec in contract.evidence_required if evidenced.get(spec.target, 0) < spec.min_uses]
        if not missing:
            return {}
        target = missing[0].target
        tactic = next((t.tactic for t in contract.elicitation if t.target == target), "")
        title = state.nodes[target].title if target in state.nodes else target
        left = max(contract.max_turns - len(turns), 0)
        hint = f"Not yet drawn out: {title}. {left} turns left. Try: {tactic}"[: deps.pedagogy.steering.max_hint_chars]
        await deps.hints.put(str(contract.scene_id), hint)
        return {"hint": hint}

    def route_after_fetch(state: TurnState) -> str:
        return END if state.skip else "score_dimensions"

    graph = StateGraph(TurnState)
    for name, fn in (
        ("fetch_context", fetch_context),
        ("score_dimensions", score_dimensions),
        ("tag_errors", tag_errors),
        ("map_to_nodes", map_to_nodes),
        ("update_evidence", update_evidence),
        ("maybe_steer", maybe_steer),
    ):
        graph.add_node(name, fn)
    graph.add_edge(START, "fetch_context")
    graph.add_conditional_edges("fetch_context", route_after_fetch, ["score_dimensions", END])
    graph.add_edge("score_dimensions", "tag_errors")
    graph.add_edge("tag_errors", "map_to_nodes")
    graph.add_edge("map_to_nodes", "update_evidence")
    graph.add_edge("update_evidence", "maybe_steer")
    graph.add_edge("maybe_steer", END)
    return graph.compile(checkpointer=checkpointer)
