"""The learning coach (decision 0029): reads what the learner has shown (rules learned and used, mistakes confirmed in
recent scenes, sound scores, exam skills) and chooses today's mistake to fix, new rule and sound, each with one
sentence of why in the learner's interface language.

It may only choose among the candidates it is given, by key; anything else is dropped and the rule-based choice
stands. Reasons are cut to length. The caller caches the plan, so the home screen never waits for it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from lingard_contracts.common import LANGUAGE_NAME, LANGUAGE_SCALE
from lingard_llm import LLMRouter, PromptRegistry

REASON_CHARS = 160
"""A reason is one sentence on a home-screen card; the prompt asks for 140 and anything past this is cut."""


class SlipCandidate(BaseModel):
    node_key: str
    title: str
    said: str
    better: str | None = None
    times: int = 1
    """How many recent scenes it was confirmed in."""


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
    """Exam skill → met / close / behind / unknown."""
    learned: list[str] = []
    slips: list[SlipCandidate] = []
    rules: list[RuleCandidate] = []
    sounds: list[SoundCandidate] = []
    done_today: list[str] = []
    reviews_due: int = 0


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


async def coach(brief: CoachBrief, *, router: LLMRouter, prompts: PromptRegistry) -> CoachPlan:
    prompt = prompts.get("learning_coach")
    system, per_call = prompt.render_split(
        exam_name=brief.exam_name,
        explain_language=brief.explain_language,
        language_name=LANGUAGE_NAME[brief.language],
        scale_name=LANGUAGE_SCALE[brief.language],
        band=brief.band,
        skills=", ".join(f"{k} {v}" for k, v in brief.skills.items()) or "not measured yet",
        done_today=", ".join(brief.done_today) or "nothing yet",
        reviews=brief.reviews_due,
        learned="\n".join(f"- {title}" for title in brief.learned) or "(nothing yet)",
        slips="\n".join(
            f"- {s.node_key}: {s.title}. Said “{s.said}”"
            + (f", better “{s.better}”" if s.better else "")
            + (f" ({s.times} scenes)" if s.times > 1 else "")
            for s in brief.slips
        )
        or "(none)",
        rules="\n".join(f"- {r.node_key}: {r.title} ({r.kind}, level {r.band}, {r.in_use:.2f})" for r in brief.rules)
        or "(none)",
        sounds="\n".join(
            f"- {s.drill}: {s.title} ({'none' if s.score is None else round(s.score)})" for s in brief.sounds
        )
        or "(none)",
    )
    plan = await router.structured("mid", prompt, CoachPlan, router.messages("mid", system, per_call))
    return _within(plan, brief)


def _within(plan: CoachPlan, brief: CoachBrief) -> CoachPlan:
    """Only candidates' keys survive, and only reasons for what survives (a reason for a dropped choice would describe
    something else)."""
    fix = plan.fix if plan.fix in {s.node_key for s in brief.slips} else None
    learn = plan.learn if plan.learn in {r.node_key for r in brief.rules} else None
    sound = plan.sound if plan.sound in {s.drill for s in brief.sounds} else None

    def cut(text: str | None, keep: bool = True) -> str | None:
        text = (text or "").strip()
        if not keep or not text:
            return None
        return text if len(text) <= REASON_CHARS else text[: REASON_CHARS - 1].rstrip() + "…"

    why = Reasons(
        warmup=cut(plan.why.warmup),
        fix=cut(plan.why.fix, fix is not None),
        story=cut(plan.why.story),
        sounds=cut(plan.why.sounds, sound is not None),
        learn=cut(plan.why.learn, learn is not None),
    )
    return CoachPlan(fix=fix, learn=learn, sound=sound, why=why)
