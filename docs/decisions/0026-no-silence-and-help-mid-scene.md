# 0026: No silence in a scene, and help when the learner is stuck

Date: 2026-10-22. Status: accepted.

## What happened

The founder played Begin day on the iPhone. Three problems: they had no clue what to say, replies were very slow, and
the NPC kept saying "Excusez-moi, je n'ai pas bien compris" after long silences.

The live worker's log showed what went wrong. The STT was fine (200–340 ms per turn). Anthropic was unreliable that
night (502s, stalled TLS handshakes; a probe afterwards still saw Haiku time out). The fast tier fell back only on
an error, so each attempt waited out its 8 s timeout, Haiku and then Sonnet: a 17–23 s silence. When no model
answered, the reply fell back to the `clarify` line, which made it sound as if the learner hadn't been understood.
Gemini, the listed cross-provider fallback, was never used because `GOOGLE_API_KEY` is empty.

## Decisions

1. **Hedged tiers** (`hedge_s` in `config/llm.yaml`). A model that hasn't streamed its first text (or, for `text`,
   finished) within `hedge_s` is raced by the next one, and the first to answer wins. An error moves on at once.
   fast: 1.8 s; guard: 1.0 s (inside the claim check's 2.5 s deadline).
2. **A different provider in the NPC chain.** fast: Haiku → Sonnet → gpt-6.1-sol → Gemini; guard: Haiku → gpt-6.1-sol
   → Gemini. Haiku stays primary (the founder's call). OpenAI is only reached when Anthropic stalls. Probe on
   2026-10-22, time to first token: Haiku 0.65–2.2 s plus timeouts; Sonnet 0.68–3.8 s; gpt-6.1-sol 1.6–2.3 s.
3. **No dead air.** If a reply has no first sentence 1.8 s after preparation began (`STALL_FILLER_AFTER_MS`), the NPC
   says a hesitation ("Alors…"). Only one hesitation per turn.
4. **The NPC never blames the learner for an outage.** When no model answers, the NPC says a `stalled` line from
   `content/languages/<lang>.yaml` ("Oh, pardon, j'étais ailleurs une seconde… Vous disiez ?"), never `clarify`.
5. **Help mid-scene.** While the scene is live, the mission's steps stay under the goal. "What can I say?" (beside
   Leave) calls `POST /v1/scenes/{id}/say-next` with the captioned conversation. The answer is three short lines at
   the learner's band, each with its meaning in the interface language and the step it serves. Prompt
   `say_next@v1`, fast tier, about 2 s. The lines clear once the learner speaks. There is no help in mock exams
   (409).

## Evidence

- Unit tests cover racing, failure fallthrough, the stall filler and the stalled line. Python and app suites pass.
- Robot scene live (rivemont, 4 turns): first audio 1.0–1.2 s after the end of each turn. One turn's model needed
  3.1 s for its first token, and the hesitation covered it. Before this, the same stall gave 17–23 s of silence.
- say-next live: 1.9–2.5 s, three on-mission lines. Maestro `e2e/scene.yaml` now asks for ideas
  (screenshot 15-say-next).
