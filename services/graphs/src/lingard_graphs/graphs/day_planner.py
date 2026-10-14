"""``day_planner`` graph (SPEC §11): learner model → targets → story beats → compiled scenes → persisted plan."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict

from lingard_contracts.common import CITY_LANGUAGE, LANGUAGE_PACK, CityKey
from lingard_contracts.planning import DayPlan, LessonSlot, SceneBrief
from lingard_contracts.scene import INTENSITY_ORDER, SceneContract
from lingard_curriculum.packs import ExamPack
from lingard_graphs.agents.scene_compiler import CompileError, SceneCompiler
from lingard_graphs.deps import GraphDeps
from lingard_graphs.pedagogy.mastery import MasteryState
from lingard_graphs.pedagogy.review import due_at
from lingard_graphs.pedagogy.selection import Candidate, Slot, plan_targets
from lingard_graphs.pedagogy.tickets import Ticket
from lingard_graphs.store import LearnerProfileView, SceneRecord
from lingard_world import load_city

logger = logging.getLogger(__name__)
SCENE_KINDS = ("function", "grammar", "lexset")
PERSUASION = {"negotiate", "persuade", "argue_point_of_view", "concede_and_counter", "hypothesise"}


class Beats(BaseModel):
    beats: list[str]


class PlanState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: uuid.UUID
    session_id: uuid.UUID
    city: CityKey
    trace_id: str | None = None
    profile: LearnerProfileView | None = None
    band: int = 5
    mastery: dict[str, MasteryState] = {}
    tickets: dict[str, Ticket] = {}
    settings: list[tuple[str, str]] = []
    """(location_key, npc_key) pairs available today."""
    slots: list[Slot] = []
    beats: list[str] = []
    contracts: list[SceneContract] = []
    lessons: list[LessonSlot] = []
    plan: DayPlan | None = None


def aged_priority(ticket: Ticket, today: datetime, per_day: float) -> float:
    """Priority grows with days since the ticket was last practised, so no open ticket is starved."""
    moments = [e.at for e in ticket.examples] + [s.at for s in ticket.successes]
    idle_days = (today - max(moments)).days if moments else 0
    return ticket.priority + per_day * max(idle_days, 0)


def pack_alignment(pack: ExamPack, targets: list[str]) -> list[str]:
    persuasive = any(t.split(".")[-1] in PERSUASION for t in targets)
    return [pack.scene_alignment["persuasive" if persuasive else "default"]]


def build_day_planner(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver[str] | None = None
) -> CompiledStateGraph[PlanState, Any, PlanState, PlanState]:
    compiler = SceneCompiler(deps.router, deps.prompts, deps.curriculum, deps.content_root)
    beats_prompt = deps.prompts.get("story_beats")
    rules = deps.pedagogy

    async def load_learner_model(state: PlanState) -> dict[str, Any]:
        profile = await deps.store.profile(state.user_id)
        language = CITY_LANGUAGE[state.city]
        band = profile.language_bands.get(language, 4)
        city = load_city(deps.content_root, state.city)
        world = await deps.store.world_state(state.user_id, state.city)
        unlocked = set(city.unlocked_districts(band, world.get("district_unlocks", [])))
        settings = [
            (location.key, hotspot.npc_key)
            for district in city.city.districts
            if district.key in unlocked
            for location in district.locations
            for hotspot in location.hotspots
            if hotspot.kind == "npc" and hotspot.npc_key
        ]
        tickets = {k: t for k, t in (await deps.store.tickets(state.user_id)).items() if k.startswith(f"{language}.")}
        return {
            "profile": profile,
            "band": band,
            "mastery": await deps.store.all_mastery(state.user_id),
            "tickets": tickets,
            "settings": settings,
        }

    async def select_targets(state: PlanState) -> dict[str, Any]:
        language = CITY_LANGUAGE[state.city]
        nodes = await deps.curriculum.nodes(language, kinds=SCENE_KINDS, max_band=state.band + 2)  # type: ignore[arg-type]
        today = deps.clock()
        ticket_candidates = [
            Candidate(
                key,
                aged_priority(ticket, today, rules.director.ticket_ageing_per_day),
                frozenset({ticket.examples[-1].context.split(":")[0]}) if ticket.examples else frozenset(),
            )
            for key, ticket in state.tickets.items()
            if any(n.key == key for n in nodes)
        ]
        fresh = []
        reviews = []
        cards = await deps.store.fsrs(state.user_id)
        now = deps.clock()
        for node in nodes:
            if node.key in state.tickets or node.band < state.band - 1:
                continue
            p = state.mastery[node.key].p_mastery if node.key in state.mastery else rules.bkt.p_init
            if p >= rules.bkt.mastered:
                due = due_at(cards[node.key]) if node.key in cards else now
                # Mastered material comes back as low-priority review, soonest-due first.
                reviews.append(Candidate(node.key, 0.3 if due <= now else 0.1 / (1 + (due - now).days)))
                continue
            weight = {0: 1.2, 1: 0.8}.get(node.band - state.band, 0.5 if node.band > state.band else 0.6)
            fresh.append(Candidate(node.key, (1 - p) * weight))
        fresh += reviews
        count = min(rules.director.scenes_per_day, len(state.settings))
        # Rotate by day so every unlocked district gets visited, not only the first one in content order.
        offset = today.toordinal() % len(state.settings) if state.settings else 0
        rotated = state.settings[offset:] + state.settings[:offset]
        chosen_settings = [loc for loc, _ in rotated[:count]]
        slots = plan_targets(ticket_candidates, fresh, chosen_settings, rules.director)
        lessons = [
            LessonSlot(node_key=k, reason="ticket_reopened")
            for k, t in state.tickets.items()
            if t.reopen_count >= rules.tickets.lesson_after_reopens
        ]
        return {"slots": slots, "lessons": lessons}

    async def plan_story_beats(state: PlanState) -> dict[str, Any]:
        assert state.profile is not None
        city = load_city(deps.content_root, state.city)
        world = await deps.store.world_state(state.user_id, state.city)
        npc_for = dict(state.settings)
        relationships = []
        for slot in state.slots:
            affinity, summary = await deps.store.relationship(state.user_id, npc_for[slot.setting])
            relationships.append(
                f"{city.npc(npc_for[slot.setting]).name}: {summary or 'not met yet'} ({affinity:+.1f})"
            )
        settings_text = "\n".join(
            f"{i + 1}. {city.location(s.setting).name} with {city.npc(npc_for[s.setting]).name}"
            for i, s in enumerate(state.slots)
        )
        text = beats_prompt.render(
            city_name=city.city.name,
            story_state=world.get("story_flags") or "just arrived",
            relationships="; ".join(relationships),
            count=len(state.slots),
            settings=settings_text,
        )
        beats = await deps.router.structured(
            "mid", beats_prompt, Beats, [HumanMessage(content=text)], trace_id=state.trace_id
        )
        padded = (beats.beats + ["An ordinary day in the neighbourhood."] * len(state.slots))[: len(state.slots)]
        return {"beats": padded}

    async def compile_scenes(state: PlanState) -> dict[str, Any]:
        assert state.profile is not None
        npc_for = dict(state.settings)
        cap = state.profile.intensity_cap
        intensity = "calm" if state.band <= 4 else "tense"
        if INTENSITY_ORDER[intensity] > INTENSITY_ORDER.get(cap, 1):
            intensity = cap
        pack = deps.packs.pack(LANGUAGE_PACK[CITY_LANGUAGE[state.city]])
        briefs = [
            SceneBrief(
                city=state.city,
                location_key=slot.setting,
                npc_keys=[npc_for[slot.setting]],
                story_beat=beat,
                targets=list(slot.targets),
                ticket_targets=list(slot.ticket_targets),
                learner_band=state.band,
                intensity=intensity,
                pack_alignment=pack_alignment(pack, list(slot.targets)),
            )
            for slot, beat in zip(state.slots, state.beats, strict=True)
        ]
        results = await asyncio.gather(
            *(compiler.compile(b, trace_id=state.trace_id) for b in briefs), return_exceptions=True
        )
        contracts = []
        for brief, result in zip(briefs, results, strict=True):
            if isinstance(result, SceneContract):
                contracts.append(result)
            elif isinstance(result, CompileError):
                logger.warning("scene at %s dropped: %s", brief.location_key, result)
            elif isinstance(result, BaseException):
                raise result
        if not contracts:
            raise CompileError([])
        plan = DayPlan(user_id=state.user_id, city=state.city, scenes=briefs, lessons=state.lessons)
        return {"contracts": contracts, "plan": plan}

    async def validate(state: PlanState) -> dict[str, Any]:
        assert state.plan is not None
        share = state.plan.ticket_share()
        # Too few open tickets to reach the minimum share is expected (supply-limited), not a planning fault.
        total = sum(len(s.targets) for s in state.plan.scenes) or 1
        floor = min(rules.director.ticket_share_min, len(state.tickets) / total)
        if state.tickets and not floor - 0.15 <= share <= rules.director.ticket_share_max + 0.15:
            logger.warning("ticket share %.2f outside the director's range", share)
        return {}

    async def persist_day_plan(state: PlanState) -> dict[str, Any]:
        assert state.plan is not None
        session_id = await deps.store.save_day_plan(state.plan, state.session_id)
        for contract in state.contracts:
            await deps.store.save_scene(SceneRecord(contract.scene_id, state.user_id, session_id, contract))
        return {}

    graph = StateGraph(PlanState)
    for name, fn in (
        ("load_learner_model", load_learner_model),
        ("select_targets", select_targets),
        ("plan_story_beats", plan_story_beats),
        ("compile_scenes", compile_scenes),
        ("validate", validate),
        ("persist_day_plan", persist_day_plan),
    ):
        graph.add_node(name, fn)
    graph.add_edge(START, "load_learner_model")
    graph.add_edge("load_learner_model", "select_targets")
    graph.add_edge("select_targets", "plan_story_beats")
    graph.add_edge("plan_story_beats", "compile_scenes")
    graph.add_edge("compile_scenes", "validate")
    graph.add_edge("validate", "persist_day_plan")
    graph.add_edge("persist_day_plan", END)
    return graph.compile(checkpointer=checkpointer)
