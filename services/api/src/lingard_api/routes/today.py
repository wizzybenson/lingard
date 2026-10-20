"""``/v1/today``: the home card. Streak, what to do next, and how far each skill is from the learner's goal."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from lingard_api.deps import Db, Principal, State
from lingard_api.routes.key_points import key_points
from lingard_api.routes.learning import learner_bands
from lingard_api.routes.me import DEFAULT_TARGETS
from lingard_contracts.common import LANGUAGE_PACK, Language, PackId
from lingard_db.models import LearnerProfile, Lesson, Session, Wallet
from lingard_economy.events import streak
from lingard_graphs.pedagogy.review import due_at

router = APIRouter(prefix="/v1", tags=["today"])

NextStep = Literal["set_goal", "placement", "key_points", "lesson", "story"]
SKILL_ORDER = ["listening", "reading", "writing", "speaking"]


class SkillGoal(BaseModel):
    skill: str
    target: int
    level_low: int | None
    level_high: int | None
    status: Literal["met", "close", "behind", "unknown"]


class Goal(BaseModel):
    pack: PackId
    pack_name: str
    exam_date: date | None
    days_left: int | None
    skills: list[SkillGoal]


class Onboarding(BaseModel):
    """First-run checklist: a new learner is walked through goal → placement → first story."""

    goal: bool
    placement: bool
    first_story: bool


class NextKeyPoint(BaseModel):
    """The first rule at the learner's level not yet learned: the Today card opens it directly."""

    node_key: str
    title: str


class Today(BaseModel):
    streak: int
    practised_today: bool
    reviews_due: int
    lessons_waiting: int
    goals: list[Goal]
    next_step: NextStep
    next_key_point: NextKeyPoint | None = None
    onboarding: Onboarding
    coins: int = 0
    """The learner's coins, shown beside the streak so every mission's reward is felt on the home screen."""


def skill_status(target: int, low: int | None, high: int | None) -> Literal["met", "close", "behind", "unknown"]:
    """Met when even the low end of the 80% range reaches the target; behind when the high end doesn't."""
    if low is None or high is None:
        return "unknown"
    if low >= target:
        return "met"
    return "behind" if high < target else "close"


@router.get("/today", response_model=Today)
async def today(principal: Principal, state: State, db: Db) -> Today:
    store = state.graph_deps.store
    now = datetime.now(UTC)
    profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == principal.user_id))).scalar_one()
    days = await store.active_days(principal.user_id)
    current, _ = streak(days, now.date())
    cards = await store.fsrs(principal.user_id)
    reviews_due = sum(due_at(card) <= now for card in cards.values())
    lessons_waiting = (
        await db.execute(
            select(func.count()).select_from(Lesson).where(Lesson.user_id == principal.user_id, Lesson.status != "done")
        )
    ).scalar_one()
    targets = profile.target_bands or DEFAULT_TARGETS
    exam_dates: dict[str, str] = profile.settings.get("exam_dates", {})
    bands = await learner_bands(state, db, principal.user_id)
    goals = []
    for pack_id in sorted({*exam_dates, *(b.pack for b in bands)}):
        pack = state.packs.pack(pack_id)  # type: ignore[arg-type]
        exam = date.fromisoformat(exam_dates[pack_id]) if exam_dates.get(pack_id) else None
        by_skill = {b.skill.value: b for b in bands if b.pack == pack_id}
        skills = []
        pack_targets = targets.get(pack_id, {})
        for skill in sorted(pack_targets, key=lambda k: SKILL_ORDER.index(k) if k in SKILL_ORDER else len(SKILL_ORDER)):
            target = pack_targets[skill]
            band = by_skill.get(skill)
            low, high = (band.clb_nclc_low, band.clb_nclc_high) if band else (None, None)
            skills.append(
                SkillGoal(
                    skill=skill, target=target, level_low=low, level_high=high, status=skill_status(target, low, high)
                )
            )
        goals.append(
            Goal(
                pack=pack_id,
                pack_name=pack.name,
                exam_date=exam,
                days_left=(exam - now.date()).days if exam else None,
                skills=skills,
            )
        )
    stories = (
        await db.execute(
            select(func.count())
            .select_from(Session)
            .where(Session.user_id == principal.user_id, Session.kind == "live", Session.ended_at.is_not(None))
        )
    ).scalar_one()
    practised_today = now.date() in days
    studying: list[Language] = [lang for lang in ("fr", "en") if LANGUAGE_PACK[lang] in exam_dates]
    pending = None
    for language in studying:
        steps = await key_points(state, db, principal.user_id, language)
        # The rules gate the story; the level's words and phrases are offered beside it in School.
        pending = pending or next((k for k in steps if k.core and k.kind == "grammar" and k.status != "done"), None)
    step: NextStep
    # Progress decides what comes next, never the calendar: due reviews are offered beside the story, not before it.
    if not exam_dates:
        step = "set_goal"
    elif not bands:
        step = "placement"
    elif pending is not None:
        step = "key_points"  # the rules come before the scene that needs them
    elif lessons_waiting:
        step = "lesson"
    else:
        step = "story"
    coins = (await db.execute(select(Wallet.coins).where(Wallet.user_id == principal.user_id))).scalar_one_or_none()
    return Today(
        streak=current,
        practised_today=practised_today,
        reviews_due=reviews_due,
        lessons_waiting=lessons_waiting,
        goals=goals,
        next_step=step,
        next_key_point=NextKeyPoint(node_key=pending.node_key, title=pending.title) if pending else None,
        onboarding=Onboarding(goal=bool(exam_dates), placement=bool(bands), first_story=stories > 0),
        coins=coins or 0,
    )
