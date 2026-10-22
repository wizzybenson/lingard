# 0029: Calm, guided days with a learning coach

Date: 2026-10-22. Status: accepted.

## Why

The founder found the app intimidating: "so many texts and school like exercises". They asked for it to be
seamless, to guide the learner to full understanding without a wall of information, and to be fun. They also asked
that the next thing to learn be AI-guided, using what was learnt and the learner's progress.

What a new look at the screens showed:

- Six tabs.
- A home card with four competing actions, two exams' progress bars, a city switcher, a map, a places list and the
  locked chapters.
- An explanatory paragraph at the top of most screens.
- A full-width TEF/IELTS switcher repeated on every screen, although one focus language already drives them all
  (0027).
- Lessons that put every teaching step on the page at once.
- Activities that ended on "Continue" with nowhere to go.

## What changed

**One path a day.** The home screen is a short path of stops, chosen in the order that teaches best:

1. **Warm-up.** At most 8 review cards that are about to be forgotten.
2. **Fix.** A mistake confirmed in recent scenes, quoting the learner's own words.
3. **Story.**
4. **Sound of the day.**
5. **New rule.** Shown only when nothing needs fixing: one new idea a day, always after the story (0025).

How the path behaves:

- Only the stop to do now is open. It gives the reason it was chosen in one sentence and has one button. The other
  stops take one line each.
- Every stop can be tapped in any order, so nothing gates the day (0025).
- Done stops stay ticked (`mark_active(kind=…)` records review, lesson, sounds and writing; a scene played today counts
  as the story).
- Finishing the whole path brings a small celebration with a haptic.
- Before the goal and level are known, the getting-started checklist stays in its place.

**The learning coach.** `lingard_graphs.agents.learning_coach` (prompt `learning_coach@v1`, `mid` tier) gets a brief
of what the learner has shown:

- rules learned;
- mistakes confirmed (≥ 0.85 plus a second check) in their last three scenes, with their words and how many scenes
  each appeared in;
- the rules at their level not learned yet, with BKT p(mastery);
- sound-drill scores;
- exam skills against the goal (met, close or behind).

From that it chooses the mistake to fix, the new rule and the sound, and writes each stop's reason in the interface
language.

- **Candidates only.** It may only choose among the candidates, by key. Anything else is dropped together with its
  reason, and reasons are cut to 160 characters.
- **Cached per day.** The plan is kept in `settings.coach` for the day under a digest of the brief. Ticking a stop or
  answering a card doesn't change the digest, so it doesn't send the coach back to work.
- **Never waited on.** The first look at the screen gets the curriculum's order at once (`coach: "thinking"`) while the
  coach runs in the background. The app looks again 4 s later and the path updates in place (`"ai"`).
- **Fallback.** Without a model, or when the coach fails, the curriculum's order and the app's own wording stand
  (`"rules"`).
- **Why not a pure LLM path.** The order of the day is pedagogy and stays in code (`lingard_api.coach.plan_path`). The
  coach decides what fills it and says why, so a model failure can never empty or scramble the day.

**Every activity hands on.** After a finished lesson, a review round, a climbed drill or the night's notebook, the
learner sees "Up next", the next stop of the path with its reason. When the path is done, it says so and offers the
way home.

**Four tabs:** Today · Practice · Exam Hall · Progress.

- The Passport tab is now **Progress**. The founder asked why it was called Passport. The name was the spec's
  immigration metaphor, but it told a learner nothing about what is inside: levels, simulated residency points and the
  latest real draw. The residency-points card keeps the Canada theme.

- Practice is three tiles: Review, Sounds (the Accent Studio) and Lessons (the School). Each tile has one line saying
  what is next, as the coach picked it.
- Review, the School and Settings are pushed screens with a Back button. Settings sits behind a gear in Progress.

**Less on every screen:**

- Intro paragraphs removed.
- The exam switcher is a small pill by the title (`FocusSwitch`).
- Long lists folded behind `Disclosure`:
  - the places under the map;
  - the School's word and phrase sets (the kind holding "next up" stays open);
  - the Studio's full drill list;
  - the exam's official parts;
  - the second exam in Progress.
- The exam on the home screen is one line: countdown and the skill needing most work.
- The streak and coins are two pills by the greeting.
- A drill's six numbered circles became a slim bar ("Words · step 3 of 6"). The three speed buttons became one chip
  that cycles 0.5×, 0.75× and 1×.
- A lesson teaches one step at a time ("Got it · next (2/4)"). Its model sentences, words and "watch out" follow once
  the steps are through. "I'm ready" stays available throughout.

**Motion:**

- Tabs shift rather than cut.
- Path stops and Practice tiles enter in a stagger. Stops spring into place as they are ticked.
- A drill's steps slide in and out.
- "Up next" rises in after a finish.
- Taps give haptics.

## Evidence

- Python: `test_coach.py` covers the order, the warm-up cap, a fix displacing the new rule, one rule a day, the
  coach's choices and reasons, and a stale choice falling back. `test_learning_coach.py` checks that the learner's
  own words and mastery reach the coach and that non-candidates and long reasons are dropped or cut.
  `test_today.py`: no path before the level is known.
- App: tsc, eslint and jest are clean.
- Maestro (Simulator, API without model keys so no paid call was made): tour, studio, school, learn-first and
  review pass with the new navigation.
- The mock flow needs a provider configured to start, so it was not run here.
- The coach has not been run against a live model yet: one `mid` call per learner per day, waiting for the founder's
  go-ahead on spend.
