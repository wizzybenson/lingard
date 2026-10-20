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
from lingard_curriculum.conjugation import FrenchConjugator
from lingard_db.models import Lesson
from lingard_graphs.graphs.lesson_builder import key_points_lesson
from lingard_graphs.pedagogy.key_points import FIRST_BAND, key_points_path
from lingard_world import load_city

router = APIRouter(prefix="/v1/key-points", tags=["key-points"])


class KeyPoint(BaseModel):
    node_key: str
    title: str
    band: int
    core: bool
    """At the learner's level: taught before the next story day."""
    preview: bool
    status: Literal["new", "open", "done"]
    lesson_id: uuid.UUID | None


@cache
def _conjugator(content_root: Path) -> FrenchConjugator | None:
    """The conjugation-duel engine (French data); the lesson builder only asks it about nodes it conjugates."""
    path = content_root / "curriculum" / "fr" / "conjugation.yaml"
    return FrenchConjugator.load(path) if path.exists() else None


async def key_points(state: AppState, db: AsyncSession, user_id: uuid.UUID, language: Language) -> list[KeyPoint]:
    profile = await state.graph_deps.store.profile(user_id)
    steps = await key_points_path(
        state.curriculum, state.settings.content_root, language, profile.language_bands.get(language)
    )
    rows = (
        await db.execute(
            select(Lesson)
            .where(Lesson.user_id == user_id, Lesson.node_key.in_([s.node.key for s in steps]))
            .order_by(Lesson.created_at)
        )
    ).scalars()
    latest: dict[str, Lesson] = {}
    done: set[str] = set()
    for row in rows:
        latest[row.node_key] = row
        if row.status == "done":
            done.add(row.node_key)
    out = []
    for step in steps:
        lesson = latest.get(step.node.key)
        out.append(
            KeyPoint(
                node_key=step.node.key,
                title=step.node.title,
                band=step.node.band,
                core=step.core,
                preview=step.preview,
                status="done" if step.node.key in done else "open" if lesson else "new",
                lesson_id=lesson.id if lesson else None,
            )
        )
    return out


@router.get("", response_model=list[KeyPoint])
async def path(language: Language, principal: Principal, state: State, db: Db) -> list[KeyPoint]:
    return await key_points(state, db, principal.user_id, language)


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
    if node is None or not node.reviewed or node.kind != "grammar":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such key point")
    language = node_language(node_key)
    profile = await state.graph_deps.store.profile(principal.user_id)
    band = profile.language_bands.get(language) or FIRST_BAND
    lesson = key_points_lesson(
        node,
        load_city(state.settings.content_root, LANGUAGE_CITY[language]),
        band,
        _conjugator(state.settings.content_root),
        random.Random(f"{principal.user_id}:{node_key}"),  # noqa: S311
    )
    lesson_id = await state.graph_deps.store.save_lesson(principal.user_id, node_key, lesson.model_dump(mode="json"))
    return {"id": lesson_id}
