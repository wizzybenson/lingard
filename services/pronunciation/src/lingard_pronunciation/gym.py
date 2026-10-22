"""Sound gym (decision 0028): the drills that retrain an accent, and the ladder each one is climbed by.

A drill trains one or a few sounds (or, with no sounds, a feature of connected speech: liaison, stress, melody). It is
climbed in order: learn how the sound is made → hear the difference → say the words → say the pairs → say the
phrases → say the sentence. A climbed drill is then reviewed on a spaced schedule; a failed review sends it back to
the words. Content comes from ``content/pronunciation/sounds_<lang>.yaml`` and the curriculum's ``pron`` nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from functools import cache
from pathlib import Path
from typing import Any

import yaml


class Stage(IntEnum):
    LEARN = 0
    HEAR = 1
    WORDS = 2
    PAIRS = 3
    PHRASES = 4
    SENTENCE = 5
    MASTERED = 6


GOOD = 70.0
"""A target sound scoring this well counts as said right."""
SENTENCE_GOOD = 75.0
MELODY_GOOD = 60.0
HEAR_GOOD = 0.8
"""Share of minimal-pair questions answered right to pass the listening stage."""
NEEDED = {Stage.WORDS: 5, Stage.PAIRS: 3, Stage.PHRASES: 3, Stage.SENTENCE: 1}
"""Good attempts that climb each spoken stage: different items, so a lucky repeat doesn't count twice."""


@dataclass(frozen=True)
class Drill:
    key: str
    sounds: tuple[str, ...]
    words: tuple[str, ...]
    pairs: tuple[tuple[str, str], ...]
    phrases: tuple[str, ...]
    sentence: str
    melody: bool = False

    def items(self, stage: Stage) -> tuple[str, ...]:
        """What is said at a spoken stage (a pair is said as its two words)."""
        if stage is Stage.WORDS:
            return self.words
        if stage is Stage.PAIRS:
            return tuple(f"{a} / {b}" for a, b in self.pairs)
        if stage is Stage.PHRASES:
            return self.phrases
        if stage is Stage.SENTENCE:
            return (self.sentence,)
        return ()

    def stages(self) -> list[Stage]:
        """The stages this drill has: no listening or pairs without pairs, no words or phrases without them."""
        have = {
            Stage.LEARN: bool(self.sounds),
            Stage.HEAR: bool(self.pairs),
            Stage.WORDS: bool(self.words),
            Stage.PAIRS: bool(self.pairs),
            Stage.PHRASES: bool(self.phrases),
            Stage.SENTENCE: True,
        }
        return [stage for stage, present in have.items() if present]


@dataclass(frozen=True)
class Gym:
    language: str
    phonemes: dict[str, dict[str, Any]]
    features: dict[str, dict[str, Any]]
    drills: tuple[Drill, ...]

    def drill(self, key: str) -> Drill:
        for drill in self.drills:
            if drill.key == key:
                return drill
        raise KeyError(key)

    def texts(self) -> list[str]:
        """Every text a drill asks the learner to hear or say (pairs as their single words)."""
        found: list[str] = []
        for drill in self.drills:
            found += [*drill.words, *drill.phrases, drill.sentence]
            found += [w for pair in drill.pairs for w in pair]
        found += [str(p["example"]) for p in self.phonemes.values()]
        return list(dict.fromkeys(found))


@cache
def load_gym(content_root: Path, language: str) -> Gym:
    data: dict[str, Any] = yaml.safe_load((content_root / "pronunciation" / f"sounds_{language}.yaml").read_text())
    pron = yaml.safe_load((content_root / "curriculum" / language / "pron.yaml").read_text())
    node_pairs = {n["key"]: n.get("payload", {}).get("minimal_pairs", []) for n in pron["nodes"]}
    drills = []
    for raw in data["drills"]:
        pairs = [*node_pairs.get(raw["key"], []), *raw.get("pairs", [])]
        drills.append(
            Drill(
                key=raw["key"],
                sounds=tuple(raw.get("sounds", [])),
                words=tuple(str(w) for w in raw.get("words", [])),
                pairs=tuple(dict.fromkeys((str(a), str(b)) for a, b in pairs)),
                phrases=tuple(str(p) for p in raw.get("phrases", [])),
                sentence=str(raw["sentence"]),
                melody=bool(raw.get("melody", False)),
            )
        )
    return Gym(language, data["phonemes"], data["features"], tuple(drills))


@dataclass
class Progress:
    """One learner's climb of one drill, stored as JSON on their profile."""

    stage: Stage = Stage.LEARN
    passed_items: list[str] = field(default_factory=list)
    """Items said well at the current stage."""
    best: dict[str, float] = field(default_factory=dict)
    """Best score per target sound so far."""

    @classmethod
    def load(cls, raw: dict[str, Any] | None) -> Progress:
        raw = raw or {}
        return cls(Stage(raw.get("stage", 0)), list(raw.get("passed_items", [])), dict(raw.get("best", {})))

    def dump(self) -> dict[str, Any]:
        return {"stage": int(self.stage), "passed_items": self.passed_items, "best": self.best}

    def advance(self, drill: Drill) -> None:
        """On to the drill's next stage."""
        later = [s for s in drill.stages() if s > self.stage]
        self.stage = later[0] if later else Stage.MASTERED
        self.passed_items = []

    def start(self, drill: Drill) -> None:
        if self.stage not in drill.stages() and self.stage is not Stage.MASTERED:
            self.advance(drill)


def target_score(drill: Drill, words: list[dict[str, Any]]) -> float | None:
    """How well the drill's own sounds were said in one attempt (every sound, for a drill without targets)."""
    sounds = [p for w in words for p in w["phonemes"]]
    wanted = [p["score"] for p in sounds if not drill.sounds or p["phoneme"] in drill.sounds]
    return sum(wanted) / len(wanted) if wanted else None


def record_attempt(
    progress: Progress, drill: Drill, stage: Stage, item: str, words: list[dict[str, Any]], intonation: float | None
) -> bool:
    """Counts one spoken attempt toward its stage; returns whether it was good. Climbs when the stage is done."""
    for sound in (p for w in words for p in w["phonemes"]):
        if sound["phoneme"] in drill.sounds:
            progress.best[sound["phoneme"]] = max(progress.best.get(sound["phoneme"], 0.0), float(sound["score"]))
    score = target_score(drill, words)
    threshold = SENTENCE_GOOD if stage is Stage.SENTENCE else GOOD
    good = score is not None and score >= threshold
    if stage is Stage.SENTENCE and drill.melody:
        good = good and intonation is not None and intonation >= MELODY_GOOD
    if good and stage == progress.stage and item not in progress.passed_items:
        progress.passed_items.append(item)
        if len(progress.passed_items) >= min(NEEDED[stage], len(drill.items(stage))):
            progress.advance(drill)
    return good
