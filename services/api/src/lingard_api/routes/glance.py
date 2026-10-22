"""``/v1/glance``: 2–5 minute text-first micro-quests from a pre-built queue, cached offline (SPEC §19.3).

An answer comes back with the right option's index: Glance is practice, so a miss shows what was right."""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import UTC, datetime
from itertools import zip_longest
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from lingard_api.deps import Db, Principal, State
from lingard_api.routes.me import focus_language
from lingard_api.routes.speech import item_bank
from lingard_contracts.common import CITY_LANGUAGE, LANGUAGE_PACK, Language, Skill
from lingard_db.models import FsrsItem, LearnerProfile, Session
from lingard_exam_packs.serving import serve, served_answer
from lingard_graphs.pedagogy.review import new_card, review
from lingard_live.languages import load_language

router = APIRouter(prefix="/v1/glance", tags=["glance"])
QUEUE_SIZE = 8


class Quest(BaseModel):
    id: str
    kind: str
    language: Language
    prompt: str
    options: list[str] = []
    text: str | None = None
    node_key: str | None = None


class AnswerBody(BaseModel):
    quest_id: str
    answer: int | str
    synced_at: datetime | None = None
    """Set by the client when the answer was given offline and synced later."""


def _quest_id(user: str, payload: str) -> str:
    return hashlib.sha256(f"{user}|{payload}".encode()).hexdigest()[:16]


async def _queue(state: State, db: Db, user_id: str, language: Language) -> list[tuple[Quest, dict[str, Any]]]:
    quests: list[tuple[Quest, dict[str, Any]]] = []
    now = datetime.now(UTC)
    due = (
        (
            await db.execute(
                select(FsrsItem)
                .where(
                    FsrsItem.user_id == uuid.UUID(user_id),
                    FsrsItem.due_at <= now,
                    FsrsItem.item_key.like(f"{language}.%"),
                )
                .order_by(FsrsItem.due_at)
                .limit(QUEUE_SIZE)
            )
        )
        .scalars()
        .all()
    )
    for card in due:
        node = await state.curriculum.get(card.item_key)
        errors = ((node.payload.get("lesson") or {}).get("common_errors") if node else None) or []
        if not errors:
            continue
        example = errors[0]
        options = sorted([example["wrong"], example["right"]], key=lambda o: hashlib.sha256(o.encode()).hexdigest())
        quest = Quest(
            id=_quest_id(user_id, card.item_key),
            kind="pick_correct",
            language=language,
            prompt=load_language(state.settings.content_root, language).choose_correct_prompt,
            options=options,
            node_key=card.item_key,
        )
        quests.append((quest, {"answer": options.index(example["right"]), "node": card.item_key}))
    bank = item_bank(state.settings.content_root)
    rng = random.Random(f"{user_id}:{now.date()}")  # noqa: S311
    items = bank.select(LANGUAGE_PACK[language], Skill.READING, standalone=True)
    for item in rng.sample(items, min(len(items), QUEUE_SIZE - len(quests))):
        served = serve(item, user_id)
        quests.append(
            (
                Quest(
                    id=_quest_id(user_id, item.id),
                    kind="read",
                    language=language,
                    prompt=served.question,
                    options=served.options,
                    text=served.text,
                ),
                {"item": item.id},
            )
        )
    return quests


@router.get("", response_model=list[Quest])
async def queue(principal: Principal, state: State, db: Db, language: Language | None = None) -> list[Quest]:
    """One language's messages; by default the learner's focus language, else that of the city they last played in,
    else every language they are preparing an exam in, taken in turn."""
    if language is not None:
        return [q for q, _ in await _queue(state, db, str(principal.user_id), language)]
    last_city = (
        await db.execute(
            select(Session.city)
            .where(Session.user_id == principal.user_id, Session.kind == "live", Session.city.is_not(None))
            .order_by(Session.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == principal.user_id))).scalar_one()
    exams = set(profile.settings.get("exam_dates", {}))
    bands = profile.settings.get("language_bands", {})
    languages = list(CITY_LANGUAGE.values())
    studying = [lang for lang in languages if LANGUAGE_PACK[lang] in exams]
    studying = studying or [lang for lang in languages if bands.get(lang)] or languages[:1]
    if last_city in CITY_LANGUAGE:
        studying = [CITY_LANGUAGE[last_city]]
    if focus := focus_language(profile):
        studying = [focus]  # the language the learner chose to work on wins over where they last played
    user = str(principal.user_id)
    queues = [[q for q, _ in await _queue(state, db, user, lang)] for lang in studying]
    return [q for turn in zip_longest(*queues) for q in turn if q is not None]


@router.post("/answer")
async def answer(
    body: AnswerBody, principal: Principal, state: State, db: Db, language: Language = "fr"
) -> dict[str, Any]:
    user = str(principal.user_id)
    match = next(((q, key) for q, key in await _queue(state, db, user, language) if q.id == body.quest_id), None)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quest expired; refresh the queue")
    quest, key = match
    await state.graph_deps.store.mark_active(principal.user_id, datetime.now(UTC).date(), "review")
    if "item" in key:
        item = item_bank(state.settings.content_root).get(key["item"])
        right = served_answer(item, user)
        return {"correct": int(body.answer) == right, "answer": right}
    correct = int(body.answer) == key["answer"]
    row = (
        await db.execute(
            select(FsrsItem).where(FsrsItem.user_id == principal.user_id, FsrsItem.item_key == key["node"])
        )
    ).scalar_one()
    card = review(row.card or new_card(), correct, now=body.synced_at or datetime.now(UTC))
    await state.graph_deps.store.save_fsrs(principal.user_id, key["node"], card)
    return {"correct": correct, "answer": key["answer"], "node_key": quest.node_key}
