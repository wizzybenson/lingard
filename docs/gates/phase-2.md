# Phase 2 gate: learning loop and placement

**Verdict: PASS offline.** The pedagogy loop runs on the real graphs. The LLM is replaced by an oracle that reads each
synthetic learner's planted errors. So this measures the loop (detection, ticketing, scheduling, closure), **not**
the LLM's judgement, which is Phase 3's correction-precision gate.

| Gate (SPEC §25) | Result |
| --- | --- |
| Synthetic learners in both languages: planted weaknesses detected | **40 of 40 detected** (100%), mean detection on day 0.38 |
| … and closed | **40 of 40 closed** (100%) within 28 simulated days |
| Placement within ±1 band (both languages) | **30 of 30** within ±1 (mean abs error 0.5) |

## Synthetic learners (`evals/suites/synthetic_learners.py`)

- Cohort: 4 learners at band 6, 2 French (`fr-conditional`, `fr-pronouns`) and 2 English (`en-perfect`,
  `en-relatives`), each with 2 planted weaknesses (p(correct) 0.2–0.3).
- 28 simulated days each, through `day_planner` → 3 scenes × 6 turns → `turn_assessment` → `night_consolidation` →
  `lesson_builder`.
- **5 replicates per learner** (20 runs), varying only the FSRS interval fuzz. Every gate must hold in every
  replicate, so a pass can't come from one lucky schedule. Runs are reproducible: seeded ids and a seeded global
  generator.
- Noise control: 11 noise tickets opened across the 20 runs (real one-off slips on in-band material). **None stayed
  open 7 days after their latest (re)opening.** Gate: `noise_tickets_stale_7d == 0`.
- 169 targeted lessons were built and taken.

### Fixes made while closing this gate

- Ticket ageing (`director.ticket_ageing_per_day: 0.15`): low-priority tickets were being starved.
- Errors on nodes more than `tickets.max_bands_above: 1` above the learner's band count as evidence but don't open
  tickets (stretch material is exposure, not a weakness). Test: `test_errors_far_above_band_do_not_open_tickets`.
- Harness determinism: FSRS fuzzing uses the global `random`, and random UUIDs had made the result vary run to run.
- The day planner's ticket-share warning now accounts for supply (it used to fire whenever there were few tickets).

## Placement (`evals/suites/placement_accuracy.py`)

- 30 synthetic learners at known bands across both languages, through the real `placement` graph (quick path).
- 30 of 30 placed within ±1 band. Mean absolute error 0.5.
- The SPEC's second data source ("founder/friends vs later mocks") needs real people. Track it in Phase 5–6.

## Reproduce

```sh
uv run python -m evals.run --suite synthetic_learners --suite placement_accuracy
```
