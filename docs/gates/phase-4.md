# Phase 4 gate: accent studio

**Verdict: NOT PASSED. Built, not yet measured.**

| Gate (SPEC §25) | Status | Why |
| --- | --- | --- |
| Pronunciation at or above published baselines | **NOT MEASURED** | speechocean762 (EN) not downloaded or run yet; the FR annotated set doesn't exist yet |
| Golden-self accent leakage below threshold in a blind test | **NOT MEASURED** | Needs a voice-conversion provider key and human listeners |

## What exists (`services/pronunciation`)

- Prosody (pitch, rhythm), GOP-style phone scoring, and a combined scoring HTTP app. Unit tests in
  `services/pronunciation/tests`.
- The wav2vec2 phone recogniser is an **optional install** (large model download). Without it, `/shadow` answers 503
  and the app shows scoring as unavailable.
- Golden self: the voice-clone provider interface, an audio watermark, and a clone-deletion cascade with verification
  (`services/api/src/lingard_api/privacy.py`). The Voicebox profile-creation endpoint paths are **assumed** from
  documentation and are untested against a live account.
- Studio loop, end to end: the app's Studio screen loads lines from `content/pronunciation/studio_<lang>.yaml`
  (`GET /v1/studio/items`). It uploads each attempt to `POST /v1/studio/shadow`, which decodes the audio and forwards
  it to the pronunciation service (`uvicorn --factory lingard_pronunciation.server:build_app`). The screen shows
  clarity, accent match and misheard phonemes. Up to 3 attempts; one FSRS review on the final attempt (Good, Hard or
  Again). Tested in `services/api/tests/test_studio.py` against the real service app with a fake recogniser. Every
  studio line is checked against the lexicon in `services/pronunciation/tests/test_app.py`.
- Reference audio: each line has a Listen button (`GET /v1/studio/reference`), and the same render goes to `/shadow` as
  the pitch reference. Intonation (0–100) is then reported separately and blended into accent match (70% phonemes,
  30% intonation). The render is the **golden self** when the learner has an ElevenLabs clone and the pronunciation
  service has `ELEVENLABS_API_KEY`: the API sends the native narrator render to `/golden`, which converts it into the
  learner's voice, watermarks and caches it. Otherwise it is the native narrator render. Without any TTS provider there
  is no reference, and intonation is `null`. Tested with fakes in `test_studio.py` and `test_pronunciation.py`; never
  run against live ElevenLabs.

## To close the gate

1. Install the recogniser extra, then run speechocean762 and compare with the published PCC baselines.
2. Build a small FR annotated set (founder plus native raters).
3. Configure a voice provider, then run a blind A/B leakage test with ≥ 10 listeners.
