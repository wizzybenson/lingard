# 0017: Progress, not the calendar; the learner's own interface language; levels in plain words

- **Date:** 2026-10-18
- **Status:** accepted (reversible)

## Context

The founder: "Do not use calendar timings to stop progress … make the date and calendar about progress and not about
actual days and time", and "those numbers are cryptic like 4–8 → 7", and the French pages had an English interface:
"it assumes the user speaks English".

## Decision

**Progress, not the calendar.**
- A city's story day is `days_lived + 1` (`WorldView.days_lived`: finished live sessions in that city). The header
  reads "Day 3 · Rivemont", and the action is "Begin day 3", not "Start today's story".
- Finishing a day (`POST /sessions/{id}/end`) queues the next day's plan right after night consolidation, so the next
  day is ready whenever the learner is. City also plans the next day ahead, keyed on the day number, not on "practised
  today".
- A planned, unplayed day is reused however old it is (`ready_plan_reuse_hours` removed). Only a plan stuck in
  "planning" past `plan_reuse_minutes` is replaced.
- The planner rotates places by story day (`days_lived`), not by `toordinal()`.
- The map's people-at-places use an in-world hour (`world_hour`, default 12), not the server clock.
- `/v1/today` never puts reviews before the story. Due reviews are a side action ("Quick review: 3 due").
- Still on real dates, deliberately: exam countdowns (a real exam date), spaced-repetition due times (learning
  science), and the practice streak (motivation only, it gates nothing).

**The learner's own interface language.**
- `users.ui_locale` is nullable (migration 0003): None means not chosen yet, instead of English for everyone.
- Sign-in starts in the device language and offers English, Français, العربية. A language picked there is saved to the
  profile on sign-in; otherwise the profile's choice applies, and an unset profile takes the language on screen.
- Practice content stays in the target language; the interface is in the learner's language (as Duolingo and other
  major apps do). More interface languages are new files in `src/i18n/`.

**Levels in plain words.** `home/levels.ts: levelWords / levelProgress`. Skills show a bar from the middle of the
estimate towards the goal, status words ("needs work · goal 7"), and one line explaining the scale ("Levels use NCLC,
the 1–12 scale Canada uses for immigration…"). Passport reads "Estimated level: below 4 to 8" and "Exam score
estimate: about 180 (likely 77–283)", never "<4–8".

## Evidence

247 Python and 39 app tests pass. API tests cover end-of-day planning, reuse of an unplayed day, and `days_lived`. On
the iPhone 17 Pro Simulator: tour, live-scene and language flows pass (the language flow picks French on sign-in, signs
in, shows City in French, and switches back).
