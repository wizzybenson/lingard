# Phase 3 gate: Exam Hall and writing

**Verdict: NOT PASSED. Blocked on human data and provider keys.** The machinery is built and tested. Neither
accuracy number can be honestly measured yet.

| Gate (SPEC §25) | Status | Why |
| --- | --- | --- |
| Mean abs error ≤ 0.5 IELTS band, ≤ 1 NCLC | **INCOMPLETE** | 0 human-rated samples. Needs ≥ 30 per pack and skill from certified raters (founder input #3) |
| Correction precision ≥ 95% | **INCOMPLETE** | Golden set has 159 FR and 118 EN items (target ≥ 300 each), and scoring it needs an LLM key |

## What exists

- Both packs: `content/packs/ielts_gt`, `content/packs/tef_canada` (sections, rubrics, timings, sources dated).
- `exam_hall` graph: timed sections → score → aggregate → CLB/NCLC conversion → persist. Conversion tables are in
  `content/crs/`, verified against IRCC on 2026-10-14.
- `writing_review` graph: 3 independent scorings → aggregate → rewrite → error tags → evidence.
- Rasch adaptive engine and item bank (`packages/exam_packs`), and band posteriors.
- The `band_calibration` suite computes MAE and QWK once samples exist: drop rated samples into
  `evals/datasets/band_calibration/`.
- The `correction_precision` suite (offline counts items; `--live` scores with the configured `frontier` model).
  Golden set: `evals/datasets/correction_golden/` (FR 45 positives / 114 clean; EN 32 / 86).

## To close the gate

1. Founder input #3: 2–3 certified raters (or a budget) to rate ≥ 30 responses per pack and skill.
2. Grow the correction golden set to ≥ 300 per language. Each item must be reviewed by a native speaker.
3. Set `ANTHROPIC_API_KEY`, then run `uv run python -m evals.run --live --suite correction_precision --suite band_calibration`.
