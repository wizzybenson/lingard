"""Native calibration of the scores (decision 0028), measured by ``tools/content_cli/calibrate.py``.

``scale``: per sound, the 10th and 50th percentile GOP of native speech, so a sound is scored against how native
speakers say it. ``contrasts``: per minimal pair (target, partner), where the two-way test separates native targets
from the partner said instead, and whether it does so reliably enough to judge a learner by it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Contrast:
    threshold: float
    """Log-likelihood ratio halfway between native targets (10th percentile) and substitutions (90th)."""
    width: float
    reliable: bool
    strong: bool = False
    """Separated at least 90% of the time both ways: then this test alone decides."""


STRESS_AGREEMENT = 1.0
"""A word's stress is judged only where the detector finds its dictionary stress in every native recording: a word it
got wrong for a native speaker could be marked wrong for a learner who said it right."""


@dataclass(frozen=True)
class Calibration:
    model: str
    scale: dict[str, tuple[float, float]]
    contrasts: dict[tuple[str, str], Contrast]
    prosody: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Per part of the music, the 10th and 50th percentile score of one native voice against another."""
    stress_words: dict[str, float] = field(default_factory=dict)
    """How often the detector finds each word's dictionary stress in native recordings."""
    stress_syllable: dict[str, int] = field(default_factory=dict)
    """Each judged word's stressed syllable, from the dictionary: the learner is held to it, not to how one model
    happened to read the word."""

    def music_score(self, part: str, raw: float) -> float:
        """A raw music score against native spread: the edge of native range (10th percentile) scores 75, a typical
        native pair (median) 95; below the edge it falls to 0."""
        if part not in self.prosody:
            return raw
        p10, p50 = self.prosody[part]
        if raw >= p10:
            return min(100.0, 75 + (raw - p10) * 20 / max(p50 - p10, 1.0))
        return 75 * raw / max(p10, 1.0)

    def stress_judged(self, word: str) -> bool:
        return self.stress_words.get(word.casefold(), 0.0) >= STRESS_AGREEMENT

    def strong(self, target: str, partner: str) -> bool:
        c = self.contrasts.get((target, partner))
        return c is not None and c.strong

    def contrast_score(self, target: str, partner: str, llr: float) -> tuple[float, bool] | None:
        """0–100 for "this was the target, not the partner" (about 90 at the edge of native range, 50 at the
        threshold), and whether this contrast can be trusted; ``None`` when it wasn't measured."""
        c = self.contrasts.get((target, partner))
        if c is None:
            return None
        return 100 / (1 + math.exp(-2.2 * (llr - c.threshold) / c.width)), c.reliable


def load_calibration(content_root: Path, language: str, model: str) -> Calibration | None:
    """The language's calibration, if one was measured for this recogniser (another model's numbers mean nothing)."""
    path = content_root / "pronunciation" / f"calibration_{language}.yaml"
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text())
    if data.get("model") != model:
        return None
    scale = {p: (float(v["p10"]), float(v["p50"])) for p, v in data["scale"].items()}
    contrasts: dict[tuple[str, str], Contrast] = {
        (pair.split(" ")[0], pair.split(" ")[1]): Contrast(
            float(v["threshold"]), float(v["width"]), bool(v["reliable"])
        )
        for pair, v in (data.get("contrasts") or {}).items()
    }
    prosody = {part: (float(v["p10"]), float(v["p50"])) for part, v in (data.get("prosody") or {}).items()}
    words = data.get("stress_words") or {}
    agreement = {w: float(v["agreement"]) if isinstance(v, dict) else float(v) for w, v in words.items()}
    syllable = {w: int(v["syllable"]) for w, v in words.items() if isinstance(v, dict)}
    return Calibration(model, scale, contrasts, prosody, agreement, syllable)
