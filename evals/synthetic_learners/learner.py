"""A simulated learner: per-node probability of correct use, improving with practice (faster after lessons)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class SyntheticLearner:
    name: str
    language: str
    true_band: float
    planted: dict[str, float]
    """Planted weaknesses: node key → initial probability of correct use (low)."""
    base_accuracy: float = 0.96
    learn_rate: float = 0.08
    lesson_boost: float = 0.25
    seed: int = 1
    node_bands: dict[str, int] = field(default_factory=dict)
    """Curriculum band per node; accuracy falls off above the learner's true band."""
    exposures: dict[str, int] = field(default_factory=dict)
    _rng: random.Random = field(init=False)
    _p: dict[str, float] = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)  # noqa: S311
        self._p = dict(self.planted)

    def p_correct(self, node_key: str) -> float:
        if node_key in self._p:
            return self._p[node_key]
        above = self.node_bands.get(node_key, 0) - self.true_band
        return self.base_accuracy if above <= 0 else max(0.35, self.base_accuracy - 0.25 * above)

    def within_band(self, node_key: str) -> bool:
        return self.node_bands.get(node_key, 0) <= self.true_band

    def attempt(self, node_key: str) -> bool:
        correct = self._rng.random() < self.p_correct(node_key)
        self.exposures[node_key] = self.exposures.get(node_key, 0) + 1
        if node_key in self._p:
            self._p[node_key] += self.learn_rate * (1 - self._p[node_key])
        return correct

    def take_lesson(self, node_key: str) -> None:
        if node_key in self._p:
            self._p[node_key] += self.lesson_boost * (1 - self._p[node_key])

    def utterance(self, targets: list[str], k: int) -> tuple[str, list[tuple[str, bool]]]:
        """An utterance attempting up to two targets, with machine-readable markers the oracle assessor reads."""
        chosen = [targets[(k + i) % len(targets)] for i in range(min(2, len(targets)))]
        attempts = [(t, self.attempt(t)) for t in dict.fromkeys(chosen)]
        words = " ".join(f"⟦{t}:{'ok' if ok else 'err'}⟧" for t, ok in attempts)
        return f"Alors {words} voilà.", attempts


def default_cohort() -> list[SyntheticLearner]:
    return [
        SyntheticLearner(
            "fr-conditional",
            "fr",
            6,
            {"fr.grammar.conditionnel_present": 0.2, "fr.func.complain_politely": 0.3},
            seed=1,
        ),
        SyntheticLearner(
            "fr-pronouns", "fr", 6, {"fr.grammar.pronoms_cod_coi": 0.2, "fr.grammar.futur_simple": 0.25}, seed=2
        ),
        SyntheticLearner(
            "en-perfect", "en", 6, {"en.grammar.first_conditional": 0.2, "en.func.complain_politely": 0.3}, seed=3
        ),
        SyntheticLearner(
            "en-relatives", "en", 6, {"en.grammar.relative_clauses": 0.2, "en.grammar.gerund_infinitive": 0.25}, seed=4
        ),
    ]
