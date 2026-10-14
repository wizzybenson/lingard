"""Turn phoneme and prosody measurements into the two dials (SPEC §13): intelligibility first, then accent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lingard_pronunciation.gop import PhonemeScore

INTELLIGIBILITY_CRITICAL = 0.6
"""Functional load above which a mispronounced target is passed to the actor as 'you didn't understand this'."""
WEAK_SCORE = 50.0


@dataclass(frozen=True)
class PronTarget:
    node_key: str
    phonemes: tuple[str, ...]
    functional_load: float
    l1_difficulty: dict[str, float]

    @classmethod
    def from_node(cls, key: str, payload: dict[str, Any]) -> PronTarget:
        return cls(
            key,
            tuple(payload.get("phonemes", [])),
            float(payload.get("functional_load", 0.5)),
            dict(payload.get("l1_difficulty", {})),
        )


@dataclass
class PronReport:
    intelligibility: float
    """0–100, weighted by functional load: what matters for being understood."""
    accent_proximity: float
    """0–100, phoneme accuracy blended with intonation similarity to the golden self."""
    node_scores: dict[str, float] = field(default_factory=dict)
    critical: list[str] = field(default_factory=list)
    heatmap: list[dict[str, Any]] = field(default_factory=list)


def report(scores: list[PhonemeScore], targets: list[PronTarget], intonation: float | None = None) -> PronReport:
    by_phoneme: dict[str, list[float]] = {}
    for s in scores:
        by_phoneme.setdefault(s.phoneme, []).append(s.score)
    loads = {p: t.functional_load for t in targets for p in t.phonemes}
    weighted = [(sum(v) / len(v), loads.get(p, 0.3)) for p, v in by_phoneme.items()]
    total_weight = sum(w for _, w in weighted) or 1.0
    intelligibility = sum(s * w for s, w in weighted) / total_weight if weighted else 0.0
    phoneme_accuracy = sum(s.score for s in scores) / len(scores) if scores else 0.0
    accent = phoneme_accuracy if intonation is None else 0.7 * phoneme_accuracy + 0.3 * intonation
    node_scores: dict[str, float] = {}
    critical: list[str] = []
    for target in targets:
        values = [v for p in target.phonemes for v in by_phoneme.get(p, [])]
        if not values:
            continue
        node_scores[target.node_key] = sum(values) / len(values)
        if node_scores[target.node_key] < WEAK_SCORE and target.functional_load > INTELLIGIBILITY_CRITICAL:
            critical.append(target.node_key)
    heatmap = [{"phoneme": s.phoneme, "score": round(s.score, 1), "heard_as": s.likely_substitute} for s in scores]
    return PronReport(intelligibility, accent, node_scores, critical, heatmap)


def diagnostic_priority(targets: list[PronTarget], l1: str) -> list[PronTarget]:
    """Order for the accent diagnostic: likely L1 difficulty × functional load (generic prior when L1 unknown)."""
    return sorted(
        targets, key=lambda t: -(t.l1_difficulty.get(l1, t.l1_difficulty.get("generic", 0.5)) * t.functional_load)
    )
