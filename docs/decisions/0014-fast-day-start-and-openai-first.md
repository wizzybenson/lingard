# 0014: A day starts at its first scene and is planned ahead; OpenAI first for planning

- **Date:** 2026-10-18
- **Status:** accepted (reversible)

## Context

The founder: starting a practice "takes too long". Planning should run "in background part by part" for a low start
latency, with "better reasoning for planning, not luna and not low sol", and "openai for most api as it is cheaper".

Measured on Ernest's plan briefs (`day_planner`: one story-beats call, then three scene compiles in parallel):

| compile model | beats | compiles (each) | learner waits |
|---|---|---|---|
| gpt-6.1-sol, effort medium (before) | 5.4 s | 24.9 / 75.7 / 27.2 s | 81 s (slowest scene, one validation retry) |
| gpt-6.1-sol, effort low | 5.2 s | 26.7 / 21.8 / 20.0 s | 32 s |
| claude-sonnet-5-5, medium | 5.0–6.4 s | 10–14 s | 19–21 s |
| gpt-6-luna, low | 3.9 s | 9.6–14.6 s | 19 s |
| claude-haiku-5-5 | 5.7 s | all failed structured output | n/a |

The founder ruled out Luna and low effort for planning, so quality stays at gpt-6.1-sol medium and the speed comes
from structure.

## Decision

- **Playable from the first scene.** `compile_scenes` saves each scene the moment it compiles and marks the session
  `ready` (with `complete: false`) at the first one. `persist_day_plan` sets `complete: true`. A resumed run reuses
  scenes already saved. The API exposes `complete`. At the end of a scene the app waits for the next one ("Preparing
  your next scene…") instead of ending the day while scenes are still compiling. Measured through the API: playable at
  31.5 s, complete at 35.6 s. A scene that needs a validation retry no longer holds up the start.
- **Planned ahead.** When City opens, the next step is the day's story, and the learner hasn't practised today, the
  app starts the day in the background. `POST /v1/sessions` reuses the newest day that is still planning (up to
  `plan_reuse_minutes`) or ready with no scene played (up to `ready_plan_reuse_hours`, 12 h). At most one unplayed day
  exists per city, so planning ahead can't stack up costs. Measured: the tap returned a ready, complete day in 13 ms.
- **OpenAI first.** `mid` is now gpt-6.1-sol → Sonnet → Gemini, and `compile` and `frontier` were already gpt-6.1-sol.
  At catalog prices (2026-10-14) gpt-6.1-sol equals Sonnet and gpt-6-luna equals Haiku per token. `fast` (NPC) and
  `guard` stay on Haiku: Luna as the NPC is a separate call (decision 0010 removed it), and the guard needs short,
  thinking-free answers (decision 0012).

## Cost

Planning ahead spends one plan (gpt-6.1-sol: beats plus three compiles) on a day the learner may not play. That's at
most once per city per 12 h, and only before the first practice of the day.
