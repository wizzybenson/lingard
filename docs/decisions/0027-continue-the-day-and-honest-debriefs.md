# 0027: A day is continued, never replaced; a debrief judges only what was said

Date: 2026-10-22. Status: accepted. Amends the day-reuse rule in `routes/sessions.py` (0014).

## What the founder hit

- **No feedback after a 14-turn conversation.** The founder had opened the scene earlier and tapped Back without
  talking. `leave()` set the status to `ended`, which asks for the debrief. The server judged an empty conversation,
  saved "not_done", and returned that saved verdict after the real conversation.
- **"Begin day 1" never changed.** A day with a played scene was never reused, so every Begin day planned a new day.
  The founder had eight unended days, each with one scene played. `days_lived` only counts ended days, so it stayed
  at 0. Each new plan also cost a compile.
- **English on the Phone tab in Rivemont.** With both exams set, the inbox alternated between the two languages.

## Decisions

1. Leaving a scene that never connected keeps it `idle`, so nothing is judged.
2. A debrief with no learner turns returns "not_done" without saving it, paying, or changing the scene's status.
3. The newest unended day is continued while it has unplayed scenes or more scenes are still being planned. A new
   day is planned only once every scene is played. `SessionView` gains `next_scene_id` and `played`. Begin day
   opens `next_scene_id` and reads "Continue day N" once a scene is played. If every scene is played, the day is
   ended and the notebook opens.
4. The Phone shows the language of the city last played in (the phone the learner carries there). Its intro now
   says what it is for: messages that review the story's material or practise exam questions, a minute at a time.

## Repair

The founder's scene `1375a11e` had its empty verdict cleared and was judged again with the endpoint's own code:
accomplished, 3/3 objectives, 70 coins. One confirmed correction (`pronoms_cod_coi`, 0.92, the second check
agrees) is waiting in the brush-up and the notebook. The older half-played days stay as they are, and the newest one
(`270a827c`) is the one that continues.
