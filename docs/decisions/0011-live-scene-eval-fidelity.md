# 0011: The live scene eval runs the real turn path; NPC actor v2 and fact judge v2

- **Date:** 2026-10-15
- **Status:** accepted (reversible; fixes found while working on the targets-elicited gate)

## Context

The first live `contract_adherence` runs (OpenAI then Haiku NPCs) elicited 34–48% of targets against a gate of 85%.
Tracing single scenes showed the eval harness, not the NPC, was the main cause, plus one real production bug.

## Findings and fixes

1. **Production bug: fluent turns dropped.** `lingard_live.turn_gate.is_low_entropy` rejected any text whose distinct
   characters were ≤ 20% of its length. Every language reuses a ~30-letter alphabet, so every turn over ~130
   characters was ignored as noise: the more fluent the learner, the more turns vanished. It now flags ≤ 3 distinct
   characters ("hahaha"). Tests cover long French and English turns and real noise.
2. **Eval: implausible audio.** Every simulated learner turn was 2 s long whatever its length, so the gate dropped
   long turns as impossibly fast speech. Turns now last 450 ms per word (`LEARNER_MS_PER_WORD`); a test keeps
   simulated turns passing the gate.
3. **Eval: no steering.** Assessment ran only after the scene, so `turn_assessment`'s steering hints never reached
   the NPC. It now runs after each learner turn and the loop takes hints from the same store, as in production.
4. **Eval: placeholder tactics.** Every tactic read "Steer the talk so the newcomer naturally needs <target>". The
   scene compiler is told to write a concrete thing the character does or asks; `evals/datasets/scenes.yaml` now
   has one such tactic per required grammar target.
5. **Eval judge grounding.** The fact judge now gets what the actor gets: the NPC's name, role and background, the
   place and its description, the learner's name and goal. Before, an NPC introducing itself counted as a violation.
6. **`prompts/fact_judge/v2`** names what counts as a new world fact (names, numbers, places and layout, the
   character's history, rules and procedures of this place, past events) and what does not (saying they don't know,
   suggesting the learner check, the character's own next action, opinions, general knowledge).
7. **`prompts/npc_actor/v2`** lists what the NPC does not know (layout, hours, stock, procedures, other names, its own
   past beyond the background) and tells it to say so and suggest checking, or turn it back with a question.

## Evidence

| Run (50 scenes unless noted) | NPC | Lines | Fact flags | Targets elicited |
| --- | --- | --- | --- | --- |
| Old harness, judge v1 | gpt-6-luna | 180 | 11 (6%) | 48% |
| Old harness, judge v1 | claude-haiku-5-5 | 174 | 28 (16%) | 34% |
| Fixed harness, actor v1, judge v1 | claude-haiku-5-5 | 448 | 251 (56%); judge v2 confirms 195 (44%) | **100%** |
| A/B, 10 scenes, judge v2, actor v1 | claude-haiku-5-5 | 90 | 37 (41%) | 10/10 |
| A/B, 10 scenes, judge v2, actor v2 | claude-haiku-5-5 | 90 | 30 (33%) | 10/10 |
| **Final**, judge v2 with full grounding, actor v2 | claude-haiku-5-5 | 446 | 143 (32%; 119 material) | **100%** |

The old harness hid most of the conversation (few NPC lines), which is why its fact numbers looked better. The A/B
difference (37 vs 30) is directional only at this sample size. Final run: see `docs/gates/phase-1.md`.

## Reverting

Pin `npc_actor` or `fact_judge` to version 1 in the prompt registry. The harness fixes and the gate fix should stay.
