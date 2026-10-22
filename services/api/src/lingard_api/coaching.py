"""Today's path for one learner: gathers what they have shown in their focus language, asks the learning coach for the
day's choices and reasons, and keeps its plan until what it was based on changes (decision 0029).

The coach answers in the background: the first look at the home screen gets the path from the curriculum's order at
once (``coach="thinking"``), and the next one the coach's (``"ai"``). Without a language model, or when it fails, the
path stays as it is (``"rules"``).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections import Counter
from datetime import UTC, datetime, time
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lingard_api.coach import Signals, Slip, Sound, Stop, plan_path
from lingard_api.routes.key_points import KeyPoint, key_points
from lingard_api.routes.studio import overview
from lingard_api.state import AppState
from lingard_contracts.assessment import ErrorTag
from lingard_contracts.common import LANGUAGE_CITY, LANGUAGE_NAME, Language
from lingard_db.models import Assessment, LearnerProfile, Scene, Session, Turn, User
from lingard_graphs.agents.learning_coach import CoachBrief, CoachPlan, RuleCandidate, SlipCandidate, SoundCandidate
from lingard_graphs.agents.learning_coach import coach as ask_coach
from lingard_llm.config import any_llm_configured

log = logging.getLogger(__name__)

Source = Literal["ai", "thinking", "rules"]

RECENT_SCENES = 3
"""Mistakes are gathered from this many of the latest scenes: one slip can be chance, the same one twice is a habit."""
RULES_OFFERED = 10
SOUNDS_OFFERED = 6
LEARNED_SHOWN = 12

ASKING: set[tuple[uuid.UUID, str]] = set()
"""Plans being worked out now, so a burst of home-screen loads asks the coach once."""


async def todays_path(
    state: AppState,
    db: AsyncSession,
    user: User,
    profile: LearnerProfile,
    language: Language,
    *,
    story_ready: bool,
    reviews_due: int,
    skills: dict[str, str],
    exam_name: str,
) -> tuple[list[Stop], Source]:
    signals = await _signals(state, db, user.id, profile, language, story_ready, reviews_due)
    if not story_ready:
        return [], "rules"
    brief = await _brief(state, db, user, profile, language, signals, skills, exam_name)
    digest = _digest(brief)
    saved = profile.settings.get("coach", {})
    if saved.get("digest") == digest and saved.get("date") == datetime.now(UTC).date().isoformat():
        return plan_path(signals, CoachPlan.model_validate(saved["plan"])), "ai"
    if not any_llm_configured() or not (brief.slips or brief.rules or brief.sounds):
        return plan_path(signals), "rules"
    if (user.id, digest) not in ASKING:
        ASKING.add((user.id, digest))
        task = asyncio.create_task(_ask(state, user.id, brief, digest))
        task.add_done_callback(lambda _: ASKING.discard((user.id, digest)))
    return plan_path(signals), "thinking"


async def _ask(state: AppState, user_id: uuid.UUID, brief: CoachBrief, digest: str) -> None:
    try:
        plan = await ask_coach(brief, router=state.graph_deps.router, prompts=state.graph_deps.prompts)
    except Exception:  # the path from the curriculum's order stands; the next look asks again
        log.warning("learning coach failed", exc_info=True)
        return
    async with state.sessions() as db:
        profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == user_id))).scalar_one()
        saved = {"date": datetime.now(UTC).date().isoformat(), "digest": digest, "plan": plan.model_dump()}
        profile.settings = {**profile.settings, "coach": saved}
        await db.commit()


def _digest(brief: CoachBrief) -> str:
    """What the plan depends on. What was done today and how many reviews wait are left out, so ticking a stop or
    answering a card doesn't send the coach back to work."""
    basis = brief.model_copy(update={"done_today": [], "reviews_due": int(brief.reviews_due > 0)})
    return hashlib.sha256(basis.model_dump_json().encode()).hexdigest()[:24]


async def _signals(
    state: AppState,
    db: AsyncSession,
    user_id: uuid.UUID,
    profile: LearnerProfile,
    language: Language,
    story_ready: bool,
    reviews_due: int,
) -> Signals:
    today = datetime.now(UTC).date()
    marked = profile.settings.get("done_today", {})
    done = set(marked.get("kinds", [])) if marked.get("date") == today.isoformat() else set()
    played = (
        select(Scene)
        .join(Session, Session.id == Scene.session_id)
        .where(
            Scene.user_id == user_id,
            Scene.status != "planned",
            Session.kind == "live",
            Session.city == LANGUAGE_CITY[language],
        )
        .order_by(Scene.updated_at.desc())
        .limit(RECENT_SCENES)
    )
    recent = list((await db.execute(played)).scalars())
    if recent and recent[0].updated_at >= datetime.combine(today, time(), UTC):
        done.add("story")
    steps = {k.node_key: k for k in await key_points(state, db, user_id, language)}
    rules = [k for k in steps.values() if k.core and k.status != "done"]
    rules.sort(key=lambda k: k.kind != "grammar")  # rules before word sets and phrases, each in curriculum order
    gym = await overview(state, profile, language)
    by_key = {d.key: d for d in gym.drills}
    started = [d.key for d in gym.drills if d.score is not None and not d.mastered and d.key not in gym.workout]
    sounds = [
        Sound(drill=d.key, title=d.title, example=d.examples[0], score=d.score)
        for key in [*gym.workout, *started][:SOUNDS_OFFERED]
        if (d := by_key[key]).examples
    ]
    return Signals(
        story_ready=story_ready,
        reviews_due=reviews_due,
        done=frozenset(done),
        slips=await _slips(db, [s.id for s in recent], steps),
        rules=tuple((k.node_key, k.title) for k in rules[:RULES_OFFERED]),
        sounds=tuple(sounds),
    )


async def _slips(db: AsyncSession, scene_ids: list[uuid.UUID], steps: dict[str, KeyPoint]) -> tuple[Slip, ...]:
    """Confirmed mistakes of the recent scenes on rules not learned yet, with the learner's own words; the ones made
    in more scenes first."""
    if not scene_ids:
        return ()
    rows = await db.execute(
        select(Turn.scene_id, Assessment.error_tags)
        .join(Turn, Assessment.turn_id == Turn.id)
        .where(Turn.scene_id.in_(scene_ids))
        .order_by(Turn.index)
    )
    first: dict[str, Slip] = {}
    scenes: Counter[str] = Counter()
    seen: set[tuple[str, uuid.UUID]] = set()
    for scene_id, batch in rows:
        for tag in map(ErrorTag.model_validate, batch):
            point = steps.get(tag.node_key)
            if not tag.showable or point is None or point.status == "done":
                continue
            first.setdefault(point.node_key, Slip(point.node_key, point.title, tag.span.text, tag.correction))
            if (point.node_key, scene_id) not in seen:
                seen.add((point.node_key, scene_id))
                scenes[point.node_key] += 1
    order = sorted(first, key=lambda k: -scenes[k])
    return tuple(Slip(first[k].node_key, first[k].title, first[k].said, first[k].better, scenes[k]) for k in order)


async def _brief(
    state: AppState,
    db: AsyncSession,
    user: User,
    profile: LearnerProfile,
    language: Language,
    s: Signals,
    skills: dict[str, str],
    exam_name: str,
) -> CoachBrief:
    steps = await key_points(state, db, user.id, language)
    learned = [k.title for k in steps if k.status == "done"][-LEARNED_SHOWN:][::-1]
    keys = [key for key, _ in s.rules]
    mastery = await state.graph_deps.store.mastery(user.id, keys)
    bands = {k.node_key: k for k in steps}
    return CoachBrief(
        language=language,
        band=int(profile.settings.get("language_bands", {}).get(language, 5)),
        exam_name=exam_name,
        explain_language=LANGUAGE_NAME[user.ui_locale or "en"],
        skills=skills,
        learned=learned,
        slips=[
            SlipCandidate(node_key=x.node_key, title=x.title, said=x.said, better=x.better, times=x.times)
            for x in s.slips
        ],
        rules=[
            RuleCandidate(
                node_key=key,
                title=title,
                kind=bands[key].kind,
                band=bands[key].band,
                in_use=round(mastery[key].p_mastery, 2) if key in mastery else 0.0,
            )
            for key, title in s.rules
        ],
        sounds=[SoundCandidate(drill=x.drill, title=x.title, score=x.score) for x in s.sounds],
        done_today=sorted(s.done),
        reviews_due=s.reviews_due,
    )
