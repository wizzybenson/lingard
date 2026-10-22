"""Native calibration of the scores (decision 0028), measured by ``tools/content_cli/calibrate.py``.

``scale``: per sound, the 10th and 50th percentile GOP of native speech, so a sound is scored against how native
speakers say it. ``contrasts``: per minimal pair (target, partner), where the two-way test separates native targets
from the partner said instead, and whether it does so reliably enough to judge a learner by it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Contrast:
    threshold: float
    """Log-likelihood ratio halfway between native targets (10th percentile) and substitutions (90th)."""
    width: float
    reliable: bool


@dataclass(frozen=True)
class Calibration:
    model: str
    scale: dict[str, tuple[float, float]]
    contrasts: dict[tuple[str, str], Contrast]

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
    return Calibration(model, scale, contrasts)
