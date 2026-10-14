# Reuse Plan

**Status:** APPROVED 2026-10-14 (decision 0003). The OpenAI Realtime client is not reused (decision 0001).
**Source:** `simupatient@69e1bd5` (read-only). Evidence: `docs/REUSE_AUDIT.md`.

Legend: **LIFT** = copy with its tests, then bring to `ruff` + `mypy --strict` · **ADAPT** = copy and reshape, or reuse the design/pattern only · **NEW** = built from scratch.

Every lifted file starts with `# Lifted from simupatient@69e1bd5:<origin path>` and gets a row in the ledger at the bottom.

## Module map (SPEC §5.2), annotated

```
apps/
  mobile/                    NEW   Expo app. Pattern refs: bedside-audio.ts (ordered playback),
                                   fake-mic Playwright technique for Expo-web smoke tests
services/
  api/                       NEW   FastAPI app
    auth/                    ADAPT invite flow, session revocation, role guard ← security/auth.py,
                                   invitation_service.py. Core NEW: name+PIN, Argon2id, lockout,
                                   rotating device refresh tokens, AuthProvider (§23.2)
    audit.py                 LIFT  ← services/audit_service.py, models/audit.py
    media_urls.py            ADAPT HMAC signed short-lived audio URLs ← bedside_session_service.py
  live/                      NEW   VoiceTransport impl (bake-off winner), Actor, Contract Guard
    turn_gate.py             LIFT  ← realtime/policy.py (quality gates, echo similarity)
    tts/                     ADAPT ← services/speech_service.py (ABC, OpenAI, ElevenLabs, Fallback);
                                   + voicebox adapter NEW; cache moves to synthesis_cache
    stt/                     NEW   (Simupatient has no standalone STT adapter)
    actor/                   ADAPT approved-facts prompt pattern ← patient_simulation_graph.py
    guard/                   NEW   post-generation per-sentence Contract Guard (§10.4)
  graphs/                    NEW   LangGraph workers
    checkpointing.py         LIFT  ← agents/checkpointing.py
    assessors/               ADAPT hybrid deterministic + LLM scoring shape, job lifecycle,
                                   calibration-fixture tests ← scoring_graph.py, scoring_service.py
    scene_compiler/          ADAPT immutable versions + readiness validation ← case_service.py,
                                   case_readiness_service.py, case_generation_graph.py
  pronunciation/             NEW
packages/
  agent-memory/              NEW   (no memory library exists in Simupatient; see audit Q2)
  contracts/                 NEW
  curriculum/                NEW   (review flow pattern ← case review/approval)
  exam_packs/                NEW
  economy/                   NEW
  llm/                       ADAPT ← agents/providers.py generic core (LangChainChatProvider init,
                                   structured output, usage capture, reasoning-effort helper,
                                   local test provider pattern). NEW: fast/mid/frontier tiers,
                                   fallback chain, prompt caching, Langfuse, versioned prompts/
                                   Cost: rate-card pattern ← usage_service.py, models/usage.py
content/                     NEW   (all original)
evals/                       NEW   (calibration-fixture style ← tests/test_scoring_calibration.py)
tools/
  voicebench/                NEW harness; stats.py LIFT ← benchmarks/voice_latency/scoring.py
                                   (percentile, bootstrap, hierarchical bootstrap) + noise-aware
                                   gate ← compare.py; A/A-control method from phase-15 doc
  content_cli/ admin_scripts/ NEW
infra/
  docker-compose.yml         ADAPT ← docker-compose.yml (strip founder-specific hostnames)
  alembic/                   ADAPT setup + migration-rehearsal test style; fresh revisions
.github/workflows/           NEW   (Simupatient has no CI)
```

## Explicitly not reused

Clinical prompts and heuristics (`providers.py` ~2,400 lines), clinical schemas, bedside engine, media/video generation, the Next.js frontend and its i18n dictionary, the AWS Elastic Beanstalk bundle, RQ, passlib, python-jose, and the OpenAI Realtime WebRTC client (pending audit Q1).

## Sizing (rough, for Phase 0–1 planning)

| Item | Effort |
| --- | --- |
| Lifts (turn gate, checkpointing, audit, bench stats) incl. strict typing | S each |
| `packages/llm` adaptation | M |
| TTS adapters + voicebox | M |
| Auth (name + PIN) | M |
| Contract Guard (new) | M–L |
| `packages/agent-memory` (new) | L |
| voicebench harness + B/C/D adapters | L |

## Lift ledger

| Lingard path | Origin path (simupatient@69e1bd5) | Verdict | Tests carried |
| --- | --- | --- | --- |
| _(filled when copying begins after approval)_ | | | |
