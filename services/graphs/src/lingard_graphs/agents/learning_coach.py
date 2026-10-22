"""The learning coach (decision 0029): reads what the learner has shown and chooses today's mistake to fix, new rule
and sound, each with one sentence of why in the learner's interface language, plus the focus of their coming week.

What it reads:
- where they stand: level per exam skill against their goal, streak, how far into the story;
- what they know: rules learned (by lesson or by using them well), and how surely they use the rest (BKT);
- what trips them: mistakes confirmed in their scenes over the last weeks, how often and how lately, and relapses
  (a mistake again on a rule they had learned);
- its own memory: what it suggested on recent days and what came of it (followed or not, the mistake gone or back,
  the sound score since);
- today: the scene to play, reviews waiting, what is done.

It may only choose among the candidates it is given, by key; anything else is dropped and the rule-based choice
stands. Text is cut to length. The caller caches the plan and keeps the journal, so the home screen never waits.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from lingard_contracts.common import LANGUAGE_NAME, LANGUAGE_SCALE
from lingard_llm import LLMRouter, PromptRegistry

REASON_CHARS = 160
"""A reason is one sentence on a home-screen card; the prompt asks for 140 and anything past this is cut."""
FOCUS_CHARS = 240
"""The week's focus is two short sentences at most."""


class SlipCandidate(BaseModel):
    node_key: str
    title: str
    said: str
    better: str | None = None
    times: int = 1
    """How many recent scenes it was confirmed in."""
    days_ago: int = 0
    """Since it was last made."""
    relapse: bool = False
    """Made again after the rule was learned: the lesson didn't hold."""


class RuleCandidate(BaseModel):
    node_key: str
    title: str
    kind: str
    band: int
    in_use: float
    """How surely the learner already uses it (BKT p(mastery))."""


class SoundCandidate(BaseModel):
    drill: str
    title: str
    score: float | None


class CoachBrief(BaseModel):
    language: str
    band: int
    exam_name: str
    explain_language: str
    skills: dict[str, str] = {}
    """Exam skill → its level against the goal, e.g. "5-7 of goal 9 (behind)"."""
    progress: str = ""
    """Streak, story days lived, lessons and sounds done: how far along the learner is."""
    learned: list[str] = []
    slips: list[SlipCandidate] = []
    rules: list[RuleCandidate] = []
    sounds: list[SoundCandidate] = []
    history: list[str] = []
    """The coach's own memory: one line per recent day, what it suggested and what came of it (newest first)."""
    done_today: list[str] = []
    reviews_due: int = 0
    story: str = ""
    """Today's next scene as the learner sees it: place, person and goal."""


class Reasons(BaseModel):
    warmup: str | None = None
    fix: str | None = None
    story: str | None = None
    sounds: str | None = None
    learn: str | None = None


class CoachPlan(BaseModel):
    fix: str | None = None
    """Key of the mistake to fix, from the slips."""
    learn: str | None = None
    """Key of the new rule, from the rules."""
    sound: str | None = None
    """Drill key, from the sounds."""
    why: Reasons = Field(default_factory=Reasons)
    focus: str | None = None
    """What the coming days are about and the next milestone, for the learner to read on the home screen."""


async def coach(brief: CoachBrief, *, router: LLMRouter, prompts: PromptRegistry) -> CoachPlan:
    prompt = prompts.get("learning_coach")
    system, per_call = prompt.render_split(
        exam_name=brief.exam_name,
        explain_language=brief.explain_language,
        language_name=LANGUAGE_NAME[brief.language],
        scale_name=LANGUAGE_SCALE[brief.language],
        band=brief.band,
        skills=", ".join(f"{k} {v}" for k, v in brief.skills.items()) or "not measured yet",
        progress=brief.progress or "just starting",
        done_today=", ".join(brief.done_today) or "nothing yet",
        reviews=brief.reviews_due,
        story=brief.story or "not planned yet",
        history="\n".join(f"- {line}" for line in brief.history) or "(no earlier days yet)",
        learned="\n".join(f"- {title}" for title in brief.learned) or "(nothing yet)",
        slips="\n".join(_slip_line(s) for s in brief.slips) or "(none)",
        rules="\n".join(f"- {r.node_key}: {r.title} ({r.kind}, level {r.band}, {r.in_use:.2f})" for r in brief.rules)
        or "(none)",
        sounds="\n".join(
            f"- {s.drill}: {s.title} ({'none' if s.score is None else round(s.score)})" for s in brief.sounds
        )
        or "(none)",
    )
    plan = await router.structured("mid", prompt, CoachPlan, router.messages("mid", system, per_call))
    return _within(plan, brief)


def _slip_line(s: SlipCandidate) -> str:
    when = "today" if s.days_ago == 0 else "yesterday" if s.days_ago == 1 else f"{s.days_ago} days ago"
    line = f"- {s.node_key}: {s.title}. Said “{s.said}”" + (f", better “{s.better}”" if s.better else "")
    line += f" ({s.times} scene{'s' if s.times > 1 else ''}, last {when})"
    return line + (" RELAPSE: made again after the rule was learned" if s.relapse else "")


def _cut(text: str | None, limit: int, keep: bool = True) -> str | None:
    text = " ".join((text or "").split())
    if not keep or not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _within(plan: CoachPlan, brief: CoachBrief) -> CoachPlan:
    """Only candidates' keys survive, and only reasons for what survives (a reason for a dropped choice would describe
    something else)."""
    fix = plan.fix if plan.fix in {s.node_key for s in brief.slips} else None
    learn = plan.learn if plan.learn in {r.node_key for r in brief.rules} else None
    sound = plan.sound if plan.sound in {s.drill for s in brief.sounds} else None
    why = Reasons(
        warmup=_cut(plan.why.warmup, REASON_CHARS),
        fix=_cut(plan.why.fix, REASON_CHARS, fix is not None),
        story=_cut(plan.why.story, REASON_CHARS),
        sounds=_cut(plan.why.sounds, REASON_CHARS, sound is not None),
        learn=_cut(plan.why.learn, REASON_CHARS, learn is not None),
    )
    return CoachPlan(fix=fix, learn=learn, sound=sound, why=why, focus=_cut(plan.focus, FOCUS_CHARS))
