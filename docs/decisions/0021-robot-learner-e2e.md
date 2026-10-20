# 0021 — A robot learner drives the real stack end to end

Date: 2026-10-20 · Status: accepted

## Context

Voice had only been measured on the loopback transport. The founder asked for a real end-to-end test with voice,
including the voice clone.

## Decision

`tools/voicebench/e2e_learner.py` acts as a learner exactly as the app does:
- signs in over HTTP and plays the next day's scene in a real LiveKit room, speaking with macOS `say` (an engine
  unlike the NPC voices);
- lets the `mid` tier decide what to say (`sim_learner` prompt), ends the day and waits for the night notebook;
- with `--clone`: consents, enrols a clone, fetches the golden-self reference, scores a shadowing attempt, then
  deletes the clone and checks the deletion.

Each run costs a few cents.

## What it found and what changed

| Found live | Change |
|---|---|
| A speculation the learner talked over was cancelled mid-commit; the final transcript came back as the first sentence only (3 of 4 turns in one run). | `ElevenLabsStream` keeps every commit in arrival order, whoever waits for it. Tested against a fake Scribe websocket; the test fails on the old code. |
| Every turn waited the full patience window (1.2 s): `semantic_eot` was enabled but never wired. | The streaming partial transcript drives it. A finished question (per-language `continuation_words`) ends the turn at 60 % of the window. Ending on any full stop split 2 of 3 multi-sentence turns, so statements always wait the full window. Measured wait: 580 ms instead of 960–1,200 ms. |
| The notebook "corrected" "nouvel arrivant", which the learner had said right; STT misheard it. | Second hearing: a streamed turn is re-transcribed by the batch recogniser (Deepgram here), after the reply. A tag whose words are not in every hearing is dropped: not shown, not evidence. Live: the planted "The controls looks" was heard by both and corrected. |
| The examiner (test centre) was cast in an ordinary story day. | `CityContent.story_settings` excludes exam-only kinds (`test_centre`). |
| "Right… Right, I'll tell you…" | The hesitation never repeats the first word of its sentence. |
| The pronunciation service crashed at start (phonemizer missing). | `phonemizer` added to the `models` extra (needs `brew install espeak-ng`, and `PHONEMIZER_ESPEAK_LIBRARY=/opt/homebrew/lib/libespeak-ng.dylib` on macOS). The recogniser now degrades instead of crashing. |
| Native speakers failed "un" (/œ̃/ heard as /ɛ̃/). | Per-language accepted variants (`content/pronunciation/variants_fr.yaml`). Good native voices score about 90. |
| A refused clone gave an unhandled 500. | 502 with the provider's reason. |
| `VoiceboxClone` did not match voicebox's real API. | Rewritten from voicebox's source: empty profile, then transcribed samples of 2–30 s; a half-made profile is deleted. Not yet run against a live voicebox. |
| One loop turn's timings were invisible. | One log line per turn: end-of-turn wait, first audio, and stage times. |

## Measured (2026-10-20, local LiveKit, real providers)

- **From learner silence to NPC voice, measured by the robot at its microphone (device not included):**
  - French: 1.3–2.7 s.
  - English: 1.44–1.68 s.
- **After the end-of-turn decision:**
  - STT: 0.18–0.3 s.
  - NPC model first token: about 0.8–1.0 s later (Haiku 5.5). This is the remaining lever, and it is the founder's call.
- **Accent Studio:** shadow scoring takes 1.6 s; the golden-self reference (native fallback) takes 3.2 s.

## Still open

- **Voice clone:** cannot be tested here.
  - ElevenLabs refuses because the pay-as-you-go plan has no instant voice cloning.
  - Installing voicebox's dependencies needs the founder's go-ahead (third-party code).
- **Golden self:** without an ElevenLabs clone, golden self falls back to the native render.
