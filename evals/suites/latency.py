"""``latency`` (SPEC §20, §22): end-of-turn → first NPC audio p50 ≤ 800 ms / p95 ≤ 1,300 ms; Guard ≤ 50 ms.

Offline mode drives the real loop with provider latencies drawn from ``tools/voicebench/profiles.yaml`` so that
Lingard's own overhead is measured; live mode uses the configured providers (keys required).
"""

from __future__ import annotations

from evals.framework import Gate, Mode, SuiteResult, suite


@suite("latency", watches=("services/live/", "tools/voicebench/", "config/llm.yaml"))
async def run(mode: Mode) -> SuiteResult:
    from tools.voicebench.bench import run_bench

    report = await run_bench(mode=mode, turns=60)
    return SuiteResult(
        suite="latency",
        mode=mode,
        metrics=report.metrics(),
        gates=[
            Gate("first_audio_p50_ms", "<=", 800),
            Gate("first_audio_p95_ms", "<=", 1300),
            Gate("guard_p99_ms", "<=", 50),
        ],
        notes=report.notes,
    )
