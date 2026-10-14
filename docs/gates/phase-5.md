# Phase 5 gate: full city and game (v1)

**Verdict: NOT PASSED.** The gate is about people using the product. Engineering can't self-verify it.

| Gate (SPEC §25) | Status |
| --- | --- |
| Founder plays 2 weeks | Not started: needs provider keys and hosting (founder input #5) |
| D7 retention among friends | Not started |
| Cost ≤ 1 USD per active hour, measured | **Projected 0.63 USD/hour** (offline `cost` eval, default stack Anthropic + Deepgram + ElevenLabs); not yet measured on real traffic |

## What exists

- Economy (`packages/economy`): coins, stars, Draw Day, friends league, streaks and the Landing Day unlock, with
  tests. Also a simulated CRS whose tables were verified against IRCC.
- Glance mode (`/v1/glance`): quick review quests from FSRS-due items.
- Mock-based placement (`exam_hall` feeds band posteriors).
- World API (`GET /v1/world/{city}`) with band-gated districts. The app renders it as a 2.5D map.

## Cost (`evals/suites/cost.py`, `config/cost_model.yaml`)

- Prompt sizes are measured by running the real graphs (a synthetic learner's days) and the NPC actor prompt; prices
  are first-party rates verified 2026-10-14 (each with `source_url`). Activity per hour (5 scenes × 12 learner turns,
  5 s of speech per turn, 140 characters of NPC speech per turn) and output-token floors are labelled assumptions.
- Default stack: 0.63 USD per active hour. TTS is the largest share (ElevenLabs Flash 0.34), then mid-tier
  assessment (0.17) and frontier scene compilation (0.10). LLM alone: Anthropic 0.27, OpenAI 0.43, Google 0.13.
- Improvement made: `utterance_assessor@v2` moved the turn below a `=== per call ===` marker so its 2.5k-token rubric and
  node list is prompt-cached. Mid-tier cost went from 0.45 to 0.17 USD/hour (total 0.92 → 0.63).
- Cheaper options if needed: OpenAI TTS (≈0.14 instead of 0.34), or Google models for the LLM tiers.

## Known gaps

- **Content:** each city has three districts with real locations and NPCs, Arrivals through Civic:
  Vieux-Port / Station Quarter (band 1+), Saint-Roch / Kingsway (band 6+: job centre, GP clinic, hardware shop) and
  Haute-Ville / Civic Quarter (band 8+: town hall consultation, library debate, local newspaper). The two cities are at
  parity (9 NPCs each). The SPEC doesn't name districts between Arrivals and Civic, so three is a content choice.
  More can be added as YAML only (see Phase 1b).
- **Art:** every location has original two-layer SVG artwork (`tools/content_cli/art.py`, served at `/v1/art`, drawn in
  the city screen's location card). It is flat vector illustration generated from templates, not commissioned art.
- The day planner used to fill every day from the first district's settings in content order, so a learner never
  reached Saint-Roch or Kingsway. It now rotates the unlocked settings by day. Covered by
  `test_day_planner_rotates_through_every_unlocked_district`.

## Phase 6 (real-world validation)

Phase 6 is the founder and friends sitting the real IELTS GT and TEF Canada. It records predicted vs actual and
retrains calibration. Nothing to report until then.
