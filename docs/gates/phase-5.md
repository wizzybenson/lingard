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

- **Content:** each city has three districts with real locations and NPCs, Arrivals through Civic:
  Vieux-Port / Station Quarter (band 1+), Saint-Roch / Kingsway (band 6+: job centre, GP clinic, hardware shop) and
  Haute-Ville / Civic Quarter (band 8+: town hall consultation, library debate, local newspaper). The two cities are at
  parity (9 NPCs each). The SPEC doesn't name districts between Arrivals and Civic, so three is a content choice.
  More can be added as YAML only (see Phase 1b).
  Location art (`layer_art`) is referenced but no image files exist yet.
- The day planner used to fill every day from the first district's settings in content order, so a learner never
  reached Saint-Roch or Kingsway. It now rotates the unlocked settings by day. Covered by
  `test_day_planner_rotates_through_every_unlocked_district`.

## Phase 6 (real-world validation)

Phase 6 is the founder and friends sitting the real IELTS GT and TEF Canada. It records predicted vs actual and
retrains calibration. Nothing to report until then.
