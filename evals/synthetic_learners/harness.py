"""Run synthetic learners through simulated days on the real graphs, with an oracle assessor (offline mode)."""

from __future__ import annotations

import json
import random
import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph

from evals.framework import ROOT
from evals.synthetic_learners.learner import SyntheticLearner
from lingard_contracts.common import CITY_LOCALE, LANGUAGE_CITY
from lingard_contracts.events import TurnEvent
from lingard_curriculum.graph import InMemoryCurriculumGraph
from lingard_curriculum.packs import PackLibrary
from lingard_curriculum.seed import load_seed, seed_graph
from lingard_graphs.deps import GraphDeps, MemoryHints
from lingard_graphs.graphs.day_planner import build_day_planner
from lingard_graphs.graphs.lesson_builder import build_lesson_builder
from lingard_graphs.graphs.night_consolidation import build_night_consolidation
from lingard_graphs.graphs.turn_assessment import build_turn_assessment
from lingard_graphs.pedagogy.config import load_pedagogy
from lingard_graphs.store import LearnerProfileView, MemoryStore
from lingard_llm import LLMConfig, LLMRouter, ModelSpec, PromptRegistry
from lingard_llm.testing import ScriptedChatModel, message_text

MARKER = re.compile(r"⟦([a-z]{2}\.[a-z_.0-9]+):(ok|err)⟧")
TURNS_PER_SCENE = 6
STALE_DAYS = 7


def oracle(messages: list[BaseMessage]) -> str:
    """Scripted LLM for every prompt the graphs use; the assessor reads the learner's markers."""
    system = message_text(messages[0])
    if "silent, rigorous examiner" in system:
        whole = "\n".join(message_text(m) for m in messages)  # the turn itself follows the cached prefix
        transcript = re.search(r'Learner turn \(speech transcript, punctuation may be missing\): "(.*)"', whole)
        text = transcript.group(1) if transcript else ""
        evidence, errors = [], []
        for match in MARKER.finditer(text):
            node, verdict = match.group(1), match.group(2)
            evidence.append({"node_key": node, "correct": verdict == "ok", "span": match.group(0), "confidence": 0.9})
            if verdict == "err":
                errors.append(
                    {
                        "node_key": node,
                        "span": match.group(0),
                        "correction": "…",
                        "confidence": 0.9,
                        "severity": "major",
                    }
                )
        return json.dumps(
            {"dimensions": [], "errors": errors, "target_evidence": evidence, "confidence": 0.8, "band_estimate": 6}
        )
    if "Independent check" in system:
        return json.dumps({"is_error": True, "confidence": 0.95})
    if "director of an ongoing life story" in system:
        count = int(re.search(r"Today there are (\d+) scenes", system).group(1))  # type: ignore[union-attr]
        return json.dumps({"beats": [f"Beat {i}." for i in range(count)]})
    if "You design one scene" in system:
        targets = [line.split()[1] for line in system.splitlines() if re.match(r"- (fr|en)\.", line)]
        return json.dumps(
            {
                "learner_goal": "Sort something out",
                "elicitation": [
                    {"target": t, "tactic": f"Make {t} natural to use"} for t in targets if ".pron." not in t
                ],
                "approved_facts": ["It is a weekday"],
                "success_conditions": ["done"],
                "evidence_required": [],
                "exits": [{"key": "end", "trigger": "done", "consequence": "next"}],
                "max_turns": 12,
                "mood": "neutral",
            }
        )
    if "night notebook" in system:
        return json.dumps({"items": [], "encouragement": "Well done."})
    if "keep the story world consistent" in system:
        return json.dumps({"story_flags": {}, "relationships": []})
    if "You are the teacher" in system:
        return json.dumps({"title": "Lesson", "rule": "Rule.", "examples": []})
    raise AssertionError(f"oracle has no answer for: {system[:80]}")


@dataclass
class LearnerOutcome:
    name: str
    planted: list[str]
    detected_day: dict[str, int | None] = field(default_factory=dict)
    closed_day: dict[str, int | None] = field(default_factory=dict)
    false_tickets: set[str] = field(default_factory=set)
    false_open_at_end: set[str] = field(default_factory=set)
    noise_opened_day: dict[str, int] = field(default_factory=dict)
    stale_noise: set[str] = field(default_factory=set)
    """Noise tickets still open ≥ STALE_DAYS after their latest (re)opening: the loop failed to close a weakness."""
    lessons: list[str] = field(default_factory=list)


async def build_deps() -> GraphDeps:
    model = ScriptedChatModel(responder=oracle)
    tiers = {
        t: {"retries": 0, "models": [{"provider": "scripted", "model": "oracle"}]} for t in ("fast", "mid", "frontier")
    }

    def factory(spec: ModelSpec) -> BaseChatModel:
        return model

    curriculum = InMemoryCurriculumGraph()
    for language in ("fr", "en"):
        await seed_graph(curriculum, load_seed(ROOT / "content", language))
    return GraphDeps(
        store=MemoryStore(),
        curriculum=curriculum,
        router=LLMRouter(LLMConfig.model_validate({"tiers": tiers}), factory=factory),
        prompts=PromptRegistry(ROOT / "prompts"),
        packs=PackLibrary(ROOT / "content"),
        pedagogy=load_pedagogy(),
        hints=MemoryHints(),
        content_root=ROOT / "content",
    )


def _ids(seed: int) -> Iterator[uuid.UUID]:
    """Seeded ids, so a run is reproducible (ids order scenes and seed per-scene choices)."""
    rng = random.Random(seed)  # noqa: S311
    while True:
        yield uuid.UUID(int=rng.getrandbits(128), version=4)


def _frozen(moment: datetime) -> Callable[[], datetime]:
    return lambda: moment


async def live_days(learner: SyntheticLearner, days: int, deps: GraphDeps, replicate: int = 0) -> LearnerOutcome:
    """``replicate`` varies only the FSRS interval fuzz, so robustness to scheduling luck can be measured."""
    ids = _ids(learner.seed)
    random.seed(learner.seed + 7919 * replicate)  # FSRS interval fuzzing draws from the global generator
    store = deps.store
    assert isinstance(store, MemoryStore)
    learner.node_bands = {n.key: n.band for n in await deps.curriculum.nodes(learner.language)}  # type: ignore[arg-type]
    user_id = next(ids)
    store.profiles[user_id] = LearnerProfileView(
        user_id, learner.name, "ar", "tense", {}, {}, {learner.language: int(learner.true_band)}
    )
    graphs: tuple[CompiledStateGraph[Any, Any, Any, Any], ...] = (
        build_day_planner(deps),
        build_turn_assessment(deps),
        build_night_consolidation(deps),
        build_lesson_builder(deps),
    )
    planner, turns, night, lessons = graphs
    city = LANGUAGE_CITY[learner.language]
    outcome = LearnerOutcome(learner.name, sorted(learner.planted))
    start = datetime(2026, 11, 1, 9, tzinfo=UTC)
    for day in range(days):
        today = start + timedelta(days=day)
        deps.clock = _frozen(today)
        session_id = next(ids)
        store.days[user_id].add((start + timedelta(days=day)).date())
        plan = await planner.ainvoke({"user_id": user_id, "session_id": session_id, "city": city})
        for contract in plan["contracts"]:
            targets = [t for t in contract.targets.elicitable()]
            for k in range(TURNS_PER_SCENE):
                text, _ = learner.utterance(targets, k)
                event = TurnEvent(
                    event_id=next(ids),
                    trace_id=next(ids),
                    user_id=user_id,
                    session_id=session_id,
                    scene_id=contract.scene_id,
                    turn_index=k,
                    speaker="learner",
                    language=CITY_LOCALE[city],
                    transcript=text,
                    targets_active=contract.targets.all(),
                )
                await turns.ainvoke({"event": event})
        result = await night.ainvoke({"user_id": user_id, "session_id": session_id})
        for node_key in result["notebook"].lessons_suggested:
            if node_key not in outcome.lessons:
                await lessons.ainvoke({"user_id": user_id, "node_key": node_key, "city": city})
                learner.take_lesson(node_key)
                outcome.lessons.append(node_key)
        for key, ticket in (await store.tickets(user_id, active_only=False)).items():
            if key in learner.planted:
                if outcome.detected_day.get(key) is None:
                    outcome.detected_day[key] = day
                if ticket.status == "closed" and outcome.closed_day.get(key) is None:
                    outcome.closed_day[key] = day
                elif ticket.status != "closed":
                    outcome.closed_day[key] = None
            elif learner.within_band(key):
                outcome.false_tickets.add(key)
                if ticket.status == "closed":
                    outcome.noise_opened_day.pop(key, None)
                else:
                    outcome.noise_opened_day.setdefault(key, day)  # (re)opened: staleness counts from here
    final = await store.tickets(user_id, active_only=True)
    outcome.false_open_at_end = {k for k in final if k not in learner.planted and learner.within_band(k)}
    outcome.stale_noise = {
        k for k in outcome.false_open_at_end if days - outcome.noise_opened_day.get(k, days) >= STALE_DAYS
    }
    for key in learner.planted:
        outcome.detected_day.setdefault(key, None)
        outcome.closed_day.setdefault(key, None)
    return outcome
