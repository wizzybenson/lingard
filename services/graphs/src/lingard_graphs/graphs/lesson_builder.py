"""``lesson_builder`` graph (SPEC §11, §16): node + the learner's own errors → explanation, games, homework scene."""

from __future__ import annotations

import random
import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict

from lingard_contracts.common import LANGUAGE_NAME, CityKey
from lingard_contracts.planning import Game, GameItem, Lesson, LessonExample, SceneBrief
from lingard_curriculum.conjugation import FrenchConjugator
from lingard_curriculum.models import CurriculumNode
from lingard_graphs.deps import GraphDeps
from lingard_graphs.graphs._build import linear
from lingard_llm import StructuredOutputError
from lingard_world import CityContent, load_city

TENSE_HINTS = {
    "imparfait": ["imparfait"],
    "passe_compose": ["passe_compose"],
    "futur": ["futur_simple"],
    "conditionnel_present": ["conditionnel_present"],
    "si_imparfait": ["imparfait", "conditionnel_present"],
    "plus_que_parfait": ["plus_que_parfait"],
    "conditionnel_passe": ["conditionnel_passe"],
    "subjonctif": ["subjonctif_present"],
    "present": ["present"],
}
PERSONS = ("je", "tu", "il/elle", "nous", "vous", "ils/elles")


class TeacherDraft(BaseModel):
    title: str
    rule: str
    examples: list[LessonExample]


class LessonState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: uuid.UUID
    node_key: str
    city: CityKey
    trace_id: str | None = None
    node: CurriculumNode | None = None
    mistakes: list[tuple[str, str]] = []
    """(learner_said, better) pairs from tickets and confirmed corrections."""
    draft: TeacherDraft | None = None
    games: list[Game] = []
    lesson: Lesson | None = None
    lesson_id: uuid.UUID | None = None


def conjugation_items(
    node: CurriculumNode, conjugator: FrenchConjugator, rng: random.Random, n: int = 8
) -> list[GameItem]:
    tenses = next((t for hint, t in TENSE_HINTS.items() if hint in node.key), [])
    # A lesson on regular (or irregular) verbs drills only those verbs.
    regularity = False if "irregular" in node.key else True if "regular" in node.key else None
    items = []
    for tense in tenses:
        for verb_key, verb in conjugator.verbs.items():
            if regularity is not None and verb.regular != regularity:
                continue
            forms = conjugator.conjugate(verb_key, tense)
            for person in rng.sample(range(6), 2):
                items.append(
                    GameItem(
                        prompt=f"{PERSONS[person]} — {verb.infinitive} ({conjugator.label(tense)})",
                        answer=forms[person],
                        node_key=node.key,
                    )
                )
    rng.shuffle(items)
    return items[:n]


def spot_the_error_items(node: CurriculumNode, mistakes: list[tuple[str, str]]) -> list[GameItem]:
    lesson = node.payload.get("lesson") or {}
    pairs = [*mistakes, *((e["wrong"], e["right"]) for e in lesson.get("common_errors", []))]
    return [GameItem(prompt=wrong, answer=right, distractors=[wrong], node_key=node.key) for wrong, right in pairs[:8]]


def sentence_race_items(node: CurriculumNode, examples: list[str], rng: random.Random) -> list[GameItem]:
    items = []
    for sentence in examples:
        words = sentence.split()
        if len(words) < 3:
            continue
        shuffled = words[:]
        while shuffled == words:
            rng.shuffle(shuffled)
        items.append(GameItem(prompt=" / ".join(shuffled), answer=sentence, node_key=node.key))
    return items


def build_games(
    node: CurriculumNode, mistakes: list[tuple[str, str]], conjugator: FrenchConjugator | None, rng: random.Random
) -> list[Game]:
    lesson = node.payload.get("lesson") or {}
    examples = list(lesson.get("examples", [])) + [better for _, better in mistakes]
    examples += [str(x) for x in node.payload.get("exponents", []) + node.payload.get("items", [])]
    games: list[Game] = []
    if conjugator is not None and node.language == "fr":
        duel = conjugation_items(node, conjugator, rng)
        if duel:
            games.append(Game(kind="conjugation_duel", items=duel, time_limit_s=60))
    spot = spot_the_error_items(node, mistakes)
    if spot:
        games.append(Game(kind="spot_the_error", items=spot))
    race = sentence_race_items(node, examples, rng)
    if race:
        games.append(Game(kind="sentence_race", items=race, time_limit_s=90))
    if examples:
        games.append(
            Game(kind="dictation", items=[GameItem(prompt=e, answer=e, node_key=node.key) for e in examples[:4]])
        )
    exponents = node.payload.get("exponents") or []
    if node.kind == "function" and len(exponents) >= 2:
        games.append(
            Game(kind="register_switch", items=[GameItem(prompt=exponents[0], answer=exponents[-1], node_key=node.key)])
        )
    return games


def homework_scene(city: CityContent, node_key: str, band: int, failed: set[str], ticket: bool) -> SceneBrief:
    """The same-day scene that puts a lesson to use: someone the learner can meet, not where the rule last failed."""
    options = [
        (loc.key, h.npc_key)
        for d in city.city.districts
        if d.key in city.unlocked_districts(band)
        for loc in d.locations
        for h in loc.hotspots
        if h.kind == "npc" and h.npc_key
    ]
    location, npc = next(((loc, n) for loc, n in options if loc not in failed), options[0])
    return SceneBrief(
        city=city.city.key,
        location_key=location,
        npc_keys=[npc or ""],
        story_beat=f"After class, the learner runs into {city.npc(npc or '').name}.",
        targets=[node_key],
        ticket_targets=[node_key] if ticket else [],
        learner_band=band,
    )


def key_points_lesson(
    node: CurriculumNode, city: CityContent, band: int, conjugator: FrenchConjugator | None, rng: random.Random
) -> Lesson:
    """A lesson taught before the learner needs the rule, straight from the node's authored key points.
    No model call: it opens at once and costs nothing, and every word was reviewed with the curriculum."""
    content = node.payload.get("lesson") or {}
    errors = content.get("common_errors", [])
    return Lesson(
        node_key=node.key,
        kind="key_points",
        title=node.title,
        rule=content.get("rule") or node.title,
        models=list(content.get("examples", [])),
        examples=[LessonExample(learner_said=e["wrong"], better=e["right"]) for e in errors],
        games=build_games(node, [], conjugator, rng),
        homework=homework_scene(city, node.key, band, set(), False),
        minutes=5,
    )


def build_lesson_builder(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver[str] | None = None
) -> CompiledStateGraph[LessonState, Any, LessonState, LessonState]:
    prompt = deps.prompts.get("teacher_lesson")
    conjugator = FrenchConjugator.load(deps.content_root / "curriculum" / "fr" / "conjugation.yaml")

    async def pick_examples_from_errors(state: LessonState) -> dict[str, Any]:
        node = await deps.curriculum.get(state.node_key)
        if node is None or not node.reviewed:
            raise ValueError(f"{state.node_key} is not a reviewed node")
        ticket = (await deps.store.tickets(state.user_id, active_only=False)).get(state.node_key)
        mistakes: list[tuple[str, str]] = []
        lesson = node.payload.get("lesson") or {}
        fixes = {e["wrong"].casefold(): e["right"] for e in lesson.get("common_errors", [])}
        for example in (ticket.examples if ticket else [])[-5:]:
            if example.text:
                mistakes.append((example.text, fixes.get(example.text.casefold(), "")))
        return {"node": node, "mistakes": mistakes}

    async def build_explanation(state: LessonState) -> dict[str, Any]:
        assert state.node is not None
        node = state.node
        lesson = node.payload.get("lesson") or {}
        rule = lesson.get("rule") or node.title
        profile = await deps.store.profile(state.user_id)
        ui = LANGUAGE_NAME.get(profile.l1, "English")
        text = prompt.render(
            school_name=load_city(deps.content_root, state.city).city.school,
            node_title=node.title,
            language_name=LANGUAGE_NAME[node.language],
            rule=rule,
            mistakes="; ".join(f'"{m}"' for m, _ in state.mistakes) or "none recorded yet",
            ui_language=ui,
        )
        try:
            draft = await deps.router.structured(
                "mid", prompt, TeacherDraft, [HumanMessage(content=text)], trace_id=state.trace_id
            )
        except StructuredOutputError:
            draft = TeacherDraft(title=node.title, rule=rule, examples=[])
        real = {m.casefold() for m, _ in state.mistakes}
        examples = [e for e in draft.examples if e.learner_said.casefold() in real]  # only the learner's real mistakes
        if not examples:
            examples = [LessonExample(learner_said=m, better=b or m) for m, b in state.mistakes] or [
                LessonExample(learner_said=e["wrong"], better=e["right"]) for e in lesson.get("common_errors", [])[:2]
            ]
        return {"draft": draft.model_copy(update={"examples": examples, "rule": draft.rule or rule})}

    async def build_games_node(state: LessonState) -> dict[str, Any]:
        assert state.node is not None
        rng = random.Random(f"{state.user_id}:{state.node_key}")  # noqa: S311
        mistakes = [(m, b) for m, b in state.mistakes if b]
        return {"games": build_games(state.node, mistakes, conjugator, rng)}

    async def build_homework_scene(state: LessonState) -> dict[str, Any]:
        assert state.node is not None and state.draft is not None
        profile = await deps.store.profile(state.user_id)
        band = profile.language_bands.get(state.node.language, 5)
        ticket = (await deps.store.tickets(state.user_id, active_only=False)).get(state.node_key)
        failed = {e.context.split(":")[0] for e in ticket.examples} if ticket else set()
        homework = homework_scene(load_city(deps.content_root, state.city), state.node_key, band, failed, bool(ticket))
        lesson = Lesson(
            node_key=state.node_key,
            title=state.draft.title,
            rule=state.draft.rule,
            models=list((state.node.payload.get("lesson") or {}).get("examples", [])),
            examples=state.draft.examples,
            games=state.games,
            homework=homework,
        )
        lesson_id = await deps.store.save_lesson(state.user_id, state.node_key, lesson.model_dump(mode="json"))
        return {"lesson": lesson, "lesson_id": lesson_id}

    graph = StateGraph(LessonState)
    steps = [
        ("pick_examples_from_errors", pick_examples_from_errors),
        ("build_explanation", build_explanation),
        ("build_games", build_games_node),
        ("build_homework_scene", build_homework_scene),
    ]
    linear(graph, steps)
    return graph.compile(checkpointer=checkpointer)
