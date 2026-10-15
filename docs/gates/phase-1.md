# Phase 1 gate: one French street (Rivemont)

**Verdict: PASS offline; FAIL on measured provider latency (2026-10-15).** The offline column comes from harnesses
with scripted providers. The live column uses real providers (OpenAI, ElevenLabs, Anthropic keys from 2026-10-15)
through the simulated loop; a real LiveKit room and network are still not measured.

| Gate (SPEC §25) | Offline result | Live result |
| --- | --- | --- |
| First audio p50 ≤ 800 ms | **334 ms** (95% CI 279–436) | **FAIL: 1,448 ms** (CI 1,303–1,712): OpenAI STT + Haiku + ElevenLabs |
| First audio p95 ≤ 1,300 ms | **657 ms** | **FAIL: 2,384 ms**, same providers |
| 0 fact violations over 50 scenes | **0 of 500 planted violations leaked**, over 50 scenes | not measured |
| Targets elicited ≥ 85% | not measurable offline (needs a real actor) | not measured |

## Latency (`evals/suites/latency.py`, using `tools/voicebench`)

- 60 simulated turns through the real endpointer, speculation, Guard and streaming code paths.
- **Provider stage timings are assumptions**, not measurements: profile `assumed_cloud` in
  `tools/voicebench/profiles.yaml` (STT 280 ms, LLM first token 380 ms, TTS first chunk 170 ms, network 45 ms, all
  lognormal medians). The result is only as good as those assumptions.
- Without speculative drafting: p50 887 ms and p95 1,146 ms, which misses the p50 budget. Speculation is what makes the
  budget, at a cost of 0.47 wasted drafts per turn.
- Guard p99: 0.27 ms, so it is not a latency factor.
- To replace the assumptions: put provider keys in `.env`, run `uv run python -m tools.voicebench.probe
  --write-profile`. It times every configured STT, TTS and fast-tier LLM provider and writes a `measured` profile,
  which the latency eval then uses automatically.

### Measured providers, 2026-10-15

Keys: OpenAI and ElevenLabs only. `tools.voicebench.probe --runs 5 --write-profile` measured medians (raw numbers in
`evals/results/provider_probe.json`, profile `measured`):

| Stage | Provider used | Median | Profile assumed |
| --- | --- | --- | --- |
| STT (batch, 2–4 s line) | OpenAI | 970 ms | 280 ms |
| LLM first token (fast tier, `gpt-6-luna`) | OpenAI | 1,385 ms | 380 ms |
| TTS first chunk | ElevenLabs | 285 ms | 170 ms |

ElevenLabs STT was 948 ms with better similarity (0.97 vs 0.93) but sits after OpenAI in the preference order.
The same 60-turn bench on the `measured` profile: **first audio p50 1,987 ms, p95 3,242 ms** (no speculation:
2,783 / 3,820 ms). The gate fails by about 2.5×. STT and the LLM's first token are each larger than the whole budget,
so this needs a streaming STT (Deepgram, or self-hosted Voicebox) and a faster fast-tier model (Anthropic Haiku
is the configured first choice); TTS is not the bottleneck. Still not measured: a real LiveKit room and network.

With the Anthropic key added (`--runs 6 --write-profile`): Haiku first token **785 ms** (Luna 1,427 ms), OpenAI STT
958 ms, ElevenLabs TTS 289 ms. Bench: **p50 1,448 ms, p95 2,384 ms** (no speculation 2,192 / 3,069 ms). Swapping only
the STT median for an assumed Deepgram batch figure of 350 ms gives p50 853 ms, p95 1,743 ms: closer, still failing.
Deepgram is not measured (no key); a streaming STT path is the next step if its batch latency is not enough.

## Contract adherence (`evals/suites/contract_adherence.py`)

- 50 scenes from `evals/scenes.py`, cycling through all 18 NPCs in both cities, with 500 violations planted in NPC
  lines (facts outside the approved set, language leaks, tutor-speak, character breaks) and 700 clean lines. A planted
  fact whose `key` the scene legitimately knows (e.g. "mercredi" when the NPC's paper comes out on Wednesdays) isn't a
  violation there. It is skipped and counted as `plants_skipped_on_contract` (6 of 500), not scored as a leak.
- Leaked: 0 fact violations, 0 language leaks, 0 tutor or character-break lines. False blocks: 0% (0 of 700 clean
  lines blocked).
- This tests the **Contract Guard**, not the actor model. A live run is needed to measure how often a real model
  produces violations and whether targets get elicited.

## Built

The Rivemont Vieux-Port district (3 NPCs: Martin Lefebvre, Chloé Gagnon, Karim Benali) and the LiveKit live loop
(`services/live`): VAD endpointer with speculation, actor, Guard, captions and STT/TTS adapters. Also the
`turn_assessment` graph, compiled scene contracts, and the 2.5D Skia map (verified rendering in Chrome on Expo web).
Language specifics live in `content/languages/fr.yaml`.

## Reproduce

```sh
uv run python -m evals.run --suite latency --suite contract_adherence
```
