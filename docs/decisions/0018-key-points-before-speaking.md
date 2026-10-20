# 0018: Key points before speaking; Phone as an inbox

- **Date:** 2026-10-20
- **Status:** accepted (reversible)

## Context

The founder: "add keypoints language lessons — no one can just start speaking without knowing rules as we planned".
SPEC §16 already says every grammar node needs a lesson template before its band is playable, but lessons were only
ever built from a learner's mistakes, so a new learner was sent into scenes with no rules at all. The founder also
called the Phone tab ugly: eight quizzes stacked in one scroll, with bold centred buttons and no feedback beyond
"Not quite".

## Decision

**Key points.**
- `GET /v1/key-points?language=` returns the grammar path up to the learner's band plus one (a preview), with
  prerequisites first and otherwise the order the curriculum files are written in. Nodes at the learner's own band
  are *core*; lower bands are "basics to refresh".
- `POST /v1/key-points/{node}` builds the lesson from the node's authored rule, examples and common errors with **no
  model call** (`lesson_builder.key_points_lesson`), so it opens at once and costs nothing. Reopening returns the same
  lesson. `Lesson.kind` is `key_points` or `remedial`, and `Lesson.models` carries correct model sentences.
- Today puts `key_points` after placement and before the story day while any core node is unlearned, and the card
  opens that lesson directly.
- The teaching order is read from the seed files rather than stored in node payloads: a payload change bumps a node's
  version and clears its review, which would lock every lesson.
- The regular-present drill uses only verbs whose present forms follow the -er/-ir pattern (derived, not listed).
  Tense names come from `conjugation.yaml`.

**Phone.** One message at a time with progress, left-aligned `Choice` rows, and the verdict plus "Next" pinned in thumb
reach. `/v1/glance/answer` now returns the right option's index (Glance is practice, never a mock). The cached queue
paints first and the network refreshes it behind.
