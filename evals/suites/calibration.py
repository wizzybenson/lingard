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


def spearman(a: list[float], b: list[float]) -> float:
    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=values.__getitem__)
        result = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                result[order[k]] = (i + j) / 2
            i = j + 1
        return result

    return statistics.correlation(ranks(a), ranks(b)) if len(a) > 2 else 0.0


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
    everything = _rows(ROOT / "evals/datasets/band_calibration", "*.jsonl")
    # Synthetic samples (written to a target level, not human-rated) never count toward the gate; in live mode they
    # only sanity-check that the examiner ranks weak below strong and lands near the intended level.
    synthetic = [r for r in everything if r.get("origin") == "synthetic"]
    rows = [r for r in everything if r.get("origin") != "synthetic"]
    gates = [Gate("ielts_mae", "<=", 0.5), Gate("tef_nclc_mae", "<=", 1.0)]
    counts = {
        "ielts_samples": sum(r["pack"] == "ielts_gt" for r in rows),
        "tef_samples": sum(r["pack"] == "tef_canada" for r in rows),
        "synthetic_samples": len(synthetic),
    }
    if mode == "offline" or not any_llm_configured():
        bad = [r.get("id") for r in rows if len(r.get("human_scores", [])) < 2 or not r.get("consent")]
        notes = [
            f"human-rated: {counts['ielts_samples']} IELTS, {counts['tef_samples']} TEF"
            f" (need ≥ {MIN_CALIBRATION_SAMPLES} per pack and skill);"
            f" synthetic sanity samples: {counts['synthetic_samples']}"
        ]
        if bad:
            notes.append(f"invalid rows (need ≥2 raters and consent): {bad}")
        return SuiteResult("band_calibration", mode, {k: float(v) for k, v in counts.items()}, [], notes=notes)
    from evals.live_calibration import score_samples

    metrics: dict[str, float] = dict(counts)
    if synthetic:
        guessed, target, _ = await score_samples(synthetic)
        metrics["synthetic_mae"] = round(statistics.fmean(abs(p - t) for p, t in zip(guessed, target, strict=True)), 3)
        metrics["synthetic_rank_corr"] = round(spearman(guessed, target), 3)
    predicted, human, packs = await score_samples(rows)
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
