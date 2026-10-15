# 0010: Every model choice is set from the environment

- **Date:** 2026-10-15
- **Status:** accepted (founder's instruction)

## Context

Model choices lived in two places: tier lists in `config/llm.yaml` (one entry per model and tier, with its price) and
default arguments in the speech provider classes (`nova-3`, `gpt-4o-transcribe`, `eleven_flash_v2_5`, ...). Changing a
model meant a code or config edit. The founder asked for all of them to be configurable, with the defaults in the env
files.

## Decision

- `config/llm.yaml` is now a **catalog** (model → provider and price, with `source_url` and `as_of`) plus **tiers**
  (catalog names in preference order, effort, max tokens, timeout, retries).
- `LLM_<TIER>_MODELS` (comma-separated) and `LLM_<TIER>_EFFORT` override a tier. A name missing from the catalog fails
  at load with the list of known names, so no call ever runs without a price.
- Speech: `STT_ORDER`, `TTS_ORDER` (already settings) and new `VOICEBOX_STT_MODEL`, `DEEPGRAM_STT_MODEL`,
  `OPENAI_STT_MODEL`, `ELEVENLABS_STT_MODEL`, `ELEVENLABS_TTS_MODEL`, `OPENAI_TTS_MODEL`, `ELEVENLABS_STS_MODEL`.
- `.env.example` (and the local `.env`) list every default. Blank means default.
- The root test fixture clears `LLM_*`, so tests always see the shipped tiers.

## Reverting

Delete the variables from `.env`; the defaults in `config/llm.yaml` and the settings classes apply.
