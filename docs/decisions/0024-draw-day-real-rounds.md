# 0024 — Draw Day uses real IRCC rounds, shipped as sourced content

Date: 2026-10-20 · Status: accepted (amends SPEC §18.3, which had an admin entering each draw by hand)

## Context

SPEC §18.3 sets Draw Day's cutoff "near recent real French-category cutoffs", entered by an admin. Nobody had entered
any, so the Passport goal was hidden, and the 150-coin `draw_invitation` reward was defined but never paid.

## Decision

- `content/crs/draws.yaml` holds the Express Entry rounds in the French-language proficiency category from the last
  12 months. It comes from IRCC's own rounds data (`source_url`, `data_url`, `as_of`).
  - On 2026-10-20 that was 14 rounds, from #376 (29 Oct 2025) to #450 (16 Oct 2026, cutoff 435).
  - Draw #450's cutoff is well above the year's usual 382–420. Draw Day follows the latest round, as the SPEC says.
- `python -m tools.content_cli.draws` rewrites the file from canada.ca (free, one download).
  `python -m lingard_api.cli seed` adds rounds the `draws` table lacks, matched by date. Each draw's `source_note`
  names the round, its source and the check date.
- The admin endpoint still works for anything entered by hand.
- `GET /v1/draws/latest` pays `draw_invitation` once per round (ledger key `draw:<id>`) when the learner's simulated
  CRS reaches the cutoff. A learner with no score yet is never invited.
- The Passport names the round's date, the cutoff and the reward. The text says "latest round", not "next draw":
  nobody can know the next cutoff.

## Both exams (amendment, same day)

A learner preparing only for IELTS would have been measured against French-language rounds, which they can't enter.
`draws.yaml` therefore lists categories, each tied to exam packs:

- `french` (round names containing "French") for `tef_canada`;
- `cec` (Canadian Experience Class) for `ielts_gt`.

A learner follows the first category that matches one of their exams, so French-language rounds win when they
prepare for both. On 2026-10-20 the latest CEC round was 15 Oct 2026, cutoff 519.

`draws.category` was added by migration 0005; existing rows are French-language. The refresh tool keeps the
categories and rewrites their rounds. The Passport names the category in the learner's interface language.

## Evidence

- `tools/content_cli/tests/test_draws.py`:
  - only the last year's French-language rounds are kept, newest first;
  - the shipped file carries its source.
- `tools/content_cli/tests/test_draws.py`: a learner's exams choose the category.
- `services/api/tests/test_phase2_to_5_api.py`:
  - an IELTS-only learner gets the CEC round; with TEF as well, the French-language round;
  - seeding is idempotent;
  - the latest cutoff is served with its source;
  - there is no invitation without a score;
  - the reward is paid exactly once.
- Simulator: the Passport shows "Latest French-language round (October 16): cutoff 435 points…".
