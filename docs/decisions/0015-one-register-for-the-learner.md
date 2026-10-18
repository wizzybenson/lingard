# 0015: One register for the learner, and a language-coherence standard for the Scene Compiler

- **Date:** 2026-10-18
- **Status:** accepted (reversible)

## Context

In one planned day, scene 1's goal said « Renseignez-vous… » and scene 2's said « Renseigne-toi… ». The founder: "this
is a serious learning app", and "a good llm should know to check those vous/tu and all language coherence" things.
The compiler prompt (v2) never stated a register, so each scene, compiled on its own, picked one.

## Decision

- `content/languages/<language>.yaml: learner_address` states how on-screen goals address the learner. French uses
  « vous » or an infinitive, never « tu »; English uses "you". It's language content, not code (AGENTS rule 7).
- `prompts/scene_compiler/v3.md` adds a **Language** section: the register from content; one register across the
  scene (learner_goal, success_conditions and how the character addresses the learner); natural, grammatical
  language (agreement, tenses, prepositions, articles, accents); and a reread-and-fix pass before answering.
- No word-list check. A first version rejected goals containing « tu/te/toi… »; the founder preferred to rely on the
  model's own judgement, which covers coherence broadly rather than one pattern.

## Evidence

gpt-6.1-sol (medium) on Ernest's three briefs. All three goals came back formal: « Renseignez-vous sur l'ouverture d'un
compte… », « Faire noter la fissure et convenir d'un rendez-vous avant de vous installer », « Renseignez-vous sur le
menu… ». Each compile took 30–34 s, against 25–27 s with v2. Planning ahead (decision 0014) hides that from the tap.
