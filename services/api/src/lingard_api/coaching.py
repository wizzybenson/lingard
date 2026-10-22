"""Today's path for one learner: gathers what they have shown in their focus language, asks the learning coach for the
day's choices, reasons and the week's focus, and keeps its plan until what it was based on changes (decision 0029).

The coach has a memory: a journal of what it suggested each day (``settings.coach_journal``), read back with what
came of it (followed or not, the mistake gone or back, the sound since), and the learner's mistakes over the last
weeks, relapses included (made again after the rule was learned).

The coach answers in the background: the first look at the home screen gets the path from the curriculum's order at
once (``coach="thinking"``), and the next one the coach's (``"ai"``). Without a language model, or when it fails or
is too slow, the path stays as it is (``"rules"``).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from time import monotonic as time_now
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lingard_api.coach import Signals, Slip, Sound, Stop, plan_path
from lingard_api.routes.key_points import KeyPoint, key_points
from lingard_api.routes.studio import GymView, overview
from lingard_api.state import AppState
from lingard_contracts.assessment import ErrorTag
from lingard_contracts.common import LANGUAGE_CITY, LANGUAGE_NAME, Language
from lingard_db.models import Assessment, LearnerProfile, Lesson, Scene, Session, Turn, User
from lingard_graphs.agents.learning_coach import CoachBrief, CoachPlan, RuleCandidate, SlipCandidate, SoundCandidate
from lingard_graphs.agents.learning_coach import coach as ask_coach
from lingard_llm.config import any_llm_configured
from lingard_world import load_city

log = logging.getLogger(__name__)

Source = Literal["ai", "thinking", "rules"]

MISTAKE_DAYS = 30
MISTAKE_SCENES = 12
"""Mistakes are gathered from the latest scenes of the last weeks: one slip can be chance, the same one in several
scenes is a habit, and one made again after its lesson is a lesson that didn't hold."""
SLIPS_OFFERED = 6
RULES_OFFERED = 10
SOUNDS_OFFERED = 6
LEARNED_SHOWN = 12
JOURNAL_DAYS = 14
"""Days the coach's journal keeps; the brief reads back the last week of them."""
HISTORY_SHOWN = 7
COACH_TIMEOUT_S = 60.0
"""A plan that hasn't come in this long is given up on (and not asked for again for a while)."""

ASKING: set[tuple[uuid.UUID, str]] = set()
"""Plans being worked out now, so a burst of home-screen loads asks the coach once."""
FAILED: dict[tuple[uuid.UUID, str], float] = {}
"""When the coach last failed on a plan: it isn't asked again for that plan for a while (a provider outage must not
turn every look at the home screen into another paid call)."""
RETRY_AFTER_S = 600


@dataclass(frozen=True)
class CoachView:
    stops: list[Stop]
    source: Source
    focus: str | None = None
    """The coach's word on the coming days, once it has planned."""


@dataclass
class Picture:
    """Everything known about the learner in one language, gathered once per look at the home screen."""

    today: date
    signals: Signals
    steps: list[KeyPoint]
    gym: GymView
    mistakes: dict[str, Slip] = field(default_factory=dict)
    """Every recent confirmed mistake by rule, learned rules included, with when it was last made."""
    last_made: dict[str, date] = field(default_factory=dict)
    played_days: set[date] = field(default_factory=set)


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
    streak: int = 0,
) -> CoachView:
    if not story_ready:
        return CoachView([], "rules")
    picture = await _gather(state, db, user.id, profile, language, reviews_due)
    brief = await _brief(state, db, user, profile, language, picture, skills, exam_name, streak)
    prompt = state.graph_deps.prompts.get("learning_coach")
    digest = _digest(brief, f"{prompt.ref}|{prompt.template}")
    saved = profile.settings.get("coach", {})
    if saved.get("digest") == digest and saved.get("date") == picture.today.isoformat():
        plan = CoachPlan.model_validate(saved["plan"])
        return CoachView(plan_path(picture.signals, plan), "ai", plan.focus)
    failed = FAILED.get((user.id, digest))
    recently_failed = failed is not None and time_now() - failed < RETRY_AFTER_S
    if not any_llm_configured() or recently_failed or not (brief.slips or brief.rules or brief.sounds):
        return CoachView(plan_path(picture.signals), "rules")
    if (user.id, digest) not in ASKING:
        ASKING.add((user.id, digest))
        task = asyncio.create_task(_ask(state, user.id, language, brief, digest))
        task.add_done_callback(lambda _: ASKING.discard((user.id, digest)))
    return CoachView(plan_path(picture.signals), "thinking")


async def _ask(state: AppState, user_id: uuid.UUID, language: Language, brief: CoachBrief, digest: str) -> None:
    try:
        plan = await asyncio.wait_for(
            ask_coach(brief, router=state.graph_deps.router, prompts=state.graph_deps.prompts), COACH_TIMEOUT_S
        )
        async with state.sessions() as db:
            # Locked while written: a review ticked at the same moment must not be overwritten by this older copy.
            mine = select(LearnerProfile).where(LearnerProfile.user_id == user_id).with_for_update()
            profile = (await db.execute(mine)).scalar_one()
            day = datetime.now(UTC).date().isoformat()
            saved = {"date": day, "digest": digest, "plan": plan.model_dump()}
            journal = remember(profile.settings.get("coach_journal", {}), language, day, plan, brief)
            profile.settings = {**profile.settings, "coach": saved, "coach_journal": journal}
            await db.commit()
    except Exception:  # the path from the curriculum's order stands; asked again after a while
        log.warning("learning coach failed", exc_info=True)
        now = time_now()
        for stale in [k for k, at in FAILED.items() if now - at >= RETRY_AFTER_S]:
            del FAILED[stale]
        FAILED[(user_id, digest)] = now


def remember(journal: dict[str, Any], language: str, day: str, plan: CoachPlan, brief: CoachBrief) -> dict[str, Any]:
    """The journal with today's plan written in (a later plan the same day replaces the earlier one), as the coach
    will read it back: what it chose, under which titles, and the sound's score at the time."""
    titles = {s.node_key: s.title for s in brief.slips} | {r.node_key: r.title for r in brief.rules}
    sound = next((s for s in brief.sounds if s.drill == plan.sound), None)
    entry = {
        "fix": plan.fix,
        "learn": plan.learn,
        "sound": plan.sound,
        "titles": {k: titles[k] for k in (plan.fix, plan.learn) if k in titles}
        | ({sound.drill: sound.title} if sound else {}),
        "sound_score": sound.score if sound else None,
        "focus": plan.focus,
    }
    days = {**journal.get(language, {}), day: entry}
    return {**journal, language: dict(sorted(days.items())[-JOURNAL_DAYS:])}


def _digest(brief: CoachBrief, prompt_ref: str) -> str:
    """What the plan depends on, the coach's prompt (its text, not only its version) included. What was done today
    and how many reviews wait are left out, and sound scores count only to the nearest 10, so ticking a stop,
    answering a card or one more take doesn't send the coach back to work."""
    sounds = [x.model_copy(update={"score": None if x.score is None else round(x.score, -1)}) for x in brief.sounds]
    basis = brief.model_copy(update={"done_today": [], "reviews_due": int(brief.reviews_due > 0), "sounds": sounds})
    return hashlib.sha256(f"{prompt_ref}|{basis.model_dump_json()}".encode()).hexdigest()[:24]


async def _gather(
    state: AppState, db: AsyncSession, user_id: uuid.UUID, profile: LearnerProfile, language: Language, reviews_due: int
) -> Picture:
    today = datetime.now(UTC).date()
    done = set(profile.settings.get("done_days", {}).get(today.isoformat(), []))
    since = datetime.combine(today, time(), UTC).timestamp() - MISTAKE_DAYS * 86_400
    played = (
        select(Scene.id, Scene.updated_at)
        .join(Session, Session.id == Scene.session_id)
        .where(
            Scene.user_id == user_id,
            Scene.status != "planned",
            Session.kind == "live",
            Session.city == LANGUAGE_CITY[language],
            Scene.updated_at >= datetime.fromtimestamp(since, UTC),
        )
        .order_by(Scene.updated_at.desc())
    )
    scenes = list(await db.execute(played))
    played_days = {when.date() for _, when in scenes}
    if today in played_days:
        done.add("story")
    steps = await key_points(state, db, user_id, language)
    by_key = {k.node_key: k for k in steps}
    learned_at = await _lessons_done(db, user_id, list(by_key))
    mistakes, last_made = await _mistakes(db, scenes[:MISTAKE_SCENES], by_key, learned_at, today)
    rules = [k for k in steps if k.core and k.status != "done"]
    rules.sort(key=lambda k: k.kind != "grammar")  # rules before word sets and phrases, each in curriculum order
    gym = await overview(state, profile, language)
    drills = {d.key: d for d in gym.drills}
    started = [d.key for d in gym.drills if d.score is not None and not d.mastered and d.key not in gym.workout]
    sounds = [
        Sound(drill=d.key, title=d.title, example=d.examples[0], score=d.score)
        for key in [*gym.workout, *started][:SOUNDS_OFFERED]
        if (d := drills[key]).examples
    ]
    # To fix: rules not learned yet, and learned ones made wrong again since (relapses first, then the most frequent,
    # then the most recent).
    fixable = [s for s in mistakes.values() if s.relapse or by_key[s.node_key].status != "done"]
    fixable.sort(key=lambda s: (not s.relapse, -s.times, s.days_ago))
    signals = Signals(
        story_ready=True,
        reviews_due=reviews_due,
        done=frozenset(done),
        slips=tuple(fixable[:SLIPS_OFFERED]),
        rules=tuple((k.node_key, k.title) for k in rules[:RULES_OFFERED]),
        sounds=tuple(sounds),
    )
    return Picture(today, signals, steps, gym, mistakes, last_made, played_days)


async def _lessons_done(db: AsyncSession, user_id: uuid.UUID, keys: list[str]) -> dict[str, datetime]:
    """When each rule's lesson was finished (its latest finish), for telling a relapse from a mistake never mended."""
    rows = await db.execute(
        select(Lesson.node_key, Lesson.updated_at).where(
            Lesson.user_id == user_id, Lesson.node_key.in_(keys), Lesson.status == "done"
        )
    )
    out: dict[str, datetime] = {}
    for key, when in rows:
        out[key] = max(when, out.get(key, when))
    return out


async def _mistakes(
    db: AsyncSession,
    scenes: list[Any],
    steps: dict[str, KeyPoint],
    learned_at: dict[str, datetime],
    today: date,
) -> tuple[dict[str, Slip], dict[str, date]]:
    """Confirmed mistakes (≥ 0.85 and a second check) of these scenes by rule, with the learner's latest words, in how
    many scenes, how long ago, and whether made again after the rule's lesson was finished."""
    if not scenes:
        return {}, {}
    when = {scene_id: at for scene_id, at in scenes}
    rows = await db.execute(
        select(Turn.scene_id, Assessment.error_tags)
        .join(Turn, Assessment.turn_id == Turn.id)
        .where(Turn.scene_id.in_(list(when)))
        .order_by(Turn.index)
    )
    latest: dict[str, tuple[datetime, ErrorTag]] = {}
    seen: dict[str, set[uuid.UUID]] = {}
    for scene_id, batch in rows:
        for tag in map(ErrorTag.model_validate, batch):
            if not tag.showable or tag.node_key not in steps:
                continue
            at = when[scene_id]
            if tag.node_key not in latest or at >= latest[tag.node_key][0]:
                latest[tag.node_key] = (at, tag)
            seen.setdefault(tag.node_key, set()).add(scene_id)
    out: dict[str, Slip] = {}
    for key, (at, tag) in latest.items():
        point = steps[key]
        relapse = point.status == "done" and key in learned_at and at > learned_at[key]
        out[key] = Slip(
            key, point.title, tag.span.text, tag.correction, len(seen[key]), (today - at.date()).days, relapse
        )
    return out, {key: at.date() for key, (at, _) in latest.items()}


def history(journal: dict[str, Any], picture: Picture, done_days: dict[str, list[str]]) -> list[str]:
    """The coach's journal read back, newest first: what it suggested each recent day and what came of it."""
    steps = {k.node_key: k for k in picture.steps}
    drills = {d.key: d for d in picture.gym.drills}
    lines = []
    for day, entry in sorted(journal.items(), reverse=True):
        on = date.fromisoformat(day)
        if on >= picture.today:
            continue
        titles: dict[str, str] = entry.get("titles", {})
        parts = []
        if fix := entry.get("fix"):
            again = picture.last_made.get(fix)
            outcome = f"made again {_ago(picture.today, again)}" if again and again > on else "not made since"
            if steps.get(fix) and steps[fix].status == "done" and not (again and again > on):
                outcome = "lesson done, not made since"
            parts.append(f"fix {titles.get(fix, fix)} ({outcome})")
        if learn := entry.get("learn"):
            status = steps[learn].status if learn in steps else "new"
            outcome = {"done": "learned", "open": "started"}.get(status, "not started")
            parts.append(f"learn {titles.get(learn, learn)} ({outcome})")
        if sound := entry.get("sound"):
            then, now = entry.get("sound_score"), drills[sound].score if sound in drills else None
            change = "not practised since" if now is None or now == then else f"score {_score(then)} → {_score(now)}"
            parts.append(f"sound {titles.get(sound, sound)} ({change})")
        did = sorted({*done_days.get(day, []), *(["story"] if on in picture.played_days else [])})
        lines.append(
            f"{_ago(picture.today, on)}: suggested "
            + ("; ".join(parts) or "nothing new")
            + f". They did: {', '.join(did) or 'nothing'}."
        )
    return lines[:HISTORY_SHOWN]


def _ago(today: date, day: date | None) -> str:
    days = (today - day).days if day else 0
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


def _score(value: float | None) -> str:
    return "none" if value is None else str(round(value))


async def _brief(
    state: AppState,
    db: AsyncSession,
    user: User,
    profile: LearnerProfile,
    language: Language,
    picture: Picture,
    skills: dict[str, str],
    exam_name: str,
    streak: int,
) -> CoachBrief:
    s = picture.signals
    learned = [k.title for k in picture.steps if k.status == "done"][-LEARNED_SHOWN:][::-1]
    keys = [key for key, _ in s.rules]
    mastery = await state.graph_deps.store.mastery(user.id, keys)
    kinds = {k.node_key: k for k in picture.steps}
    climbed = sum(d.mastered for d in picture.gym.drills)
    lived = await state.graph_deps.store.days_lived(user.id, LANGUAGE_CITY[language])
    lessons = sum(k.status == "done" for k in picture.steps)
    journal = profile.settings.get("coach_journal", {}).get(language, {})
    return CoachBrief(
        language=language,
        band=int(profile.settings.get("language_bands", {}).get(language, 5)),
        exam_name=exam_name,
        explain_language=LANGUAGE_NAME[user.ui_locale or "en"],
        skills=skills,
        progress=(
            f"{streak}-day streak; {lived} story days lived; {lessons} rules, words and phrases learned; "
            f"{climbed} of {len(picture.gym.drills)} sound drills climbed"
        ),
        learned=learned,
        slips=[
            SlipCandidate(
                node_key=x.node_key,
                title=x.title,
                said=x.said,
                better=x.better,
                times=x.times,
                days_ago=x.days_ago,
                relapse=x.relapse,
            )
            for x in s.slips
        ],
        rules=[
            RuleCandidate(
                node_key=key,
                title=title,
                kind=kinds[key].kind,
                band=kinds[key].band,
                in_use=round(mastery[key].p_mastery, 2) if key in mastery else 0.0,
            )
            for key, title in s.rules
        ],
        sounds=[SoundCandidate(drill=x.drill, title=x.title, score=x.score) for x in s.sounds],
        history=history(journal, picture, profile.settings.get("done_days", {})),
        done_today=sorted(s.done),
        reviews_due=s.reviews_due,
        story=await _story(state, db, user.id, language),
    )


async def _story(state: AppState, db: AsyncSession, user_id: uuid.UUID, language: Language) -> str:
    """The next scene of the day still to play, as the learner will see it (place, person, goal; never its hidden
    targets), so the coach can tie today's choices to it."""
    city = LANGUAGE_CITY[language]
    contract = (
        await db.execute(
            select(Scene.contract)
            .join(Session, Session.id == Scene.session_id)
            .where(
                Scene.user_id == user_id,
                Scene.status == "planned",
                Session.kind == "live",
                Session.city == city,
                Session.ended_at.is_(None),
            )
            .order_by(Session.started_at.desc(), Scene.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if contract is None:
        return ""
    content = load_city(state.settings.content_root, city)
    place = content.location(contract["location_key"]).name
    cast = contract.get("cast") or []
    npc = content.npc(cast[0]["npc_key"]) if cast else None
    who = f" with {npc.name} ({npc.role})" if npc else ""
    return f"{place}{who}: {contract['learner_goal']}"
