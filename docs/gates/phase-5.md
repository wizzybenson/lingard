# Phase 5 gate: full city and game (v1)

**Verdict: NOT PASSED.** The gate is about people using the product. Engineering can't self-verify it.

| Gate (SPEC §25) | Status |
| --- | --- |
| Founder plays 2 weeks | Not started: needs provider keys and hosting (founder input #5) |
| D7 retention among friends | Not started |
| Cost ≤ 1 USD per active hour, measured | Not measured: cost logging is in place (LLM router usage + telemetry), but there's no real traffic |

## What exists

- Economy (`packages/economy`): coins, stars, Draw Day, friends league, streaks and the Landing Day unlock, with
  tests. Also a simulated CRS whose tables were verified against IRCC.
- Glance mode (`/v1/glance`): quick review quests from FSRS-due items.
- Mock-based placement (`exam_hall` feeds band posteriors).
- World API (`GET /v1/world/{city}`) with band-gated districts. The app renders it as a 2.5D map.

## Known gaps

- **Content:** only the first district of each city has real locations and NPCs. Later districts (through Civic) are
  placeholders. That's content work, not code (see Phase 1b).
- Both cities' first districts are at parity (3 NPCs each). Parity beyond that depends on the content above.

## Phase 6 (real-world validation)

Phase 6 is the founder and friends sitting the real IELTS GT and TEF Canada. It records predicted vs actual and
retrains calibration. Nothing to report until then.
