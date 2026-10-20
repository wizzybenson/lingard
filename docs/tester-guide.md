# Testing Lingard by hand

For someone trying Lingard on a phone or the Simulator for the first time.

## Getting in

1. The founder creates your account:
   - in the admin screen, or
   - with `POST /v1/admin/users {"display_name": ...}`.

   You get a one-time PIN.
2. Sign in with your name and that PIN. You are then asked to choose your own 6-digit PIN.
3. Pick the app's language (English, French or Arabic) on the sign-in screen. You can change it later in Settings.

Setup for the founder: `docs/ios.md` covers the Simulator and a real iPhone. Before a session, start the services
listed in `AGENTS.md` and run `uv run python -m lingard_api.cli seed`.

## What to try, in each language

Set at least one exam goal: TEF Canada (French, Rivemont) or IELTS General Training (English, Ashford). Setting both
lets you try everything twice.

| Area | Try | Look for |
| --- | --- | --- |
| First run | Goal → placement (or skip) → first rule → first story day | Nothing blocks you; each step says what comes next |
| Story missions | Start a day, read the mission brief, talk, then Leave or finish | The brief makes the goal clear; the character stays in character and in the story's facts; the debrief judges what you actually said; coins arrive |
| Lessons in the journey | The "Useful here" strips before a scene, on the map and after a scene | They help without getting in the way, and close for the day |
| School | A rule, a word set, a phrase set | Explanations make sense; the games work (in English grammar: irregular verbs, e.g. go → went); tap any line to hear it |
| Phone | Answer a few quick messages | If you study both exams, French and English take turns |
| Exam Hall | A full mock (TEF or IELTS), Desk writing | Official order and timing; recordings play once; scores feel fair |
| Accent Studio, Your voice | Read the passage, hear your own voice with a native accent | Consent first; deleting your voice works |
| Shop (coin pill on Home, or Passport) | Streak freeze, café visit, a gift, flat upgrade | Each one does what it says: freeze next to the streak, an extra café mission on a new day, the character warmer, décor in your home on the map |
| Passport | Simulated CRS, Draw Day goal | The latest real round's cutoff for your exam (French-language rounds for TEF; Canadian Experience Class for IELTS only) |

## What to report

- **Wrong language:** wrong grammar, an unnatural phrase, or English or French that a teacher would correct. Quote it
  and say where you saw it.
- **Story slips:** a character contradicting the mission, inventing facts, or breaking character.
- **Being stuck:** anything that blocks or confuses you, waits too long, or loses your progress.
- **Rewards:** coins or stars that seem wrong.
- **Screen problems:** text cut off, overlapping, or untranslated, especially in Arabic, which reads right to left.

## Known limits

- **Dark mode:** not built yet.
- **Voice is slower in some places:** a few spots in a live call can take 2–3 seconds; the character's model is the
  bottleneck.
- **Lessons are machine-reviewed:** a person has not yet read every lesson; finding mistakes in them is part of this
  test.
- **The simulated CRS is for motivation only:** it is not an official assessment.
