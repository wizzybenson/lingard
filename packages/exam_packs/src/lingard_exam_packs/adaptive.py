"""Adaptive testing with a 1-parameter (Rasch) model and EAP ability estimates (SPEC §17).

Start mid-band, pick the most informative unseen item, stop when the standard error falls below a threshold
or after ``max_items``. Pure functions: the placement graph replays them deterministically on resume.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from lingard_exam_packs.items import Item, logit_to_band

GRID = [x / 10 for x in range(-50, 51)]


def p_correct(theta: float, difficulty: float) -> float:
    return 1 / (1 + math.exp(-(theta - difficulty)))


@dataclass(frozen=True)
class Estimate:
    theta: float
    se: float

    @property
    def band(self) -> float:
        return logit_to_band(self.theta)

    @property
    def band_se(self) -> float:
        return self.se / 0.75


def estimate(responses: list[tuple[float, bool]], prior_mean: float = 0.0, prior_sd: float = 1.5) -> Estimate:
    """EAP over a grid with a normal prior; ``responses`` = (difficulty, correct)."""
    weights = []
    for theta in GRID:
        log_w = -((theta - prior_mean) ** 2) / (2 * prior_sd**2)
        for difficulty, correct in responses:
            p = p_correct(theta, difficulty)
            log_w += math.log(p if correct else 1 - p)
        weights.append(log_w)
    peak = max(weights)
    probs = [math.exp(w - peak) for w in weights]
    total = sum(probs)
    mean = sum(t * p for t, p in zip(GRID, probs, strict=True)) / total
    var = sum((t - mean) ** 2 * p for t, p in zip(GRID, probs, strict=True)) / total
    return Estimate(theta=mean, se=math.sqrt(var))


def next_item(candidates: list[Item], current: Estimate) -> Item | None:
    """Maximum Fisher information at the current estimate (ties broken by id for determinism)."""
    if not candidates:
        return None

    def information(item: Item) -> float:
        p = p_correct(current.theta, item.difficulty)
        return p * (1 - p)

    return max(sorted(candidates, key=lambda i: i.id), key=information)


def should_stop(current: Estimate, answered: int, *, se_threshold: float, max_items: int, min_items: int = 4) -> bool:
    return answered >= max_items or (answered >= min_items and current.se <= se_threshold)
