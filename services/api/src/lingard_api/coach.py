"""Today's path (decision 0029): the few things worth doing today, in the order that teaches best, each with the
reason it was chosen drawn from what the learner has shown.

Remember first (reviews about to be forgotten), mend what tripped them up in recent scenes, use it in the story, then
tune one sound. A new rule is offered only when nothing from the scenes needs mending: one new idea a day, and never
before the story (decision 0025). Every stop can be tapped in any order; the path only suggests.

The order is fixed here. What fills it, and the reasons, come from the learning coach (an LLM reading the learner's
progress, :mod:`lingard_graphs.agents.learning_coach`) once its plan for the day is ready; until then, and whenever it
fails, the first candidate of each kind stands and the app words the reasons itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from lingard_graphs.agents.learning_coach import CoachPlan

StopKind = Literal["warmup", "fix", "story", "sounds", "learn"]

WARMUP_CARDS = 8
"""A warm-up is a handful of cards, never the whole pile: a count of 40 is a wall, eight is a minute or two."""


class Stop(BaseModel):
    kind: StopKind
    done: bool
    minutes: int
    why: str | None = None
    """The coach's reason, in the learner's interface language; ``None`` until its plan is ready."""
    count: int | None = None
    """Warm-up: cards in it."""
    node_key: str | None = None
    """Fix or learn: the key point to open."""
    title: str | None = None
    """Fix or learn: the rule; sounds: the drill."""
    said: str | None = None
    """Fix: the words the learner actually said, quoted back as the reason."""
    better: str | None = None
    """Fix: how to say them."""
    drill: str | None = None
    """Sounds: the drill to open."""
    example: str | None = None
    """Sounds: a word with the sound, e.g. "rue"."""


@dataclass(frozen=True)
class Slip:
    """A confirmed mistake (≥ 0.85 and a second check) from a recent scene, on a rule not yet learned."""

    node_key: str
    title: str
    said: str
    better: str | None
    times: int = 1


@dataclass(frozen=True)
class Sound:
    drill: str
    title: str
    example: str
    score: float | None = None


@dataclass(frozen=True)
class Signals:
    story_ready: bool
    """Goal and level known: the story can be played."""
    reviews_due: int = 0
    done: frozenset[str] = field(default_factory=frozenset)
    """What was done today: "review", "lesson", "story", "sounds"."""
    slips: tuple[Slip, ...] = ()
    """Most frequent first."""
    rules: tuple[tuple[str, str], ...] = ()
    """Rules at the learner's level not yet learned, in the curriculum's order: (node key, title)."""
    sounds: tuple[Sound, ...] = ()
    """Today's sound workout, in its order."""


def plan_path(s: Signals, plan: CoachPlan | None = None) -> list[Stop]:
    if not s.story_ready:
        return []  # setting a goal and the placement come first; the home screen walks the learner through those
    why = plan.why if plan else None
    path: list[Stop] = []
    if s.reviews_due or "review" in s.done:
        count = min(s.reviews_due, WARMUP_CARDS)
        path.append(Stop(kind="warmup", done="review" in s.done, minutes=2, count=count, why=why and why.warmup))
    slip = _pick(s.slips, plan.fix if plan else None, lambda x: x.node_key)
    if slip:
        path.append(
            Stop(
                kind="fix",
                done=False,
                minutes=3,
                why=why.fix if why and plan and plan.fix == slip.node_key else None,
                node_key=slip.node_key,
                title=slip.title,
                said=slip.said,
                better=slip.better,
            )
        )
    path.append(Stop(kind="story", done="story" in s.done, minutes=10, why=why and why.story))
    sound = _pick(s.sounds, plan.sound if plan else None, lambda x: x.drill)
    if sound:
        path.append(
            Stop(
                kind="sounds",
                done="sounds" in s.done,
                minutes=5,
                why=why.sounds if why and plan and plan.sound == sound.drill else None,
                drill=sound.drill,
                title=sound.title,
                example=sound.example,
            )
        )
    if not slip and ("lesson" in s.done or s.rules):
        # Learned today: the stop is ticked, not refilled with the next rule.
        rule = _pick(s.rules, plan.learn if plan else None, lambda x: x[0]) if "lesson" not in s.done else None
        path.append(
            Stop(
                kind="learn",
                done=rule is None,
                minutes=5,
                why=why.learn if rule and why and plan and plan.learn == rule[0] else None,
                node_key=rule and rule[0],
                title=rule and rule[1],
            )
        )
    return path


def _pick[T](candidates: tuple[T, ...], chosen: str | None, key: Callable[[T], str]) -> T | None:
    """The coach's choice when it is still a candidate, else the first one."""
    fallback = candidates[0] if candidates else None
    return next((c for c in candidates if chosen is not None and key(c) == chosen), fallback)
