# 0025: Lessons never block the day; they teach before they test

- **Date:** 2026-10-21
- **Status:** accepted (reversible). Amends 0018 ("Today puts `key_points` before the story day") and the "grammar
  targets stay hidden" rule of the scene prep.

## Context

The founder: lessons looked compulsory, with no way to start a day and move around the city without them. Lessons are
a must but must not be a blocker: they should be disclosed progressively inside missions and quests, with the whole
library there for anyone who goes looking. Lessons also asked the learner to try exercises before teaching the rule (a
one-line rule, then games), and a conjugation lesson showed no full table of the verb.

## Decision

**Nothing gates the day.** `/v1/today` returns `set_goal`, `placement` or `story`; `key_points` and `lesson` are gone
as steps. The next unlearned rule (`next_key_point`) is an optional chip under "Begin day", beside reviews and waiting
lessons.

**Lessons come to the learner inside the journey.**
- The mission brief teaches the rule the scene practises (`/v1/scenes/{id}/prep` now returns one unlearned grammar
  target first, then words and phrases). It is a collapsed row that opens in place (`/v1/key-points/{node}/card`: rule,
  steps, models, the mistake to avoid; no lesson created), with "Full lesson" and "Got it". "Start talking" stays
  pinned. Only the rule is shown: the other targets stay hidden.
- After a scene, confirmed mistakes still offer their lessons; places on the map still offer theirs.
- A rule counts as learned through use, too: BKT mastery ≥ `bkt.mastered` (0.85, about three confident correct uses)
  marks the key point done (`learned_in_use`), lesson or not.
- The School shows every level (`?every_level=true`): the learner's level, then lessons from mistakes, then each level
  above folded to one line, then the basics.

**Lessons teach before they test.**
- Every grammar point has authored step-by-step teaching (`content/curriculum/<lang>/teach.yaml`, merged into
  `payload.lesson.teach` at load; fr 54, en 51; a test enforces ≥ 2 steps, valid verb tables, closed highlights).
  A step is one idea plus a verb's table, a pattern table or examples; `**x**` highlights. Opened lessons always get
  the node's current teaching.
- The lesson screen has two parts: **1 Learn** (rule, steps, models, words, watch-out) and **2 Practise**; the games
  open on "I'm ready" (a lesson already started opens with its games).
- Any verb in teaching opens its tables as a native form sheet (`/verb/[language]/[key]`): a tab per tense, easiest
  first, opening on the rule's tense; stem and ending split with the ending coloured; forms off the pattern marked;
  each form playable (`/v1/conjugations/{lang}/{verb}/say`). In explanations only highlighted words link; in examples
  every verb does.
- Verb data: French regular -er/-ir verbs are derived from a `regular` list (spelling changes like mangeons and
  commençons are handled); English gains regular verbs and the present simple, present perfect and past perfect.
  Words that are far more often something else stay plain (`not_tappable`: été, passé…; English regular bare forms,
  which are as often nouns: an answer, a book).

## Evidence

`services/api/tests/test_lessons_in_the_journey.py`, `test_key_points.py`, the curriculum test
`test_every_rule_is_taught_before_it_is_practised`, `apps/mobile/src/__tests__/verbs.test.ts`; Maestro flows
`e2e/learn-first.yaml` and `e2e/mission-rule.yaml` pass on the iOS Simulator (free: no scene played, no day planned).

## Open

The teaching is machine-authored and not yet read by a human teacher (as for the rest of the curriculum). The rule card
in a brief has no audio (lines are only spoken from a lesson's own content).
