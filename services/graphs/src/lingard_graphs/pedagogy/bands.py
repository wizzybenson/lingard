"""Band posterior per skill (SPEC §12.2): Gaussian with evidence-weighted updates, 80% interval, calibration."""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from statistics import NormalDist

from lingard_contracts.assessment import BandEstimate
from lingard_contracts.common import PackId, Skill
from lingard_curriculum.packs import Conversion, ExamPack
from lingard_graphs.pedagogy.config import Bands


@dataclass
class BandPosterior:
    mean: float
    variance: float
    observations: int = 0

    def update(self, observed: float, observation_variance: float) -> BandPosterior:
        precision = 1 / self.variance + 1 / observation_variance
        mean = (self.mean / self.variance + observed / observation_variance) / precision
        return BandPosterior(mean=mean, variance=1 / precision, observations=self.observations + 1)

    @property
    def sd(self) -> float:
        return math.sqrt(self.variance)

    def interval(self, mass: float) -> tuple[float, float]:
        z = NormalDist().inv_cdf(0.5 + mass / 2)
        return self.mean - z * self.sd, self.mean + z * self.sd

    def probability_at_least(self, threshold: float) -> float:
        return 1 - NormalDist(self.mean, self.sd).cdf(threshold)


def prior(pack: ExamPack, skill: Skill, guess: float | None, rules: Bands) -> BandPosterior:
    """Wide prior centred on a guess (placement) or mid-scale. Variance is in band² for IELTS, scaled for TEF points."""
    top = pack.max_score(skill)
    scale = 1.0 if pack.scale.type == "band" else (top / 9) ** 2
    centre = guess if guess is not None else top / 2
    return BandPosterior(mean=centre, variance=rules.prior_variance * scale)


def observe(
    posterior: BandPosterior, pack: ExamPack, skill: Skill, score: float, source: str, rules: Bands
) -> BandPosterior:
    scale = 1.0 if pack.scale.type == "band" else (pack.max_score(skill) / 9) ** 2
    clipped = min(max(score, pack.min_score(skill)), pack.max_score(skill))
    return posterior.update(clipped, rules.observation_variance[source] * scale)


def summarise(
    posterior: BandPosterior, pack: ExamPack, skill: Skill, conversion: Conversion, rules: Bands, pack_id: PackId
) -> BandEstimate:
    low, high = posterior.interval(rules.display_interval)
    low, high = max(low, pack.min_score(skill)), min(high, pack.max_score(skill))
    mean = min(max(posterior.mean, pack.min_score(skill)), pack.max_score(skill))
    digits = 1 if pack.scale.type == "band" else 0  # IELTS bands to a tenth; TEF points are whole numbers
    return BandEstimate(
        pack=pack_id,
        skill=skill,
        mean=round(mean, digits),
        sd=max(posterior.sd, 1e-6),
        low80=round(low, digits),
        high80=round(high, digits),
        clb_nclc_low=conversion.to_level(skill, low),
        clb_nclc_mean=conversion.to_level(skill, mean),
        clb_nclc_high=conversion.to_level(skill, high),
        observations=posterior.observations,
    )


class IsotonicCalibrator:
    """Monotone map raw scorer output → human-rated band (pool-adjacent-violators). Identity until fitted."""

    def __init__(self) -> None:
        self._x: list[float] = []
        self._y: list[float] = []

    def fit(self, raw: list[float], human: list[float]) -> IsotonicCalibrator:
        pairs = sorted(zip(raw, human, strict=True))
        blocks: list[list[float]] = []  # [sum_y, count, max_x]
        for x, y in pairs:
            blocks.append([y, 1.0, x])
            while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
                y2, c2, x2 = blocks.pop()
                blocks[-1][0] += y2
                blocks[-1][1] += c2
                blocks[-1][2] = x2
        self._x = [b[2] for b in blocks]
        self._y = [b[0] / b[1] for b in blocks]
        return self

    def __call__(self, raw: float) -> float:
        if not self._x:
            return raw
        index = bisect_right(self._x, raw)
        if index == 0:
            return self._y[0]
        if index >= len(self._x):
            return self._y[-1]
        x0, x1, y0, y1 = self._x[index - 1], self._x[index], self._y[index - 1], self._y[index]
        return y0 + (y1 - y0) * (raw - x0) / (x1 - x0) if x1 != x0 else y1
