# Phase 4 gate: accent studio

**Verdict: NOT PASSED. Built, not yet measured.**

| Gate (SPEC §25) | Status | Why |
| --- | --- | --- |
| Pronunciation at or above published baselines | **NOT MEASURED** | speechocean762 (EN) not downloaded or run yet; the FR annotated set doesn't exist yet |
| Golden-self accent leakage below threshold in a blind test | **NOT MEASURED** | Needs a voice-conversion provider key and human listeners |

## What exists (`services/pronunciation`)

- Prosody (pitch, rhythm), GOP-style phone scoring, and a combined scoring HTTP app. Unit tests in
  `services/pronunciation/tests`.
- The wav2vec2 phone recogniser is an **optional install** (large model download). Without it, scoring uses the
  prosody features only.
- Golden self: the voice-clone provider interface, an audio watermark, and a clone-deletion cascade with verification
  (`services/api/src/lingard_api/privacy.py`). The Voicebox profile-creation endpoint paths are **assumed** from
  documentation and are untested against a live account.
- Studio loop, end to end: the app's Studio screen loads lines from `content/pronunciation/studio_<lang>.yaml`
  (`GET /v1/studio/items`). It uploads each attempt to `POST /v1/studio/shadow`, which decodes the audio and forwards
  it to the pronunciation service (`uvicorn --factory lingard_pronunciation.server:build_app`). The screen shows
  clarity, accent match and misheard phonemes. Up to 3 attempts; one FSRS review on the final attempt (Good, Hard or
  Again). Tested in `services/api/tests/test_studio.py` against the real service app with a fake recogniser. Every
  studio line is checked against the lexicon in `services/pronunciation/tests/test_app.py`.
- Until a golden-self render exists, shadowing has **no reference audio**: intonation isn't scored and there's no
  pitch overlay. Accent match is then phoneme accuracy only.

## To close the gate

1. Feed the golden-self render (or a native TTS render) to `/shadow` as the reference, so intonation is scored.
2. Install the recogniser extra, then run speechocean762 and compare with the published PCC baselines.
3. Build a small FR annotated set (founder plus native raters).
4. Configure a voice provider, then run a blind A/B leakage test with ≥ 10 listeners.
