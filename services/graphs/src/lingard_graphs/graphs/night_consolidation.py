"""``night_consolidation`` graph (SPEC §11): session end → notebook, bands, FSRS, tickets, sim CRS, rewards, memory."""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field

from agent_memory import MemoryItem, MemoryKind, ScopedMemory, curate
from lingard_contracts.assessment import UtteranceAssessment
from lingard_contracts.common import CITY_LANGUAGE, LANGUAGE_PACK, Skill
from lingard_curriculum.models import CurriculumNode
from lingard_economy.crs import CrsInputs, LanguageLevels, compute
from lingard_economy.events import streak
from lingard_economy.rewards import COINS, LedgerEntry
from lingard_graphs.agents.coach import Coach, Notebook
from lingard_graphs.deps import GraphDeps
from lingard_graphs.graphs._build import linear
from lingard_graphs.pedagogy.bands import BandPosterior, observe, prior
from lingard_graphs.pedagogy.review import new_card
from lingard_graphs.store import SceneRecord
from lingard_world import load_city


class WorldUpdate(BaseModel):
    class Relationship(BaseModel):
        npc_key: str
        affinity_delta: float = Field(ge=-0.3, le=0.3)
        summary: str

    story_flags: dict[str, str] = {}
    relationships: list[Relationship] = []


class NightState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: uuid.UUID
    session_id: uuid.UUID
    trace_id: str | None = None
    scenes: list[SceneRecord] = []
    assessments: list[UtteranceAssessment] = []
    language: str = "fr"
    nodes: dict[str, CurriculumNode] = {}
    notebook: Notebook | None = None
    language_band: int | None = None
    sim_crs: int | None = None
    coins_awarded: int = 0
    world_flags: dict[str, str] = {}


def world_namespace(user_id: uuid.UUID, city: str) -> tuple[str, ...]:
    return ("user", str(user_id), "world", city)


def confident_level(posterior: BandPosterior, thresholds: dict[int, float], confidence: float) -> int:
    """Highest CLB/NCLC level the learner reaches with probability ≥ ``confidence`` (SPEC §18.2)."""
    reached = [level for level, minimum in thresholds.items() if posterior.probability_at_least(minimum) >= confidence]
    return max(reached, default=0)


def build_night_consolidation(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver[str] | None = None
) -> CompiledStateGraph[NightState, Any, NightState, NightState]:
    coach = Coach(deps.router, deps.prompts)
    keeper_prompt = deps.prompts.get("narrative_keeper")
    rules = deps.pedagogy

    async def summarise_session(state: NightState) -> dict[str, Any]:
        scenes = await deps.store.scenes_for_session(state.session_id)
        scenes = [s for s in scenes if s.user_id == state.user_id]
        assessments = [a for s in scenes for a in await deps.store.assessments_for_scene(s.scene_id)]
        language = CITY_LANGUAGE[scenes[0].contract.city] if scenes else "fr"
        keys = sorted(
            {t.node_key for a in assessments for t in a.error_tags}
            | {e.node_key for a in assessments for e in a.target_evidence}
        )
        nodes = {k: n for k in keys if (n := await deps.curriculum.get(k)) is not None}
        return {"scenes": scenes, "assessments": assessments, "language": language, "nodes": nodes}

    async def coach_notebook(state: NightState) -> dict[str, Any]:
        profile = await deps.store.profile(state.user_id)
        tickets = await deps.store.tickets(state.user_id)
        lessons = sorted(k for k, t in tickets.items() if t.reopen_count >= rules.tickets.lesson_after_reopens)
        notebook = await coach.notebook(
            state.assessments,
            state.nodes,
            language=state.language,
            ui_language=profile.l1 if profile.l1 in ("fr", "en") else "en",
            band=profile.language_bands.get(state.language, 5),
            lessons_suggested=lessons,
            trace_id=state.trace_id,
        )
        await deps.store.save_notebook(state.user_id, state.session_id, notebook.model_dump())
        return {"notebook": notebook}

    async def update_mastery(state: NightState) -> dict[str, Any]:
        """Turn-level band estimates feed the speaking posterior at low weight (SPEC §12.2)."""
        pack_id = LANGUAGE_PACK[state.language]
        pack = deps.packs.pack(pack_id)
        posteriors = await deps.store.posteriors(state.user_id)
        posterior = posteriors.get((pack_id, "speaking")) or prior(pack, Skill.SPEAKING, None, rules.bands)
        observed = [a.band_estimate for a in state.assessments if a.band_estimate is not None and a.confidence >= 0.5]
        conversion = deps.packs.conversion(pack_id)
        for estimate in observed:
            score = (
                estimate
                if pack.scale.type == "band"
                else conversion.mid_score_for(Skill.SPEAKING, round(estimate), pack.max_score(Skill.SPEAKING))
            )
            posterior = observe(posterior, pack, Skill.SPEAKING, score, "turn", rules.bands)
        await deps.store.save_posterior(state.user_id, pack_id, "speaking", posterior)
        level = conversion.to_level(Skill.SPEAKING, posterior.mean)
        if observed and level:
            await deps.store.save_language_band(state.user_id, state.language, max(level, 1))
        return {"language_band": level or None}

    async def update_fsrs(state: NightState) -> dict[str, Any]:
        cards = await deps.store.fsrs(state.user_id)
        for key in state.notebook.review_items if state.notebook else []:
            if key not in cards:
                await deps.store.save_fsrs(state.user_id, key, new_card())
        return {}

    async def update_tickets(state: NightState) -> dict[str, Any]:
        """Tickets move per turn; at night only the lesson queue is derived (already on the notebook)."""
        return {}

    async def update_sim_crs(state: NightState) -> dict[str, Any]:
        profile = await deps.store.profile(state.user_id)
        if not profile.crs_inputs:
            return {}
        posteriors = await deps.store.posteriors(state.user_id)
        levels: dict[str, dict[str, int]] = {}
        for pack_id in ("ielts_gt", "tef_canada"):
            conversion = deps.packs.conversion(pack_id)
            per_skill = {}
            for skill in Skill:
                posterior = posteriors.get((pack_id, skill.value))
                thresholds = {lv: mins[skill] for lv, mins in conversion.levels.items()}
                per_skill[skill.value] = (
                    confident_level(posterior, thresholds, rules.bands.crs_confidence) if posterior else 0
                )
            levels[pack_id] = per_skill
        english, french = levels["ielts_gt"], levels["tef_canada"]
        french_first = sum(french.values()) > sum(english.values())
        result = compute(
            CrsInputs.model_validate(profile.crs_inputs),
            LanguageLevels(
                first=french if french_first else english,
                first_is_french=french_first,
                second=english if french_first else french,
            ),
            deps.content_root / "crs" / "crs_grid.yaml",
        )
        previous = await deps.store.latest_crs(state.user_id)
        if previous != result.total:
            await deps.store.save_crs_snapshot(state.user_id, result.total, result.model_dump())
        return {"sim_crs": result.total}

    async def award_rewards(state: NightState) -> dict[str, Any]:
        entries = [
            LedgerEntry("coins", COINS["quest_complete"], "quest_complete", str(s.scene_id), f"quest:{s.scene_id}")
            for s in state.scenes
            if s.status in ("live", "done")
        ]
        current, _ = streak(await deps.store.active_days(state.user_id), deps.clock().date())
        if current:
            day = deps.clock().date().isoformat()
            entries.append(LedgerEntry("coins", COINS["streak_day"], "streak_day", day, f"streak:{day}"))
        added = await deps.store.apply_ledger(state.user_id, entries)
        return {"coins_awarded": sum(e.delta for e in entries[:added]) if added else 0}

    async def memory_curate(state: NightState) -> dict[str, Any]:
        """Narrative Keeper: world memory only. Pedagogy can't be written here by construction (scoped view)."""
        if not state.scenes:
            return {}
        city = state.scenes[0].contract.city
        content = load_city(deps.content_root, city)
        namespace = world_namespace(state.user_id, city)
        world_view = ScopedMemory(deps.memory, [namespace])
        world = await deps.store.world_state(state.user_id, city)
        lines = []
        for scene in state.scenes:
            turns = await deps.store.turns(scene.scene_id)
            npc = scene.contract.cast[0].npc_key
            transcript = " / ".join(
                f"{'learner' if t.speaker == 'learner' else npc}: {t.transcript}" for t in turns[-12:]
            )
            lines.append(
                f"- {content.npc(npc).name} at {content.location(scene.contract.location_key).name}: "
                f"goal '{scene.contract.learner_goal}'. {transcript}"
            )
        text = keeper_prompt.render(scenes="\n".join(lines), flags=world.get("story_flags", {}))
        update = await deps.router.structured(
            "mid", keeper_prompt, WorldUpdate, [HumanMessage(content=text)], trace_id=state.trace_id
        )
        flags = {**world.get("story_flags", {}), **update.story_flags}
        await deps.store.save_world_state(state.user_id, city, {**world, "story_flags": flags})
        for rel in update.relationships:
            if rel.npc_key not in content.npcs:
                continue
            affinity, _ = await deps.store.relationship(state.user_id, rel.npc_key)
            await deps.store.save_relationship(
                state.user_id, rel.npc_key, max(-1.0, min(1.0, affinity + rel.affinity_delta)), rel.summary
            )
            await world_view.put(
                MemoryItem(
                    namespace=(*namespace, rel.npc_key),
                    kind=MemoryKind.EPISODIC,
                    content=rel.summary,
                    embedding=deps.embedder.embed(rel.summary),
                    importance=min(1.0, 0.5 + abs(rel.affinity_delta)),
                )
            )
        await curate(deps.memory, namespace)
        return {"world_flags": flags}

    graph = StateGraph(NightState)
    steps = [
        ("summarise_session", summarise_session),
        ("coach_notebook", coach_notebook),
        ("update_mastery", update_mastery),
        ("update_fsrs", update_fsrs),
        ("update_tickets", update_tickets),
        ("update_sim_crs", update_sim_crs),
        ("award_rewards", award_rewards),
        ("memory_curate", memory_curate),
    ]
    linear(graph, steps)
    return graph.compile(checkpointer=checkpointer)
