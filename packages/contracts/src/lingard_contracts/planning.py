"""Director and Teacher outputs (SPEC §10, §16)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from lingard_contracts.common import CityKey, NodeKey, Strict
from lingard_contracts.scene import Intensity


class SceneBrief(Strict):
    """What the Director asks the Scene Compiler to build."""

    brief_id: UUID = Field(default_factory=uuid4)
    city: CityKey
    location_key: str
    npc_keys: list[str] = Field(min_length=1)
    story_beat: str
    targets: list[NodeKey] = Field(min_length=1)
    ticket_targets: list[NodeKey] = Field(default_factory=list)
    learner_band: int = Field(ge=1, le=12)
    intensity: Intensity = "calm"
    pack_alignment: list[str] = Field(default_factory=list)


class LessonSlot(Strict):
    node_key: NodeKey
    reason: Literal["ticket_reopened", "director", "new_band"] = "director"


class DayPlan(Strict):
    user_id: UUID
    city: CityKey
    scenes: list[SceneBrief] = Field(min_length=1)
    lessons: list[LessonSlot] = Field(default_factory=list)

    def ticket_share(self) -> float:
        all_targets = [t for s in self.scenes for t in s.targets]
        if not all_targets:
            return 0.0
        ticket = {t for s in self.scenes for t in s.ticket_targets}
        return sum(1 for t in all_targets if t in ticket) / len(all_targets)


GameKind = Literal[
    "conjugation_duel", "sentence_race", "spot_the_error", "dictation", "register_switch", "fill_the_gap"
]


class GameItem(Strict):
    prompt: str
    answer: str
    distractors: list[str] = Field(default_factory=list)
    node_key: NodeKey


class Game(Strict):
    kind: GameKind
    items: list[GameItem] = Field(min_length=1)
    time_limit_s: int | None = None


class LessonExample(Strict):
    learner_said: str
    better: str
    note: str = ""


class Lesson(Strict):
    node_key: NodeKey
    kind: Literal["key_points", "remedial"] = "remedial"
    """key_points: taught before the learner needs the rule, from authored content (no mistakes yet).
    remedial: built from the learner's own mistakes."""
    title: str
    rule: str
    models: list[str] = Field(default_factory=list)
    """Correct sentences that show the rule at work."""
    words: list[str] = Field(default_factory=list)
    """The words (a vocabulary set) or phrases (a function) the lesson teaches, each one listenable."""
    examples: list[LessonExample] = Field(min_length=1)
    """Wrong → right pairs: the learner's own mistakes (remedial) or common ones (key points)."""
    games: list[Game] = Field(min_length=1)
    homework: SceneBrief
    minutes: int = Field(default=8, ge=5, le=10)
