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
- **Live coach (the founder said go ahead).** On the test learner, the plan arrived about 15 s after the first look,
  and the path updated in place.
  - v1's reasons were generic ("in your speaking practice" three times) and it gave no reason for the story.
  - v2 gets today's next scene (place, person and goal, never its hidden targets) and must not repeat itself. It then
    chose "Factures et services" over the curriculum's next rule, because the scene was setting up the internet with
    Martin. Every reason named the scene, the sound or the words.
  - v2 also claimed the review cards were about "agreement and disagreement", which it can't know. It is now told it
    doesn't know the cards.
  - The plan's cache key includes the prompt version, and counts sound scores only to the nearest 10.
- **Mock flows.** mock and mock-ielts pass with the keys restored. school-en passes; it was already missing its
  "I'm ready" step.
- **Language switch in flows.** Maestro now switches language with the city pill on Today. On the Simulator, the dev
  build's menu button sits over the pill by the title.

## Found when checking again (2026-10-22, evening)

- **Blank screen.** Once, the Progress tab stayed blank for 20 s after returning from a pushed screen and switching
  tabs. The tab "shift" animation was removed; the tour then passed twice.
- **Rhythm section of the Accent Studio** (the founder saw it display wrongly):
  - The syllable strip labelled syllables in IPA ("œ̃", "ɡʁɑ̃", "tʃeɪs"), and the rhythm tip said "Hold maɪs longer". The
    service now sends each syllable's written word (`spelling`) and the word to hold (`stretch_word`), and the app
    shows the words.
  - The melody line was drawn as if dots were always 40 px apart, so segments pointed the wrong way and didn't join.
    It is now drawn from the panel's measured width, and pitch beyond ±8 semitones is drawn at the edge.
  - The pitch tracker's octave slips: a native "un café" read −13 semitones on its last syllable and scored 11 on
    intonation. Frames more than 9 semitones from the speaker's median are folded back by an octave
    (`accent.fold_octaves`). The same take now reads −1.1 and scores 70.
  - Checked by rendering real results for "un grand café", "un café" and "the cats chase mice" on the Simulator
    through a throwaway screen, since the Simulator can't record.
- **Flows.**
  - Settings is opened by a test id on its row, because the dev menu button covers the gear.
  - French flows first put French in focus (`focus-fr.yaml`), since the English flows leave English in focus.
  - learn-first opens a named grammar lesson, since School's next-up is now the coach's pick.
  - mock-ielts handles a first set without choices, since mocks are assembled afresh.
  - All free flows pass: tour (twice), review, school, school-en, learn-first, studio, voice, language, mock and
    mock-ielts.
- **Not run.** Onboarding needs a fresh account. A live scene ("day") is paid. Nothing has been tried on the phone
  itself since this redesign.

