# 0020: Transcribe while the learner speaks

- **Date:** 2026-10-20
- **Status:** accepted (reversible: `STT_STREAMING=false`)

## Context

The founder asked for smooth voice end to end. With the latencies measured on 2026-10-15, the offline latency eval put
first NPC audio after the end of a learner's turn at p50 2,188 ms and p95 2,861 ms (gate: 800 / 1,300). Batch STT of
the whole turn (~1.0–1.2 s) sat first in the serial chain STT → LLM first sentence → Guard → TTS.

Small live probes (2026-10-20, a few cents):
- batch STT: ElevenLabs Scribe 802 ms and similarity 0.973; OpenAI 1,012 ms and 0.931. So ElevenLabs is both faster and
  more accurate, yet it came last in `STT_ORDER`.
- streaming STT (ElevenLabs Scribe v2 Realtime over a websocket): **~250 ms from commit to final text**, exact on
  the test sentence, including a second commit that carries on after a speculative pause.
- NPC tier with thinking off vs on: no reliable difference at n=3 (876 vs 1,240 ms), so the config is unchanged.
  Prompt caching already applies (Haiku 5.5 caches from 512 tokens).

## Decision

- The endpointer emits `LearnerAudio` in 100 ms batches while the learner speaks, flushed before every speculation
  and end-of-turn decision (tested: everything up to the decision has been streamed).
- `LiveLoop` opens an `ElevenLabsRealtimeStt` stream when speech starts, feeds it, and at speculation or end of turn
  only commits. It falls back to batch transcription on any failure, an empty result, or a 1.5 s timeout.
- `STT_ORDER` puts ElevenLabs before OpenAI for the batch fallback.
- The latency bench models the streamed commit (`stt_stream_commit_ms` in `profiles.yaml`, n=3, marked as such).

## Result

Offline latency eval with measured provider latencies: p50 2,188 → **1,239 ms**, p95 2,861 → **1,874 ms**. The gate
still fails. The biggest remaining stage is the NPC model's first token (~0.9–1.3 s on Haiku 5.5). Changing the
fast-tier model is the founder's call.
