"""``exam_hall`` graph (SPEC §11, Exam Hall Proctor §10): full mocks in the exact official format and timing.

Sections run in pack order with server-side clocks; answers after a section's deadline are discarded. Receptive
sections are scored by Rasch ability over the items (ours are original, so raw-score tables don't apply);
productive sections by an examiner ensemble (three samples, median). No hints are ever given.
"""

from __future__ import annotations

import asyncio
import random
import statistics
import uuid
from typing import Any

import yaml
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict

from lingard_contracts.common import CITY_LANGUAGE, LANGUAGE_CITY, LANGUAGE_NAME, PackId, Skill
from lingard_contracts.scene import (
    CastMember,
    Condition,
    ElicitationTactic,
    Exit,
    SceneContract,
    SceneTargets,
    npc_band_for,
)
from lingard_curriculum.packs import ExamPack, PartDef, ielts_overall
from lingard_economy.events import landing_day_unlocked
from lingard_economy.rewards import COINS, LedgerEntry
from lingard_exam_packs.adaptive import estimate
from lingard_exam_packs.generator import ItemGenerator
from lingard_exam_packs.items import Item, ItemBank
from lingard_exam_packs.serving import check, serve_set
from lingard_graphs.agents.writing import WritingExaminer, rubric_text
from lingard_graphs.deps import GraphDeps
from lingard_graphs.pedagogy.bands import observe, prior
from lingard_graphs.store import SceneRecord
from lingard_world import load_city

EXAMS = {"tef_canada": "TEF Canada", "ielts_gt": "IELTS General Training"}
TARGET_KINDS = {"functions": "func", "grammar": "grammar", "lexset": "lexset", "pron": "pron"}
"""Scene target lists by the curriculum key segment that marks each kind of node."""
TRANSCRIPT_WAIT_TRIES, TRANSCRIPT_WAIT_S = 10, 0.5
SAMPLES = 3


class MockTasks(BaseModel):
    class Writing(BaseModel):
        task_id: str
        prompt: str

    class Speaking(BaseModel):
        part_id: str
        prompt: str
        targets: list[str] = []
        tactics: list[str] = []
        facts: list[str] = []
        """With facts, the part is played live with the examiner; without, it is answered as a recording."""

    writing: list[Writing]
    speaking: list[Speaking]
    examiner: dict[str, str] | None = None
    """``npc_key`` and ``location_key`` of the examiner who runs live speaking parts."""


class _SpeakingScores(BaseModel):
    class Score(BaseModel):
        dimension: str
        score: float
        rationale: str = ""

    dimensions: list[Score]


class ExamState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: uuid.UUID
    pack: PackId
    trace_id: str | None = None
    attempt: uuid.UUID | None = None
    """Set once when the paper is assembled; seeds the ids of anything created during the mock."""
    item_ids: dict[str, list[str]] = {}
    sets: dict[str, list[list[str]]] = {}
    """Per receptive section, the question groups in serving order (one screen each)."""
    tasks: MockTasks | None = None
    answers: dict[str, list[tuple[str, bool]]] = {}
    writing: dict[str, str] = {}
    speaking: dict[str, str] = {}
    section_index: int = 0
    scores: dict[str, float] = {}
    """Per skill, on the pack's own scale (band or points)."""
    levels: dict[str, int] = {}
    overall: float | None = None
    mock_id: uuid.UUID | None = None


def spread_bands(count: int, low: int = 4, high: int = 10) -> list[int]:
    return [low + round(i * (high - low) / max(count - 1, 1)) for i in range(count)]


def build_exam_hall(
    deps: GraphDeps, bank: ItemBank, checkpointer: BaseCheckpointSaver[str] | None = None
) -> CompiledStateGraph[ExamState, Any, ExamState, ExamState]:
    generator = ItemGenerator(deps.router, deps.prompts)
    examiner = WritingExaminer(deps.router, deps.prompts, deps.content_root)
    tasks_prompt = deps.prompts.get("mock_tasks")
    speaking_prompt = deps.prompts.get("speaking_examiner")
    rules = deps.pedagogy

    async def assemble(state: ExamState) -> dict[str, Any]:
        """Fill every receptive section part by part to its official count from whole question sets in the bank,
        a fresh choice each attempt; generated items only top up a part the bank cannot fill."""
        pack = deps.packs.pack(state.pack)
        rng = random.Random(uuid.uuid4().hex)  # noqa: S311 - varies the paper between attempts; checkpointed
        sets: dict[str, list[list[str]]] = {}
        for section in pack.ordered_sections():
            if section.items is None:
                continue
            parts = section.part_list() or [PartDef(id="", items=section.items)]
            groups: list[list[Item]] = []
            for part in parts:
                needed = part.items or 0
                pool = [g for g in bank.sets(state.pack, section.id).values() if (g[0].part or "") == part.id]
                rng.shuffle(pool)
                chosen = fill(pool, needed)
                short = needed - sum(len(g) for g in chosen)
                if short > 0:
                    chosen += [[i] for i in await top_up(pack, section.skill, part.id, short, state.trace_id)]
                groups += sorted(chosen, key=lambda g: min(i.band for i in g))  # easier first within a part
            sets[section.id] = [[i.id for i in g] for g in groups]
        tasks = authored_tasks(state.pack) or await generated_tasks(pack, state)
        return {
            "sets": sets,
            "item_ids": {k: [i for g in v for i in g] for k, v in sets.items()},
            "tasks": tasks,
            "attempt": uuid.uuid4(),
        }

    async def top_up(pack: ExamPack, skill: Skill, part: str, count: int, trace_id: str | None) -> list[Item]:
        bands = spread_bands(count)
        items: list[Item] = []
        for band in sorted(set(bands)):
            for item in await generator.generate(pack, skill, band, bands.count(band), trace_id=trace_id):
                item = item.model_copy(update={"part": part or None})
                if item.id not in {i.id for i in items}:
                    bank.add(item)
                    items.append(item)
        return items[:count]

    def authored_tasks(pack_id: PackId) -> MockTasks | None:
        """Writing and speaking tasks from the pack's own prompt files, so a mock starts at once and costs nothing."""
        folder = deps.content_root / "packs" / pack_id
        writing_file, speaking_file = folder / "writing_prompts.yaml", folder / "speaking_prompts.yaml"
        if not (writing_file.exists() and speaking_file.exists()):
            return None
        writing, speaking = yaml.safe_load(writing_file.read_text()), yaml.safe_load(speaking_file.read_text())
        pack = deps.packs.pack(pack_id)
        task_ids = [t.id for s in pack.sections for t in s.tasks]
        part_ids = [p.id for s in pack.sections if s.skill is Skill.SPEAKING for p in s.part_list()]
        if not all(writing.get(t) for t in task_ids) or not all(speaking.get(p) for p in part_ids):
            return None
        pick = random.Random(uuid.uuid4().hex)  # noqa: S311

        def speaking_task(part_id: str) -> MockTasks.Speaking:
            chosen = pick.choice(speaking[part_id])
            fields = chosen if isinstance(chosen, dict) else {"prompt": chosen}
            return MockTasks.Speaking(part_id=part_id, **fields)

        return MockTasks(
            writing=[MockTasks.Writing(task_id=t, prompt=pick.choice(writing[t])) for t in task_ids],
            speaking=[speaking_task(p) for p in part_ids],
            examiner=speaking.get("examiner"),
        )

    async def generated_tasks(pack: ExamPack, state: ExamState) -> MockTasks:
        writing_tasks = ", ".join(t.id for s in pack.sections for t in s.tasks)
        speaking_parts = ", ".join(p.id for s in pack.sections if s.skill is Skill.SPEAKING for p in s.part_list())
        return await deps.router.structured(
            "frontier",
            tasks_prompt,
            MockTasks,
            [
                HumanMessage(
                    content=tasks_prompt.render(
                        exam=EXAMS[state.pack],
                        language_name=LANGUAGE_NAME[pack.language],
                        writing_tasks=writing_tasks,
                        speaking_parts=speaking_parts,
                    )
                )
            ],
            trace_id=state.trace_id,
        )

    async def run_section(state: ExamState) -> dict[str, Any]:
        """One section at a time, strictly timed. On resume, answers carry ``elapsed_s`` from the section start."""
        pack = deps.packs.pack(state.pack)
        section = pack.ordered_sections()[state.section_index]
        limit_s = section.max_minutes * 60
        seed = f"{state.user_id}:mock"
        update: dict[str, Any] = {"section_index": state.section_index + 1}
        if section.items is not None:
            answers: list[tuple[str, bool]] = []
            groups = state.sets.get(section.id) or [[i] for i in state.item_ids[section.id]]
            total = sum(len(g) for g in groups)
            for group in groups:
                items = [bank.get(i) for i in group]
                audio = f"tts:{items[0].id}" if section.skill is Skill.LISTENING else None
                reply = interrupt(
                    {
                        "kind": "set",
                        "section": section.id,
                        "minutes": section.max_minutes,
                        "progress": {"done": len(answers), "total": total},
                        "set": serve_set(items, seed, audio_ref=audio).model_dump(),
                    }
                )
                late = float(reply.get("elapsed_s", 0)) > limit_s
                given = reply.get("answers") or []
                for n, item in enumerate(items):
                    value = given[n] if n < len(given) else None
                    answers.append((item.id, not late and check(item, seed, value)))
            update["answers"] = {**state.answers, section.id: answers}
        elif section.tasks:
            assert state.tasks is not None
            texts = dict(state.writing)
            for task in section.tasks:
                task_prompt = next((t.prompt for t in state.tasks.writing if t.task_id == task.id), task.id)
                reply = interrupt(
                    {
                        "kind": "writing",
                        "section": section.id,
                        "task": task.id,
                        "prompt": task_prompt,
                        "min_words": task.min_words,
                        "minutes": section.max_minutes,
                    }
                )
                texts[task.id] = "" if float(reply.get("elapsed_s", 0)) > limit_s else str(reply.get("text", ""))
            update["writing"] = texts
        else:
            assert state.tasks is not None
            spoken = dict(state.speaking)
            for part in section.part_list():
                speaking_task = next((p for p in state.tasks.speaking if p.part_id == part.id), None)
                request: dict[str, Any] = {
                    "kind": "speaking",
                    "section": section.id,
                    "part": part.id,
                    "prompt": speaking_task.prompt if speaking_task else part.id,
                    "minutes": part.minutes,
                }
                if speaking_task and speaking_task.facts and state.tasks.examiner and state.attempt:
                    request["scene_id"] = str(await examiner_scene(state, pack, part, speaking_task))
                reply = interrupt(request)
                if reply.get("scene_id") and reply.get("scene_id") == request.get("scene_id"):
                    spoken[part.id] = await examiner_transcript(uuid.UUID(str(reply["scene_id"])))
                else:
                    spoken[part.id] = str(reply.get("transcript", ""))
            update["speaking"] = spoken
        return update

    async def examiner_scene(state: ExamState, pack: ExamPack, part: PartDef, task: MockTasks.Speaking) -> uuid.UUID:
        """A live scene in which the examiner runs this speaking part. Ids come from the attempt, so the graph
        resuming (which re-runs this node) finds the same session and scene instead of creating new ones."""
        assert state.attempt is not None and state.tasks is not None and state.tasks.examiner is not None
        city_key = LANGUAGE_CITY[pack.language]
        city = load_city(deps.content_root, city_key)
        examiner = city.npc(state.tasks.examiner["npc_key"])
        session_id = uuid.uuid5(state.attempt, "speaking")
        scene_id = uuid.uuid5(state.attempt, part.id)
        profile = await deps.store.profile(state.user_id)
        band = profile.language_bands.get(pack.language, 5)
        minutes = max(part.minutes) if isinstance(part.minutes, list) else (part.minutes or 5)
        targets = {kind: [t for t in task.targets if f".{abbr}." in t] for kind, abbr in TARGET_KINDS.items()}
        contract = SceneContract(
            scene_id=scene_id,
            city=city_key,
            location_key=state.tasks.examiner["location_key"],
            cast=[CastMember(npc_key=examiner.key, role=examiner.role, voice_id=examiner.voice_id)],
            learner_goal=task.prompt,
            targets=SceneTargets(**targets),
            elicitation=[ElicitationTactic(target=t, tactic=" ".join(task.tactics)) for t in task.targets],
            approved_facts=task.facts,
            npc_language_band=npc_band_for(band),
            accent_variety=[examiner.accent],
            success_conditions=[Condition(description="The candidate completes this part of the speaking test")],
            max_turns=max(4, min(80, minutes * 5)),
            exits=[Exit(key="time_up", trigger="The time for this part is over", consequence="Thank the candidate")],
            pack_alignment=[f"{pack.id}.speaking.{part.id}"],
        )
        await deps.store.open_exam_session(session_id, state.user_id, city_key)
        await deps.store.save_scene(SceneRecord(scene_id, state.user_id, session_id, contract))
        return scene_id

    async def examiner_transcript(scene_id: uuid.UUID) -> str:
        """The spoken exchange, examiner and candidate, as the examiner panel scores it. Turns reach the store
        through the turn stream a moment after they are spoken, so a fresh scene is given a few seconds."""
        for _ in range(TRANSCRIPT_WAIT_TRIES):
            turns = await deps.store.turns(scene_id)
            if any(t.speaker == "learner" for t in turns):
                break
            await asyncio.sleep(TRANSCRIPT_WAIT_S)
        return "\n".join(f"{'Candidate' if t.speaker == 'learner' else 'Examiner'}: {t.transcript}" for t in turns)

    def next_after_section(state: ExamState) -> str:
        return "run_section" if state.section_index < len(deps.packs.pack(state.pack).sections) else "score_section"

    async def score_section(state: ExamState) -> dict[str, Any]:
        pack = deps.packs.pack(state.pack)
        conversion = deps.packs.conversion(state.pack)
        scores: dict[str, float] = {}
        for section in pack.ordered_sections():
            if section.items is not None:
                responses = [(bank.get(i).difficulty, ok) for i, ok in state.answers.get(section.id, [])]
                level = estimate(responses).band
                scores[section.skill.value] = _to_pack_score(pack, conversion, section.skill, level)
            elif section.tasks:
                task_scores = []
                weights = []
                for task in section.tasks:
                    prompt = next(
                        (t.prompt for t in (state.tasks.writing if state.tasks else []) if t.task_id == task.id),
                        task.id,
                    )
                    result = await examiner.score(
                        pack=pack,
                        conversion=conversion,
                        task=task,
                        task_prompt=prompt,
                        response=state.writing.get(task.id, ""),
                        nodes={},
                        trace_id=state.trace_id,
                    )
                    await deps.store.save_writing(state.user_id, prompt, state.writing.get(task.id, ""), result)
                    task_scores.append(result.band_or_points)
                    weights.append(task.weight)
                weighted = sum(s * w for s, w in zip(task_scores, weights, strict=True)) / sum(weights)
                scores["writing"] = round(weighted * 2) / 2 if pack.scale.type == "band" else round(weighted)
            else:
                scores["speaking"] = await _score_speaking(pack, conversion, section.rubric, state)
        return {"scores": scores}

    async def _score_speaking(pack: ExamPack, conversion: Any, rubric_keys: list[str], state: ExamState) -> float:
        rubrics = yaml.safe_load((deps.content_root / "packs" / pack.id / "rubrics.yaml").read_text())["speaking"]
        parts = "\n".join(f"[{k}] {v}" for k, v in state.speaking.items())
        text = speaking_prompt.render(
            exam=EXAMS[pack.id],
            scale=pack.scale_description,
            rubric=rubric_text(rubrics, rubric_keys),
            parts=parts or "(no response)",
            pronunciation_note="transcript only; the pronunciation engine adjusts this later",
        )
        samples = await asyncio.gather(
            *(
                deps.router.structured(
                    "frontier", speaking_prompt, _SpeakingScores, [HumanMessage(content=text)], trace_id=state.trace_id
                )
                for _ in range(SAMPLES)
            )
        )
        per_dimension = [
            statistics.median(d.score for s in samples for d in s.dimensions if d.dimension == key)
            for key in rubric_keys
            if any(d.dimension == key for s in samples for d in s.dimensions)
        ]
        mean = statistics.fmean(per_dimension) if per_dimension else 0.0
        if pack.scale.type == "band":
            return round(mean * 2) / 2
        return float(conversion.mid_score_for(Skill.SPEAKING, round(mean), pack.max_score(Skill.SPEAKING)))

    async def aggregate(state: ExamState) -> dict[str, Any]:
        pack = deps.packs.pack(state.pack)
        overall = ielts_overall([state.scores[s.value] for s in Skill]) if pack.scale.type == "band" else None
        return {"overall": overall}

    async def convert_to_clb_nclc(state: ExamState) -> dict[str, Any]:
        conversion = deps.packs.conversion(state.pack)
        return {"levels": {skill: conversion.to_level(Skill(skill), score) for skill, score in state.scores.items()}}

    async def persist(state: ExamState) -> dict[str, Any]:
        pack = deps.packs.pack(state.pack)
        record = {
            "pack": state.pack,
            "sections": [s.id for s in pack.ordered_sections()],
            "raw_scores": {k: sum(ok for _, ok in v) for k, v in state.answers.items()},
            "band_or_score": {**state.scores, **({"overall": state.overall} if state.overall is not None else {})},
            "clb_nclc": state.levels,
        }
        mock_id = await deps.store.save_mock(state.user_id, record)
        posteriors = await deps.store.posteriors(state.user_id)
        for skill_name, score in state.scores.items():
            skill = Skill(skill_name)
            posterior = posteriors.get((state.pack, skill_name)) or prior(pack, skill, None, rules.bands)
            await deps.store.save_posterior(
                state.user_id, state.pack, skill_name, observe(posterior, pack, skill, score, "mock", rules.bands)
            )
        await deps.store.save_language_band(state.user_id, pack.language, min(state.levels.values() or [1]) or 1)
        await deps.store.apply_ledger(
            state.user_id,
            [LedgerEntry("coins", COINS["mock_complete"], "mock_complete", str(mock_id), f"mock:{mock_id}")],
        )
        profile = await deps.store.profile(state.user_id)
        history = []
        for mock in await deps.store.mocks(state.user_id):
            targets = profile.target_bands.get(mock["pack"], {})
            met = bool(targets) and all(mock["clb_nclc"].get(s, 0) >= t for s, t in targets.items())
            history.append({mock["pack"]: met})
        merged: list[dict[str, bool]] = []
        for entry in history:
            merged.append({**(merged[-1] if merged else {}), **entry})
        if landing_day_unlocked(merged):
            for city in CITY_LANGUAGE:  # the finale spans both packs, so both cities see it
                world = await deps.store.world_state(state.user_id, city)
                await deps.store.save_world_state(
                    state.user_id,
                    city,
                    {**world, "story_flags": {**world.get("story_flags", {}), "landing_day": "unlocked"}},
                )
        return {"mock_id": mock_id}

    graph = StateGraph(ExamState)
    for name, fn in (
        ("assemble", assemble),
        ("run_section", run_section),
        ("score_section", score_section),
        ("aggregate", aggregate),
        ("convert_to_clb_nclc", convert_to_clb_nclc),
        ("persist", persist),
    ):
        graph.add_node(name, fn)
    graph.add_edge(START, "assemble")
    graph.add_edge("assemble", "run_section")
    graph.add_conditional_edges("run_section", next_after_section, ["run_section", "score_section"])
    graph.add_edge("score_section", "aggregate")
    graph.add_edge("aggregate", "convert_to_clb_nclc")
    graph.add_edge("convert_to_clb_nclc", "persist")
    graph.add_edge("persist", END)
    return graph.compile(checkpointer=checkpointer)


def _to_pack_score(pack: ExamPack, conversion: Any, skill: Skill, level: float) -> float:
    """CLB/NCLC ability → the pack's own scale, at the middle of the level's score range."""
    whole = int(level)
    if whole < 4:
        return float(pack.min_score(skill)) if pack.scale.type == "points" else max(1.0, round(level * 2) / 2 - 0.5)
    score = conversion.mid_score_for(skill, whole, pack.max_score(skill))
    if pack.scale.type == "band":
        return float(round(score * 2) / 2)
    return float(round(score))


def fill(pool: list[list[Item]], needed: int) -> list[list[Item]]:
    """Whole sets until the part is full; the last set is cut short if nothing else fits exactly."""
    chosen: list[list[Item]] = []
    total = 0
    for group in pool:
        if total + len(group) <= needed:
            chosen.append(group)
            total += len(group)
    for group in pool:
        if total >= needed:
            break
        if group not in chosen:
            chosen.append(group[: needed - total])
            total += len(chosen[-1])
    return chosen
