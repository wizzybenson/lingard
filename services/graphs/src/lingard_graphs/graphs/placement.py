"""``placement`` graph (SPEC §11, §17): interactive quick placement, a mock hand-off, or skip with wide priors.

Learner input arrives through LangGraph ``interrupt``/resume (Postgres checkpointer in deployment). Adaptive item
selection is a pure function of previous answers, so replays on resume are exact; LLM scoring runs in its own
nodes so it never re-executes on resume.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

import yaml
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict

from lingard_contracts.common import LANGUAGE_CITY, LANGUAGE_NAME, LANGUAGE_PACK, Language, Skill
from lingard_curriculum.packs import TaskDef
from lingard_exam_packs.adaptive import Estimate, estimate, next_item, should_stop
from lingard_exam_packs.items import ItemBank, band_to_logit
from lingard_exam_packs.serving import is_correct, serve
from lingard_graphs.agents.writing import WritingExaminer
from lingard_graphs.deps import GraphDeps
from lingard_graphs.pedagogy.bands import observe, prior
from lingard_graphs.pedagogy.tickets import Example, record_error
from lingard_world import load_city

SE_THRESHOLD = 0.5
MAX_ITEMS = 15
START_BAND = 6
CITY_FOR = LANGUAGE_CITY


class SpeakingCheck(BaseModel):
    met: bool
    level_estimate: int
    reason: str = ""


class PlacementState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: uuid.UUID
    language: Language
    path: Literal["quick", "mock", "skip"] = "quick"
    in_fiction: bool = True
    trace_id: str | None = None
    listening: list[tuple[str, bool]] = []
    reading: list[tuple[str, bool]] = []
    writing_text: str = ""
    writing_band: float | None = None
    writing_tags: list[tuple[str, str]] = []
    speaking_index: int = 0
    speaking_failures: int = 0
    speaking_transcript: str = ""
    speaking_level: int = 3
    read_aloud: dict[str, Any] = {}
    estimates: dict[str, float] = {}
    start_district: str | None = None
    status: str = "running"


def _content(deps: GraphDeps, language: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((deps.content_root / "placement" / f"{language}.yaml").read_text())
    return data


def build_placement(
    deps: GraphDeps, bank: ItemBank, checkpointer: BaseCheckpointSaver[str] | None = None
) -> CompiledStateGraph[PlacementState, Any, PlacementState, PlacementState]:
    examiner = WritingExaminer(deps.router, deps.prompts, deps.content_root)
    speaking_prompt = deps.prompts.get("placement_speaking")
    rules = deps.pedagogy

    def adaptive(skill: Skill, field: Literal["listening", "reading"]) -> Any:
        async def node(state: PlacementState) -> dict[str, Any]:
            pack = LANGUAGE_PACK[state.language]
            seed = str(state.user_id)
            answers: list[tuple[str, bool]] = []
            current = estimate([], prior_mean=band_to_logit(START_BAND))
            while not should_stop(current, len(answers), se_threshold=SE_THRESHOLD, max_items=MAX_ITEMS):
                seen = {i for i, _ in answers}
                item = next_item(bank.select(pack, skill, exclude=seen), current)
                if item is None:
                    break
                served = serve(item, seed, audio_ref=f"tts:{item.id}" if skill is Skill.LISTENING else None)
                choice = interrupt({"kind": "item", "skill": skill.value, "item": served.model_dump()})
                answers.append((item.id, is_correct(item, seed, int(choice))))
                current = estimate(
                    [(bank.get(i).difficulty, ok) for i, ok in answers], prior_mean=band_to_logit(START_BAND)
                )
            return {field: answers}

        return node

    async def choose_path(state: PlacementState) -> dict[str, Any]:
        return {"status": "handed_to_exam_hall" if state.path == "mock" else "running"}

    async def writing_task(state: PlacementState) -> dict[str, Any]:
        task = _content(deps, state.language)["writing"]
        text = interrupt({"kind": "writing", "prompt": task["prompt"], "min_words": task["min_words"]})
        return {"writing_text": str(text)}

    async def score_writing(state: PlacementState) -> dict[str, Any]:
        content = _content(deps, state.language)["writing"]
        pack_id = LANGUAGE_PACK[state.language]
        pack = deps.packs.pack(pack_id)
        base = pack.section_for(Skill.WRITING).tasks[0]
        task = TaskDef(
            id=content["task_id"],
            kind="email",
            min_words=content["min_words"],
            suggested_minutes=15,
            rubric=base.rubric,
        )
        nodes = await deps.nodes_for(state.language, max_band=10)
        result = await examiner.score(
            pack=pack,
            conversion=deps.packs.conversion(pack_id),
            task=task,
            task_prompt=content["prompt"],
            response=state.writing_text,
            nodes=nodes,
            trace_id=state.trace_id,
        )
        tags = [(t.node_key, t.span.text) for t in result.error_tags if t.confidence >= 0.7]
        return {"writing_band": result.band_or_points, "writing_tags": tags}

    async def speaking_prompt_node(state: PlacementState) -> dict[str, Any]:
        level = _content(deps, state.language)["speaking"][state.speaking_index]
        transcript = interrupt(
            {"kind": "speaking", "prompt": level["prompt"], "level": level["level"], "in_fiction": state.in_fiction}
        )
        return {"speaking_transcript": str(transcript)}

    async def speaking_assess(state: PlacementState) -> dict[str, Any]:
        levels = _content(deps, state.language)["speaking"]
        level = levels[state.speaking_index]
        text = speaking_prompt.render(
            language_name=LANGUAGE_NAME[state.language],
            level=level["level"],
            kind=level["kind"],
            prompt=level["prompt"],
            transcript=state.speaking_transcript,
        )
        check = await deps.router.structured(
            "mid", speaking_prompt, SpeakingCheck, [HumanMessage(content=text)], trace_id=state.trace_id
        )
        failures = 0 if check.met else state.speaking_failures + 1
        reached = level["level"] if check.met else state.speaking_level
        return {
            "speaking_failures": failures,
            "speaking_level": max(reached, state.speaking_level),
            "speaking_index": state.speaking_index + 1,
        }

    def after_speaking(state: PlacementState) -> str:
        levels = _content(deps, state.language)["speaking"]
        done = state.speaking_failures >= 2 or state.speaking_index >= len(levels)
        return "read_aloud" if done else "speaking_interview"

    async def read_aloud(state: PlacementState) -> dict[str, Any]:
        text = _content(deps, state.language)["read_aloud"]["text"]
        answer = interrupt({"kind": "read_aloud", "text": text, "asks_clone_consent": True})
        return {"read_aloud": dict(answer) if isinstance(answer, dict) else {"audio_ref": str(answer)}}

    async def score(state: PlacementState) -> dict[str, Any]:
        estimates: dict[str, float] = {}
        for field, skill in (("listening", Skill.LISTENING), ("reading", Skill.READING)):
            answers: list[tuple[str, bool]] = getattr(state, field)
            if answers:
                result: Estimate = estimate(
                    [(bank.get(i).difficulty, ok) for i, ok in answers], prior_mean=band_to_logit(START_BAND)
                )
                estimates[skill.value] = round(result.band, 2)
        pack_id = LANGUAGE_PACK[state.language]
        conversion = deps.packs.conversion(pack_id)
        if state.writing_band is not None:
            estimates["writing"] = float(conversion.to_level(Skill.WRITING, state.writing_band))
        estimates["speaking"] = float(state.speaking_level)
        return {"estimates": estimates}

    async def seed_learner_model(state: PlacementState) -> dict[str, Any]:
        """Write posteriors per skill (placement weight; wide priors on skip) and the first tickets."""
        pack_id = LANGUAGE_PACK[state.language]
        pack, conversion = deps.packs.pack(pack_id), deps.packs.conversion(pack_id)
        levels = []
        for skill in Skill:
            level = state.estimates.get(skill.value)
            posterior = prior(pack, skill, None, rules.bands)
            if level is not None and state.path == "quick":
                score_value = conversion.min_score_for(skill, max(4, round(level)))
                if pack.scale.type == "band" and level < 4:
                    score_value = 3.5
                posterior = observe(posterior, pack, skill, score_value, "placement", rules.bands)
                levels.append(level)
            await deps.store.save_posterior(state.user_id, pack_id, skill.value, posterior)
        band = round(sum(levels) / len(levels)) if levels else 4
        await deps.store.save_language_band(state.user_id, state.language, max(1, band))
        tickets = await deps.store.tickets(state.user_id, active_only=False)
        now = deps.clock()
        for node_key, text in state.writing_tags:
            errors = await deps.store.recent_errors(state.user_id, node_key)
            await deps.store.record_error_time(state.user_id, node_key, now)
            ticket, _ = record_error(
                tickets.get(node_key), node_key, Example(now, text, "placement:writing"), 0.6, errors, rules.tickets
            )
            if ticket is not None:
                tickets[node_key] = ticket
                await deps.store.save_ticket(state.user_id, ticket)
        return {}

    async def pick_start_district(state: PlacementState) -> dict[str, Any]:
        city = load_city(deps.content_root, CITY_FOR[state.language])
        profile = await deps.store.profile(state.user_id)
        band = profile.language_bands.get(state.language, 1)
        start = city.unlocked_districts(band)[0]
        return {"start_district": start, "status": "done"}

    graph = StateGraph(PlacementState)
    graph.add_node("choose_path", choose_path)
    graph.add_node("adaptive_listening", adaptive(Skill.LISTENING, "listening"))
    graph.add_node("adaptive_reading", adaptive(Skill.READING, "reading"))
    graph.add_node("writing_task", writing_task)
    graph.add_node("score_writing", score_writing)
    graph.add_node("speaking_interview", speaking_prompt_node)
    graph.add_node("speaking_assess", speaking_assess)
    graph.add_node("read_aloud", read_aloud)
    graph.add_node("score", score)
    graph.add_node("seed_learner_model", seed_learner_model)
    graph.add_node("pick_start_district", pick_start_district)
    graph.add_edge(START, "choose_path")
    graph.add_conditional_edges(
        "choose_path",
        lambda s: {"quick": "adaptive_listening", "skip": "seed_learner_model", "mock": END}[s.path],
        ["adaptive_listening", "seed_learner_model", END],
    )
    graph.add_edge("adaptive_listening", "adaptive_reading")
    graph.add_edge("adaptive_reading", "writing_task")
    graph.add_edge("writing_task", "score_writing")
    graph.add_edge("score_writing", "speaking_interview")
    graph.add_edge("speaking_interview", "speaking_assess")
    graph.add_conditional_edges("speaking_assess", after_speaking, ["speaking_interview", "read_aloud"])
    graph.add_edge("read_aloud", "score")
    graph.add_edge("score", "seed_learner_model")
    graph.add_edge("seed_learner_model", "pick_start_district")
    graph.add_edge("pick_start_district", END)
    return graph.compile(checkpointer=checkpointer)
