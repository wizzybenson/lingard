"""``band_calibration`` and ``correction_precision`` (SPEC §20, Phase 3 gate).

Both need real model calls (live mode). Offline mode checks dataset integrity and reports how much data exists.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, get_args

from evals.framework import ROOT, Gate, Mode, SuiteResult, suite
from lingard_contracts.common import Language
from lingard_llm.config import any_llm_configured

MIN_CALIBRATION_SAMPLES = 30
MIN_GOLDEN_ITEMS = 300


def _rows(folder: Path, pattern: str) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(folder.glob(pattern)):
        rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows


def quadratic_weighted_kappa(a: list[int], b: list[int], low: int, high: int) -> float:
    n = high - low + 1
    observed = [[0.0] * n for _ in range(n)]
    for x, y in zip(a, b, strict=True):
        observed[x - low][y - low] += 1
    total = len(a)
    hist_a = [sum(row) for row in observed]
    hist_b = [sum(observed[i][j] for i in range(n)) for j in range(n)]
    num = den = 0.0
    for i in range(n):
        for j in range(n):
            weight = (i - j) ** 2 / (n - 1) ** 2
            expected = hist_a[i] * hist_b[j] / total
            num += weight * observed[i][j]
            den += weight * expected
    return 1 - num / den if den else 1.0


@suite(
    "band_calibration",
    watches=(
        "services/graphs/src/lingard_graphs/agents/writing.py",
        "prompts/writing_examiner/",
        "prompts/speaking_examiner/",
        "content/packs/",
    ),
)
async def band_calibration(mode: Mode) -> SuiteResult:
    rows = _rows(ROOT / "evals/datasets/band_calibration", "*.jsonl")
    gates = [Gate("ielts_mae", "<=", 0.5), Gate("tef_nclc_mae", "<=", 1.0)]
    counts = {
        "ielts_samples": sum(r["pack"] == "ielts_gt" for r in rows),
        "tef_samples": sum(r["pack"] == "tef_canada" for r in rows),
    }
    if mode == "offline" or not any_llm_configured():
        bad = [r.get("id") for r in rows if len(r.get("human_scores", [])) < 2 or not r.get("consent")]
        notes = [
            f"{counts} human-rated samples; need ≥ {MIN_CALIBRATION_SAMPLES} per pack and skill (founder input #3)"
        ]
        if bad:
            notes.append(f"invalid rows (need ≥2 raters and consent): {bad}")
        return SuiteResult("band_calibration", mode, {k: float(v) for k, v in counts.items()}, [], notes=notes)
    from evals.live_calibration import score_samples

    predicted, human, packs = await score_samples(rows)
    metrics: dict[str, float] = dict(counts)
    for pack_id, key in (("ielts_gt", "ielts_mae"), ("tef_canada", "tef_nclc_mae")):
        pairs = [(p, h) for p, h, k in zip(predicted, human, packs, strict=True) if k == pack_id]
        if len(pairs) >= MIN_CALIBRATION_SAMPLES:
            metrics[key] = round(statistics.fmean(abs(p - h) for p, h in pairs), 3)
            scale = 2 if pack_id == "ielts_gt" else 1
            metrics[f"{key.split('_')[0]}_qwk"] = round(
                quadratic_weighted_kappa(
                    [round(p * scale) for p, _ in pairs],
                    [round(h * scale) for _, h in pairs],
                    0,
                    9 * scale if scale == 2 else 12,
                ),
                3,
            )
    return SuiteResult("band_calibration", mode, metrics, gates)


@suite(
    "correction_precision",
    watches=(
        "services/graphs/src/lingard_graphs/agents/assessor.py",
        "prompts/utterance_assessor/",
        "prompts/correction_check/",
    ),
)
async def correction_precision(mode: Mode) -> SuiteResult:
    folder = ROOT / "evals/datasets/correction_golden"
    by_language: dict[Language, list[dict[str, Any]]] = {
        lang: _rows(folder, f"{lang}.*.jsonl") for lang in get_args(Language)
    }
    metrics: dict[str, float] = {f"{lang}_items": float(len(rows)) for lang, rows in by_language.items()}
    gates = [Gate("fr_precision", ">=", 0.95), Gate("en_precision", ">=", 0.95)]
    # Rows a machine reviewer judged ambiguous stay in the files for a human to look at, but are not scored.
    by_language = {lang: [r for r in rows if not r.get("excluded")] for lang, rows in by_language.items()}
    unreviewed = {lang: sum(r.get("reviewed") is False for r in rows) for lang, rows in by_language.items()}
    machine = {lang: sum("machine_review" in r for r in rows) for lang, rows in by_language.items()}
    metrics.update({f"{lang}_items": float(len(rows)) for lang, rows in by_language.items()})
    metrics.update({f"{lang}_machine_checked": float(n) for lang, n in machine.items()})
    metrics.update({f"{lang}_unreviewed": float(n) for lang, n in unreviewed.items()})
    notes = [
        f"golden items: { {k: len(v) for k, v in by_language.items()} } (target ≥ {MIN_GOLDEN_ITEMS} each)",
        f"drafted items awaiting native review: {unreviewed}",
    ]
    if mode == "offline" or not any_llm_configured():
        positives = {lang: sum(r["has_error"] for r in rows) for lang, rows in by_language.items()}
        metrics.update({f"{lang}_positives": float(n) for lang, n in positives.items()})
        return SuiteResult("correction_precision", mode, metrics, [], notes=notes)
    from evals.live_calibration import correction_run

    for language, rows in by_language.items():
        shown, correct_shown = await correction_run(language, rows)
        metrics[f"{language}_shown"] = float(shown)
        metrics[f"{language}_precision"] = round(correct_shown / shown, 4) if shown else 1.0
    return SuiteResult("correction_precision", mode, metrics, gates, notes=notes)
