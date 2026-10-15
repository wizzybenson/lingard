# 0012: Contract Guard claim check, scenes rich enough that NPCs need not invent

- **Date:** 2026-10-15
- **Status:** accepted (reversible; chosen by the founder from the options in docs/gates/phase-1.md: "do 1 and 2")

## Context

The live `contract_adherence` run with Haiku NPCs (decision 0011) had fact violations in 143 of 446 NPC lines (119
material, mostly invented requirements and procedures). Two causes:

1. SPEC §10 gives the Contract Guard "rules + small classifier"; only the rules existed. They block new numbers, names
   and dates, but not "the lease says you must repaint" or "you need the blue form".
2. Scene contracts carried 3–6 facts for an 8-turn service conversation, so the NPC filled the gaps.

## Decision

### Claim check (the "small classifier")

- `lingard_live.claims.LlmClaimChecker`: each NPC sentence that passes the rules is checked against everything the NPC
  may state (`GuardContext.grounding`: approved facts, persona facts, what is written in the place, who and where it
  is, from `prompts/npc_grounding`) plus what the learner and the NPC already said. The model answers `OK` or
  `FIX: <sentence without the unsupported claim>` (`prompts/claim_check`). A repair that passes the rules and is a
  complete sentence is spoken instead (verdict `rewrite`); otherwise the sentence is withheld (`block`). A check that
  fails or misses its deadline withholds the sentence. If a whole reply is withheld the NPC says an in-character "I'd
  have to check" line (`LanguageConfig.unsure`).
- It runs on a new `guard` model tier (`LLM_GUARD_MODELS`, default `claude-haiku-5-5`), not a local model: no local
  classifier for invented procedures exists to reuse, training one needs labelled data this check now produces, and a
  hosted call can be swapped for a local one behind the same `ClaimChecker` protocol later.
- **Latency.** SPEC §10 budgets the Guard at ≤ 50 ms per sentence; a hosted check takes about a second, so it is kept
  off that budget:
  - the rules still screen every sentence first (a rule-blocked sentence never reaches TTS);
  - sentences that can only recombine grounded words skip the check (`CLAIM_FREE_WORDS`: up to 6 words, or a question,
    with every word already known);
  - the check runs while earlier sentences play, and the screened sentence's audio is synthesised meanwhile but never
    played before the check clears it;
  - if the first sentence is still held `FILLER_AFTER_MS` (150 ms) after it is ready, the NPC says a hesitation from
    `LanguageConfig.fillers` ("Hmm…", "Alors…"), as people do while thinking; the worker pre-synthesises these
    stock lines in the NPC's voice while the opening line plays, so the cached TTS plays them at once;
  - `npc_actor` v3 asks for the brief opening reaction people naturally give, which usually needs no check.
- All thresholds are settings (`CLAIM_CHECK`, `CLAIM_CHECK_DEADLINE_S`, `CLAIM_CHECK_CONTEXT_LINES`,
  `CLAIM_FREE_WORDS`, `FILLER_AFTER_MS`); language-specific lines live in `content/languages/*.yaml`.

### Rich scenes

- `prompts/scene_compiler` v2 asks for facts covering everything the goal's conversation needs: procedure steps,
  requirements, prices, times, availability, where things are, what happens next, the character's position and the
  limits of what it knows. It also sees what is written in the place (signs, objects).
- The number of facts is configuration (`scenes.approved_facts_min/max` in `config/pedagogy.yaml`, 10–18) and
  `validate_contract(facts_range=…)` reports `thin_facts`, which the compiler feeds back and retries.
- The live eval now compiles its 18 scene briefs with the real compiler instead of using hand-written facts, so it
  measures what production plays.
- Signs and objects in a location (`Hotspot.text`) are now part of what the actor knows and the Guard allows.

### Measuring

- `fact_judge` v3 grades each violation material (could mislead someone acting in the world) or colour (harmless
  scene-setting). The gate counts material violations; all violations are still reported.
- The live eval reports claim-check rate, repairs, withheld sentences, check latency, how often the first sentence
  needed a check and how often the hesitation played. The provider probe measures the claim check; the latency bench
  runs it.

## Results (2026-10-15, docs/gates/phase-1.md)

- Material fact violations over 50 live scenes: 119 → 32 lines (all violations 143 → 39); targets elicited 96%.
- `guard` tier runs with thinking off: with thinking on, Haiku used its token budget reasoning and returned no answer,
  so 15% of sentences were withheld by accident.
- First-audio cost of the check: none measurable with the 150 ms hesitation and pre-warmed stock lines; the
  hesitation plays on about two thirds of replies.
- Not yet at the gate (0 material violations). Next steps are listed in the gate file.
