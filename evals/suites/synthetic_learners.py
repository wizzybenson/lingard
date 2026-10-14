"""``synthetic_learners`` (SPEC §20, Phase 2 gate): planted weaknesses are detected, ticketed and closed.

Offline mode runs the real day-planner, turn-assessment, night-consolidation and lesson graphs with an oracle
assessor that reads the simulated learner's planted errors; it measures the pedagogy loop, not LLM judgement.
"""

from __future__ import annotations

from evals.framework import Gate, Mode, SuiteResult, suite
from evals.synthetic_learners.harness import build_deps, live_days
from evals.synthetic_learners.learner import default_cohort

DAYS = 28
REPLICATES = 5
"""Each learner is re-run under different FSRS fuzz draws; gates must hold in every replicate."""


@suite("synthetic_learners", watches=("services/graphs/", "config/pedagogy.yaml", "content/curriculum/"))
async def run(mode: Mode) -> SuiteResult:
    if mode == "live":
        return SuiteResult(
            "synthetic_learners", mode, {}, [], notes=["live mode: LLM-simulated learners, not built yet"]
        )
    outcomes = []
    for replicate in range(REPLICATES):
        for learner in default_cohort():
            outcomes.append(await live_days(learner, DAYS, await build_deps(), replicate))
    planted = sum(len(o.planted) for o in outcomes)
    detected = sum(1 for o in outcomes for d in o.detected_day.values() if d is not None)
    closed = sum(1 for o in outcomes for c in o.closed_day.values() if c is not None)
    false = sum(len(o.false_tickets) for o in outcomes)
    false_open = sum(len(o.false_open_at_end) for o in outcomes)
    stale = sum(len(o.stale_noise) for o in outcomes)
    detect_days = [d for o in outcomes for d in o.detected_day.values() if d is not None]
    return SuiteResult(
        suite="synthetic_learners",
        mode=mode,
        metrics={
            "learners": len(outcomes) // REPLICATES,
            "replicates": REPLICATES,
            "days": DAYS,
            "planted": planted,
            "detected_rate": round(detected / planted, 3),
            "closed_rate": round(closed / planted, 3),
            "noise_tickets_opened": false,
            "noise_tickets_open_at_end": false_open,
            "noise_tickets_stale_7d": stale,
            "mean_detection_day": round(sum(detect_days) / max(len(detect_days), 1), 2),
            "lessons_built": sum(len(o.lessons) for o in outcomes),
        },
        gates=[
            Gate("detected_rate", "==", 1.0),
            Gate("closed_rate", ">=", 0.875),
            Gate("noise_tickets_stale_7d", "==", 0),
        ],
        samples=[
            {
                "learner": o.name,
                "replicate": i // (len(outcomes) // REPLICATES),
                "detected": o.detected_day,
                "closed": o.closed_day,
                "noise": sorted(o.false_tickets),
                "noise_open": sorted(o.false_open_at_end),
                "stale": sorted(o.stale_noise),
                "opened_day": o.noise_opened_day,
                "lessons": o.lessons,
            }
            for i, o in enumerate(outcomes)
        ],
    )
