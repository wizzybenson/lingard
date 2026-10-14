# Lifted from simupatient@69e1bd5:backend/benchmarks/voice_latency/scoring.py
"""Percentiles and bootstrap confidence intervals, including the paired two-level (item, repeat) bootstrap.

Adapted: typed signatures; the ``stat`` callable is explicit.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable

Stat = Callable[[list[float]], float]


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile (numpy 'linear'); q in [0, 100]. Raises on empty input."""
    if not values:
        raise ValueError("percentile of empty sequence")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (q / 100)
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return float(ordered[low])
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def bootstrap_ci(
    values: list[float], q: float = 50, *, iterations: int = 2000, alpha: float = 0.05, seed: int = 1729
) -> tuple[float, float] | None:
    if len(values) < 2:
        return None
    rng = random.Random(seed)  # noqa: S311
    stats = sorted(percentile([rng.choice(values) for _ in values], q) for _ in range(iterations))
    return percentile(stats, 100 * alpha / 2), percentile(stats, 100 * (1 - alpha / 2))


def bootstrap_delta_ci(
    baseline: list[float],
    candidate: list[float],
    q: float = 50,
    *,
    iterations: int = 2000,
    alpha: float = 0.05,
    seed: int = 1729,
) -> tuple[float, float] | None:
    """CI for percentile(candidate) − percentile(baseline); negative = faster."""
    if len(baseline) < 2 or len(candidate) < 2:
        return None
    rng = random.Random(seed)  # noqa: S311
    deltas = sorted(
        percentile([rng.choice(candidate) for _ in candidate], q)
        - percentile([rng.choice(baseline) for _ in baseline], q)
        for _ in range(iterations)
    )
    return percentile(deltas, 100 * alpha / 2), percentile(deltas, 100 * (1 - alpha / 2))


def hierarchical_bootstrap_delta(
    baseline: dict[str, list[float]],
    candidate: dict[str, list[float]],
    stat: Stat,
    *,
    iterations: int = 2000,
    alpha: float = 0.05,
    seed: int = 1729,
) -> tuple[float, float] | None:
    """Paired two-level bootstrap: resample items (the pairing unit), then repeats within each item."""
    items = [i for i in sorted(set(baseline) & set(candidate)) if baseline[i] and candidate[i]]
    if len(items) < 2:
        return None
    rng = random.Random(seed)  # noqa: S311
    deltas = []
    for _ in range(iterations):
        pooled_base: list[float] = []
        pooled_cand: list[float] = []
        for _ in items:
            item = rng.choice(items)
            pooled_base.extend(rng.choice(baseline[item]) for _ in baseline[item])
            pooled_cand.extend(rng.choice(candidate[item]) for _ in candidate[item])
        deltas.append(stat(pooled_cand) - stat(pooled_base))
    deltas.sort()
    return percentile(deltas, 100 * alpha / 2), percentile(deltas, 100 * (1 - alpha / 2))
