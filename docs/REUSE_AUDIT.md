# Reuse Audit: Simupatient → Lingard

**Status:** APPROVED 2026-10-14 (decisions 0001, 0003). Q1: candidate A disqualified, no bake-off, LiveKit chosen. Q2: Simupatient only
**Audited:** `~/Documents/simupatient` @ `69e1bd5` (origin `git@github.com:wizzybenson/simupatient.git`), read-only
**Date:** 2026-10-14
**Method:** I read the architecture, phase and voice-latency docs and the backend modules listed below, then ran the backend test suite without writing caches (`pytest -p no:cacheprovider`: **405 passed, 8 skipped** in 6 min 16 s). `git status` in Simupatient was clean afterwards.

## Summary

Simupatient is a healthy codebase (405 tests pass, phase gates are documented, latency work is benchmarked with care), but it was built for a different product. Three findings shape the plan:

1. **Simupatient's voice pipeline probably fails the bake-off's hard constraints as-is.** It runs the browser over WebRTC straight to OpenAI Realtime (`gpt-realtime-2`). The backend LangGraph returns approved text and the realtime model *speaks* it. So the audio comes from a hosted speech-to-speech model, TTS can't be swapped (no voicebox or ElevenLabs voice in the live loop), the media path can't be self-hosted, and the client is browser-only Next.js. See open question Q1.
2. **The "LLM router" is a domain service, not a router.** `agents/providers.py` is 2,752 lines: about 350 lines of generic LangChain core and about 2,400 lines of clinical prompts and local heuristics. It has *scopes* (`default/generation/interaction/voice_interaction`), not tiers, and no cross-provider fallback, response caching or prompt caching. The generic core is worth lifting and wrapping in tiers. The rest stays behind.
3. **There is no memory library to lift.** Simupatient's memory is `session_state` JSON plus LangGraph checkpoints. `packages/agent-memory` gets built new (SPEC §2).

Everything Simupatient does well and generically comes across: transcript quality gates, echo rejection, TTS adapters with fallback, the checkpointer wrapper, latency-bench statistics, audit-log and usage-tracking patterns, and the pre-generation fact-gating design.

## Audit table

| Capability | Source path(s) | What it does today | Quality notes | Verdict | Effort |
| --- | --- | --- | --- | --- | --- |
| **Voice transport** | `backend/app/realtime/manager.py`, `realtime/providers/openai_realtime.py`, `frontend/src/lib/realtime/openai-realtime-client.ts` (1,610 lines) | Backend mints an OpenAI Realtime client secret. The browser opens WebRTC to OpenAI, which does VAD (`semantic_vad`, eagerness high), STT (`gpt-4o-mini-transcribe`) and audio output. Each transcribed turn calls the tool `consult_langgraph_patient`, the backend returns approved text, and the realtime model speaks it | Well instrumented (per-stage telemetry, first-audio fix in phase 15). Over WebRTC, audio deltas don't reach the data channel, so sentence-level gating of audio isn't possible. Measured: speech end → VAD ~0.9 s p50, backend turn ~2.0 s p50, `response.create` → first audio ~0.5 s. Commit → first audio p50 **3.06 s**, p90 3.9 s, far above Lingard's 800 / 1,300 ms budget | **Replace** (candidate A as-is likely fails hard constraints; see Q1) | — |
| Turn detection / barge-in | same + `config.py` (`openai_realtime_vad_*`) | Provider VAD; `response.cancel` on barge-in; tracks `interruptedPatientAudio` and passes it to the backend | Works, but depends on OpenAI VAD. `server_vad` at 300–500 ms caused +4–22 pp fragmentation, which is evidence for §6.2's per-learner `eot_ms` | **Adapt (pattern)**: interruption-in-context flag | S |
| Transcript quality gate + echo handling | `backend/app/realtime/policy.py` (148 lines) | Language-agnostic turn validation: empty / too short / low entropy / echo similarity to recent NPC lines / confidence and speech-duration plausibility → accepted / needs_confirmation / ignored | Clean, pure functions, tested, no clinical coupling. Thresholds live in settings. Directly serves the "0 NPC self-transcriptions" metric | **Lift** → `services/live/turn_gate.py` | S |
| STT / TTS adapters | `backend/app/services/speech_service.py` (358 lines) | `SpeechProvider` ABC with `synthesize`/`stream`; OpenAI TTS, ElevenLabs (`eleven_multilingual_v2`, per-role/per-language voices), `FallbackSpeechProvider`, scripted test provider, in-process LRU audio cache | Small and clear. No STT adapter (STT is inside Realtime). No voicebox. Cache is per-process, not `synthesis_cache` | **Adapt** → `services/live/tts/` + add voicebox and a new STT adapter | M |
| Ordered client audio playback | `frontend/src/lib/bedside-audio.ts` | Prefetch, play in timeline order, stall/timeout caps, mute | Browser `HTMLAudioElement`; logic is sound | **Adapt (pattern)** for the Expo audio queue | S |
| **Fact-gated character speech** → Contract Guard | `backend/app/agents/graphs/patient_simulation_graph.py` (1,172 lines), `schemas/patient_intent_schema.py` | *Pre-generation* gating: classify intent → select allowed case facts → LLM writes reply only from `allowed_facts` → trace. Clinical results go out as system cards, not speech. Affect changes tone, never facts | Good design and well tested, but heavily clinical (vitals, exam, investigations, collateral informants). **Known residual: about 1 in 750 generated turns over-discloses** (phase 15 report), so pre-gating alone doesn't reach Lingard's "0 fact violations" gate | **Adapt (design)**: keep the approved-facts prompt pattern in the NPC Actor; build the *post-generation* per-sentence Contract Guard (§10.4) new | M |
| Scenario / case structure | `schemas/case_schema.py`, `models/case.py`, `services/case_service.py`, `case_readiness_service.py`, `agents/graphs/case_generation_graph.py`, `case_augmentation_graph.py` | Immutable published `case_versions` (`case_json`, `rubric_json`); readiness checks before publish; sectioned AI generation with consultant review; language field per case | Strong patterns (immutable versions, readiness gate, human review as primitive). Schema content is clinical | **Adapt (pattern)**: versioning + readiness/validation + review flow → `SceneContract` validation and curriculum review (§8.1). Schema replaced | M |
| LLM router | `backend/app/agents/providers.py` L31–170, 360–430, 544–900, 2745+; `config.py` | `init_chat_model` for OpenAI/Anthropic, per-scope model/timeout/reasoning-effort/service-tier, `with_structured_output` (json_schema on OpenAI), usage capture via `UsageMetadataCallbackHandler`, local deterministic provider for tests | Generic core is good. Gaps for Lingard: no tiers, no fallback chain, retries = LangChain `max_retries` only, no prompt caching, no Langfuse, prompts are inline f-strings (Lingard needs versioned `prompts/` files). Typed loosely (`Any`), not `mypy --strict` clean | **Adapt** → `packages/llm`: lift core, add `fast/mid/frontier` tiers, fallback, Anthropic prompt caching, Langfuse callback, prompt-version logging | M |
| Cost tracking | `services/usage_service.py`, `models/usage.py` (`AIUsageEvent`, `AIRateCard`) | Usage events from traces, projected off the hot path via RQ, priced from a rate-card table, CSV export | Sensible; off-critical-path by design. Langfuse covers much of it | **Adapt (pattern)**: rate card with `source_url`/`as_of`, feeding §22 cost budgets | S |
| LangGraph checkpointing | `backend/app/agents/checkpointing.py` (40 lines) | `AsyncPostgresSaver` context manager, in-memory saver under test | Tiny, correct | **Lift** → `services/graphs/checkpointing.py` | S |
| Scoring and debrief | `agents/graphs/scoring_graph.py` (636 lines), `services/scoring_service.py`, `agents/rubric_recall.py`, `tests/test_scoring_calibration.py`, `tests/fixtures/scoring_calibration/` | Hybrid: deterministic components plus LLM rubric classification and feedback; rubric augmented in case language; async scoring jobs with status; calibration fixtures | Good pattern: deterministic first, LLM for judgement, language-aware feedback, calibration tests as fixtures. Rubric content is clinical, and there's no band posterior or isotonic calibration | **Adapt (pattern)**: hybrid scoring graph shape, job/status lifecycle, calibration-fixture tests. Assessors built new | M |
| Latency benchmark harness | `backend/benchmarks/voice_latency/` (`scoring.py`, `compare.py`, `bench_realtime.py`, `run_interleaved.sh`) | Gold corpus, concurrent arms with shared shuffled order, A/A control, paired hierarchical bootstrap, noise-aware gate | Methodologically the strongest code in the repo (an A/A run showed naive per-turn bootstrap was anti-conservative). Directly reusable for voicebench | **Lift** stats + gating (`percentile`, `bootstrap_*`, `hierarchical_bootstrap_*`, noise-aware gate) → `tools/voicebench/stats.py` | S |
| Memory | `docs/architecture/session-memory.md`, `models/session.py` (`session_state`), checkpoints | Per-session working memory: disclosed facts, asked categories, running notes, affect. No episodic/semantic/procedural store, no embeddings | Not a library; session-scoped | **Replace**: build `packages/agent-memory` new (SPEC §2) | L |
| Voice cloning / TTS cache / audio storage | `speech_service._AudioCache`, `media/storage.py`, `bedside_session_service.stream_signed_speech` | No cloning. LRU audio cache in memory. Local-disk media storage with HMAC-signed short-lived URLs | Signed-URL streaming is a good pattern for `<audio>`/Expo playback without bearer tokens | **Adapt (pattern)**: signed URLs. Voice clone service + `synthesis_cache` new (§13.7) | S |
| Auth, user model, sessions | `security/auth.py`, `services/auth_service.py`, `invitation_service.py`, `models/auth.py`, `models/user.py` | Email + password (bcrypt via passlib) and passwordless email links; JWT (python-jose); token-session table with revocation; multi-tenant memberships/roles; invitations | Revocation and audit are solid. Mismatch: Lingard is name + 6-digit PIN with Argon2id, lockout backoff and rotating device-bound refresh tokens. passlib and python-jose are effectively unmaintained | **Adapt (pattern)**: invite flow, session revocation, role guard, audit hooks. **Replace** core: `argon2-cffi`, `PyJWT`, new `AuthProvider` | M |
| Audit log | `services/audit_service.py`, `models/audit.py` | Append-only actor/action/target records | Small, generic | **Lift** (adapt to §7 columns) | S |
| Frontend stack / design system / i18n | `frontend/` (Next.js 16.2.6, React 19.2.4, Tailwind 4, Vitest, Playwright); `src/lib/i18n.ts` (2,374 lines, flat dictionary) | Web-only, responsive; EN/FR dictionary with locale switcher; Playwright e2e incl. fake-mic voice specs | Not Expo; no RN components reusable. Dictionary keys are clinical. Fake-microphone e2e technique is reusable for web | **Replace** (Expo app new). Reuse the fake-mic Playwright technique for Expo-web smoke tests | — |
| EN/FR handling | `case.language`, `bedside_engine/french.py`, `_language_instruction`, `_patient_reply_language_instruction`, `openai_realtime_transcription_language`, `i18n-bedside.ts` | Per-case language drives prompts, STT language, voices (`ELEVENLABS_VOICE_*_FR`), UI strings | Language is a data field rather than code branches. `french.py` contains hand-written French grammar helpers (pronouns, agreement) for clinical templates | **Adapt (pattern)**: language as config, per-language voice maps, STT locale from content. Code itself is clinical | S |
| Video avatars / media | `media/providers.py`, `media/scene_pack.py`, `agents/graphs/scene_pack_graph.py`, `bedside_engine/` | Image/video generation (fal, Higgsfield) for patient scenes, media QA, scene packs | Not in v1 scope (2.5D sprites). Possible later use for illustrating districts | **Skip in v1** (revisit for asset generation) | — |
| Infra: Docker / compose | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `aws/` (Elastic Beanstalk bundle) | frontend, backend, RQ worker, Postgres, Redis; migrations on boot | Works. Contains founder-specific ngrok/cloudflare hostnames, which must not come across (§24 open-source readiness) | **Adapt**: compose skeleton → add live, graphs, pronunciation, MinIO, Langfuse, voicebox | S |
| Migrations | `backend/alembic/` (16 revisions) | Alembic, incl. migration tests (`test_phase14_migration.py`) | Revisions are clinical schema | **Adapt (pattern)**: Alembic setup + migration-rehearsal test style. Fresh revision history | S |
| Tests | `backend/tests/` (31 files), `frontend/e2e/` | 405 backend tests pass; local deterministic provider makes graph tests offline | Good. Lifted modules bring their tests (SPEC §0.2) | Lift tests with lifted modules | — |
| CI | none (`.github/` absent) | — | No CI exists | **New** | M |
| Env / config | `backend/app/config.py` (pydantic-settings), `.env.example` | Typed settings, many flags, validator for prod-unsafe providers | Good pattern; one flat settings class | **Adapt (pattern)**: per-service typed settings + YAML thresholds (§24) | S |
| Python version | `backend/.venv` | Runs on **Python 3.13** | Lingard targets 3.12 (SPEC §0.8); lifted code must be re-tested on 3.12 | Note | — |

## Licences

Backend dependencies (versions as installed in Simupatient's venv, licence from package metadata):

| Package | Version | Licence | Flag |
| --- | --- | --- | --- |
| fastapi | 0.124.2 | MIT | |
| langchain / langchain-openai / langchain-anthropic | 1.2.0 / 1.1.3 / 1.2.0 | MIT | |
| langgraph / langgraph-checkpoint-postgres | 1.0.10 / 3.0.2 | MIT | |
| SQLAlchemy / alembic | 2.0.45 / 1.17.2 | MIT | |
| pydantic-settings | 2.12.0 | MIT | |
| redis / rq | 7.1.0 / 2.6.1 | MIT / BSD-2 | RQ not needed (Redis Streams + LangGraph workers) |
| httpx / uvicorn | 0.28.1 / 0.38.0 | BSD-3 | |
| python-multipart / bcrypt | 0.0.20 / 4.0.1 | Apache-2.0 | |
| pillow | 11.3.0 | MIT-CMU | |
| email-validator | 2.3.0 | Unlicense | |
| passlib | 1.7.4 | BSD | **Unmaintained**: don't carry over (use `argon2-cffi`) |
| python-jose | 3.5.0 | MIT | **Maintenance risk**: use `PyJWT` |
| psycopg | 3.3.2 | **LGPL-3.0-only** | OK to use unmodified as a library in closed or open products; note it in the licence inventory |

Frontend: next, react, react-dom (MIT); lucide-react (ISC). None carries over (Expo replaces Next).

**Simupatient itself has no LICENSE file.** Copying is fine because the founder owns both repos. Lifted files get an origin header and a `REUSE_PLAN.md` entry, and Lingard's licence choice stays deferred to the founder (SPEC §24).

Nothing found blocks selling or open-sourcing. CI will run a licence check (`pip-licenses` / `license-checker`) to keep this current.

## Open questions for the founder (blocking)

**Q1. Voice candidate A.** Ported as-is, Simupatient's pipeline is OpenAI Realtime speech-to-speech over WebRTC. It appears to fail three hard constraints in SPEC §4.2: TTS can't be swapped (the realtime model is the voice, so no voicebox or ElevenLabs clone), it can't be self-hosted (the media plane is OpenAI's), and it doesn't run natively in Expo without a react-native-webrtc port. Arguably it also fails "cascaded", since audio comes from an S2S model rather than a TTS. Under SPEC §4.2 a candidate that fails a hard constraint is out. Choose one:
- (a) **Disqualify A**, record it in `docs/gates/phase-0.md`, run the bake-off with B, C and D. Simupatient's reusable voice parts (turn gate, echo check, TTS adapters, bench stats) go into the winner regardless. *(Recommended.)*
- (b) Define **A′** = Simupatient's *backend* pipeline (turn gate + TTS adapters + its own STT) behind a plain WebSocket transport, built to compete. That's new transport code, not reuse, so it's mostly an extra build cost.
- (c) Keep A in the bake-off for its numbers only (as a reference baseline), ineligible to win.

**Q2. Other repos in `~/Documents`.** The spec names Simupatient as the only reuse source, but I saw `agent-memory-system`, `simupatient-gpt-live`, `simupatient-gpt-live-native`, `voice-latency-results`, `lingovox` and `talklyne`. I haven't opened them. `agent-memory-system` in particular might already be the `packages/agent-memory` the spec asks for. Should any of them be in scope? If yes, that changes SPEC §0.1/§2, so I'd write `docs/decisions/CHALLENGE-reuse-scope.md` rather than deviate silently.

**Q3. Bake-off test set.** §4.2 needs 60 minutes of recorded FR + EN learner speech with hand-labelled pauses, plus a real phone for the echo test. Who records it, and when? I can build the harness and a recording/labelling tool first so the data drops straight in.

**Q4. GitHub.** I initialised git locally with `origin` = `wizzybenson/lingard` (the remote is empty). Should I commit and push `main` after you approve this audit, or do you want PRs from the start?

## Reversible defaults I'll take (recorded in `docs/decisions/` once approved)

- `PyJWT` + `argon2-cffi` instead of python-jose + passlib.
- No RQ in Lingard: Redis Streams consumers + LangGraph workers cover background work (§5.3, §11).
- Lifted files get a header comment: `# Lifted from simupatient@69e1bd5:<path>`.
