"""``/v1/key-points``: the rules a learner is taught before a scene asks for them (SPEC §16).

Each step is one grammar node, built into a lesson from its authored key points with no model call, so it opens at
once. Finishing it goes through the usual ``/v1/lessons/{id}/complete``.
"""

from __future__ import annotations

import random
import uuid
from functools import cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lingard_api.deps import Db, Principal, State
from lingard_api.state import AppState
from lingard_contracts.common import LANGUAGE_CITY, Language, node_language
from lingard_contracts.planning import LessonExample, TeachStep
from lingard_curriculum.conjugation import Conjugator, load_conjugator
from lingard_curriculum.models import CurriculumNode
from lingard_db.models import Lesson
from lingard_graphs.graphs.lesson_builder import key_points_lesson, teach_steps
from lingard_graphs.pedagogy.key_points import FIRST_BAND, KINDS, key_points_path
from lingard_world import load_city

router = APIRouter(prefix="/v1/key-points", tags=["key-points"])


class KeyPoint(BaseModel):
    node_key: str
    kind: Literal["grammar", "lexset", "function"]
    """A rule, a set of words, or a way of saying something."""
    title: str
    band: int
    core: bool
    """At the learner's level: what the journey offers now."""
    preview: bool
    status: Literal["new", "open", "done"]
    learned_in_use: bool = False
    """Done because the learner has been using it well in the city (evidenced mastery), lesson or not."""
    lesson_id: uuid.UUID | None
    places: list[str] = []
    """Kinds of place where this is useful (a bank, a clinic): the journey offers it there."""


PLACE_OFFER = 3
"""How many lessons a place offers at once: a nudge, not a syllabus."""


@cache
def _conjugator(content_root: Path, language: Language) -> Conjugator | None:
    """The language's conjugation-duel engine; it drills only the grammar points its content names."""
    return load_conjugator(content_root / "curriculum" / language / "conjugation.yaml")


async def key_points(
    state: AppState, db: AsyncSession, user_id: uuid.UUID, language: Language, *, every_level: bool = False
) -> list[KeyPoint]:
    profile = await state.graph_deps.store.profile(user_id)
    steps = await key_points_path(
        state.curriculum,
        state.settings.content_root,
        language,
        profile.language_bands.get(language),
        every_level=every_level,
    )
    return await describe(state, db, user_id, [(s.node, s.core, s.preview) for s in steps])


async def describe(
    state: AppState, db: AsyncSession, user_id: uuid.UUID, nodes: list[tuple[CurriculumNode, bool, bool]]
) -> list[KeyPoint]:
    """Key points for ``(node, core, preview)``, with the learner's lesson for each and whether it is done: its lesson
    finished, or the rule shown in use often and well enough to count as mastered (SPEC §14), lesson or not."""
    rows = (
        await db.execute(
            select(Lesson)
            .where(Lesson.user_id == user_id, Lesson.node_key.in_([n.key for n, _, _ in nodes]))
            .order_by(Lesson.created_at)
        )
    ).scalars()
    latest: dict[str, Lesson] = {}
    done: set[str] = set()
    for row in rows:
        latest[row.node_key] = row
        if row.status == "done":
            done.add(row.node_key)
    mastery = await state.graph_deps.store.mastery(user_id, [n.key for n, _, _ in nodes])
    mastered = state.graph_deps.pedagogy.bkt.mastered
    in_use = {key for key, m in mastery.items() if m.p_mastery >= mastered}
    out = []
    for node, core, preview in nodes:
        lesson = latest.get(node.key)
        out.append(
            KeyPoint(
                node_key=node.key,
                kind=node.kind,
                title=node.title,
                band=node.band,
                core=core,
                preview=preview,
                status="done" if node.key in done | in_use else "open" if lesson else "new",
                learned_in_use=node.key in in_use and node.key not in done,
                lesson_id=lesson.id if lesson else None,
                places=[str(p) for p in node.payload.get("places", [])],
            )
        )
    return out


@router.get("", response_model=list[KeyPoint])
async def path(
    language: Language, principal: Principal, state: State, db: Db, every_level: bool = False
) -> list[KeyPoint]:
    """The path to the learner's level and one level beyond; with ``every_level``, the whole library."""
    return await key_points(state, db, principal.user_id, language, every_level=every_level)


@router.get("/for-place", response_model=list[KeyPoint])
async def for_place(language: Language, place: str, principal: Principal, state: State, db: Db) -> list[KeyPoint]:
    """The words and phrases useful at this kind of place, at the learner's level or below, not yet learned first."""
    useful = [k for k in await key_points(state, db, principal.user_id, language) if place in k.places]
    useful.sort(key=lambda k: (k.status == "done", k.preview, not k.core))
    return useful[:PLACE_OFFER]


class RuleCard(BaseModel):
    """A rule taught where it's needed (a mission brief) without opening a lesson: the authored teaching, examples
    and the mistakes to avoid, straight from the curriculum."""

    node_key: str
    title: str
    rule: str
    teach: list[TeachStep]
    models: list[str]
    watch_out: list[LessonExample]


@router.get("/{node_key}/card", response_model=RuleCard)
async def rule_card(node_key: str, _: Principal, state: State) -> RuleCard:
    node = await state.curriculum.get(node_key)
    if node is None or not node.reviewed or node.kind not in KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such key point")
    content = node.payload.get("lesson") or {}
    return RuleCard(
        node_key=node.key,
        title=node.title,
        rule=content.get("rule") or node.title,
        teach=teach_steps(node),
        models=list(content.get("examples", [])),
        watch_out=[LessonExample(learner_said=e["wrong"], better=e["right"]) for e in content.get("common_errors", [])],
    )


@router.post("/{node_key}", status_code=201)
async def open_key_points(node_key: str, principal: Principal, state: State, db: Db) -> dict[str, uuid.UUID]:
    """The lesson for this node: the learner's existing one, or a new one built from its key points."""
    existing = (
        await db.execute(
            select(Lesson)
            .where(Lesson.user_id == principal.user_id, Lesson.node_key == node_key)
            .order_by(Lesson.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"id": existing.id}
    node = await state.curriculum.get(node_key)
    if node is None or not node.reviewed or node.kind not in KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such key point")
    language = node_language(node_key)
    profile = await state.graph_deps.store.profile(principal.user_id)
    band = profile.language_bands.get(language) or FIRST_BAND
    lesson = key_points_lesson(
        node,
        load_city(state.settings.content_root, LANGUAGE_CITY[language]),
        band,
        _conjugator(state.settings.content_root, language),
        random.Random(f"{principal.user_id}:{node_key}"),  # noqa: S311
    )
    lesson_id = await state.graph_deps.store.save_lesson(principal.user_id, node_key, lesson.model_dump(mode="json"))
    return {"id": lesson_id}
