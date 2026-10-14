"""Bayesian knowledge tracing with evidence weighted by context difficulty and assessor confidence (SPEC §14)."""

from __future__ import annotations

from dataclasses import dataclass, field

from lingard_graphs.pedagogy.config import Bkt


@dataclass
class MasteryState:
    node_key: str
    p_mastery: float
    evidence_count: int = 0
    contexts: list[str] = field(default_factory=list)


def bkt_update(p: float, correct: bool, params: Bkt, weight: float = 1.0) -> float:
    """One BKT step. ``weight`` ∈ (0, 1] blends the posterior with the prior for weak evidence."""
    if correct:
        evidence = p * (1 - params.p_slip) / (p * (1 - params.p_slip) + (1 - p) * params.p_guess)
    else:
        evidence = p * params.p_slip / (p * params.p_slip + (1 - p) * (1 - params.p_guess))
    posterior = evidence + (1 - evidence) * params.p_transit
    weighted = p + max(0.0, min(weight, 1.0)) * (posterior - p)
    return min(max(weighted, 0.001), 0.999)


def evidence_weight(assessor_confidence: float, context_difficulty: float) -> float:
    """Confident evidence in harder contexts counts more; difficulty ∈ [0, 1] (calm scene → mock exam)."""
    return max(0.05, min(1.0, assessor_confidence * (0.6 + 0.4 * context_difficulty)))


def apply_evidence(
    state: MasteryState, correct: bool, *, confidence: float, difficulty: float, context: str, params: Bkt
) -> MasteryState:
    state.p_mastery = bkt_update(state.p_mastery, correct, params, evidence_weight(confidence, difficulty))
    state.evidence_count += 1
    if correct and context not in state.contexts:
        state.contexts.append(context)
    return state
