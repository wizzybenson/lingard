# Lingard — Implementation Spec v1

**For:** Claude Code (implementing agent)
**Owner:** Ernest (founder)
**Date:** 2026-10-14
**Repo:** https://github.com/wizzybenson/lingard.git
**Design doc (source of truth for intent):** https://claude.ai/code/artifact/abf9127e-5783-4bc3-9443-7ac476a0cceb

---

## 0. Rules for the implementing agent

1. **Reuse before build.** Phase 0 is a mandatory reuse audit of **Simupatient**, the only existing codebase to draw from. It sits next to the `lingard` clone in the founder's `~/Documents` folder (expected at `../simupatient` relative to the repo root; list `~/Documents` to confirm the exact folder name, and ask if it isn't there). Write no new module until `docs/REUSE_AUDIT.md` exists and the founder has approved it.
2. **Lingard is a fresh repo**: https://github.com/wizzybenson/lingard.git, laid out as in §5. Keep this spec at `docs/SPEC.md` in the repo. Code lifted from Simupatient is copied in (never linked or modified in place), keeps its tests, and is noted in `docs/REUSE_PLAN.md` with its origin path. Where no Simupatient code fits, build new.
3. **Locked decisions (§2) are not re-litigated.** If evidence says one is wrong, write `docs/decisions/CHALLENGE-<topic>.md` with the evidence and ask. Do not silently deviate.
4. **Verify anything time-sensitive at implementation time**: SDK versions, model IDs, vendor prices, CRS tables, IELTS/TEF formats, CLB conversion tables. Every external fact stored in the repo carries `source_url` and `as_of`.
5. **Phases ship behind gates (§25).** Do not start a phase until the previous gate passes, with evidence committed in `docs/gates/phase-N.md`.
6. **Never commit** secrets, learner audio, voice embeddings, PINs, or calibration-vault content.
7. **Irreversible or ambiguous choices → stop and ask.** Reversible choices → pick the sensible default, record it in `docs/decisions/`, continue.
8. **Code quality:** Python 3.12, type hints everywhere, Pydantic v2, `ruff` + `mypy --strict` on new packages; TypeScript `strict`. Small modules, tests alongside code, no dead code.

---

## 1. Product in one paragraph

**Lingard**: the learner lives in a simulated world until they pass **IELTS General Training** and **TEF Canada** at their target bands. An English city in England and a francophone city in Canada are populated by agent NPCs whose everyday errands, arguments, calls, letters and broadcasts are disguised exam tasks compiled from a curriculum graph. A silent assessor scores everything against CLB/NCLC descriptors and each test's rubric; a director agent rewrites the next session around weaknesses. A School teaches rules explicitly and pairs each lesson with a same-day quest. Accent work uses the learner's own cloned voice speaking with native pronunciation ("golden self"). Exam Hall runs full mocks in the exact official format. Progress is scored as a **simulated CRS**, with stars and coins as secondary rewards.

---

## 2. Locked decisions

| Area | Decision |
| --- | --- |
| Product shape | **Lingard**, a fresh repo; Simupatient is the only reuse source. v1 = personal exam tool for the founder plus a few invited friends; built robust enough to sell or open-source later |
| Exams | IELTS General Training (English), TEF Canada (French). Other tests only via the exam-pack interface, not built in v1 |
| Setting | English city in England ("Ashford"); francophone city in Canada ("Rivemont"). Joined by a flight. French NPCs speak mostly standard French; Québécois voices appear at higher bands |
| Orchestration | **LangGraph** for all planning/assessment graphs. Google ADK rejected |
| LLM access | **LangChain LLM router** lifted from Simupatient. No LiteLLM. Tiers: `fast`, `mid`, `frontier` mapped in config |
| Voice transport | **Decided by a Phase 0 bake-off** (§4.2): Simupatient's pipeline vs LiveKit Agents vs Pipecat, plus any stronger option found at the time. Best measured score wins; ties go to Simupatient (reuse). All behind `VoiceTransport` (§6) |
| Voice pipeline | Cascaded STT → LLM → Guard → TTS (no speech-to-speech in v1) |
| Voice clone | jamiepine/voicebox self-hosted (primary), ElevenLabs fallback; persistent clones, delete only on explicit user action. Built new in Lingard (§13.7) |
| Memory | `packages/agent-memory`: four-type model (episodic, semantic, procedural; working memory in LangGraph state). Lift from Simupatient if it exists there; otherwise build it as a standalone, framework-agnostic package with no LLM orchestration inside |
| Stores | Postgres + pgvector (primary), Redis Streams (events), S3-compatible object storage (MinIO locally). Curriculum graph in Postgres behind `CurriculumGraph` interface; Neo4j adapter optional |
| Observability | Langfuse (self-hosted) + OpenTelemetry |
| Client | Expo (React Native) for iOS/Android + web. **2.5D** illustrated world first; 3D later. World state is renderer-independent |
| Auth | **Display name + 6-digit PIN**, invite-only, behind `AuthProvider` interface (§23.2) |
| Language order | **French first, English required in v1.** Phase 1 builds Rivemont (French); Ashford (English) follows in Phase 1b; both languages reach full parity before v1 is called done. Everything language-specific is per-language config/content, never French-only code |
| Placement | Optional placement: quick adaptive placement, full mock, or skip (§17) |
| Content | Form follows official tests exactly; all shipped content is original. Official materials the founder owns may go into a private, uncommitted calibration vault |

## 3. Non-goals for v1

- 3D world, human-to-human multiplayer, payments, public sign-up, app-store release (use Expo dev builds / internal TestFlight / web).
- CELPIP, PTE Core, TCF Canada packs (interface only).
- Arabic UI (planned later; UI strings must be i18n-ready from day one).
- Immigration advice beyond linking official IRCC pages.

---

## 4. Phase 0 — Reuse audit and voice bake-off

### 4.1 Audit procedure

1. Locate both repos. Clone/read **read-only**. Never modify Simupatient.
2. For every capability below, fill one row of `docs/REUSE_AUDIT.md`:

| Capability | Source path(s) | What it does today | Quality notes | Verdict (lift / adapt / replace) | Effort (S/M/L) |
| --- | --- | --- | --- | --- | --- |

Capabilities to audit:

- Voice loop: STT/TTS providers, transport (WS? WebRTC?), streaming, sentence chunking, barge-in, echo handling, mobile behaviour.
- Fact-gated character speech (Simupatient's "approved case facts" gating) → becomes the Contract Guard.
- Scenario/case structure and how cases are authored and loaded.
- LangChain LLM router: tiers, retries, fallbacks, caching, cost tracking.
- Scoring and debrief patterns.
- Any memory implementation (candidate for `packages/agent-memory`).
- Any voice cloning, TTS caching or audio storage code.
- Auth, user model, sessions.
- Frontend stack (is it Expo? Next.js?), design system, i18n.
- EN/FR handling, video avatars (Simupatient).
- Infra: Docker, deploy scripts, CI, tests, migrations, env/config.
- Licenses of every dependency (flag anything that blocks open-sourcing or selling).

3. Produce `docs/REUSE_PLAN.md`: target module map (§5) annotated with what is lifted, adapted or new.
4. **Stop for founder approval.**

### 4.2 Voice bake-off (decides §6)

Pick the voice stack on measured evidence, not preference. Build `tools/voicebench/`: one harness, one recorded test set, one network simulator, run against every candidate behind the same `VoiceTransport` interface.

**Candidates**

| ID | Candidate | Why it is in |
| --- | --- | --- |
| A | Simupatient's pipeline, ported as-is | Working today; reuse default |
| B | LiveKit Agents (self-hosted server) | WebRTC media, echo cancellation, jitter buffer, mobile SDKs, turn detection |
| C | Pipecat (self-hosted WebRTC transport) | Python pipeline framework, provider-agnostic, similar features to B |
| D | Scouted option | Before the bake-off, spend at most half a day searching for anything newer or clearly better (e.g. a realtime API used in text-out mode with our own TTS). Add it only if it can meet the hard constraints below |

**Hard constraints** (a candidate failing any is out):

- Cascaded: the NPC's text exists before its audio, so the Contract Guard can check every sentence. Speech-to-speech models that emit audio directly are out for v1.
- STT and TTS providers are swappable, including self-hosted voicebox and ElevenLabs as fallback.
- Self-hostable, with no licence that blocks selling or open-sourcing.
- Works in the Expo app on iOS, Android and web.

To keep it fair, all candidates use the same STT, LLM tier, Guard and TTS. Only transport, turn-taking and audio handling differ. Reuse Simupatient's STT/TTS adapters in B, C and D.

**Test set:** 60 minutes of recorded learner speech in French and English across bands, including hesitant low-band speech with long mid-sentence pauses. Founder and friends can record it; label pause positions by hand.

**Scorecard** (each metric scored 0–10 against its target; weights sum to 100):

| Metric | Target | Weight |
| --- | --- | --- |
| End of speech → first NPC audio, p50 / p95 | ≤ 800 / ≤ 1,300 ms | 20 |
| Premature cut-offs on hesitant speech (NPC talks during a mid-sentence pause) | < 2% of turns | 15 |
| Simulated 4G (`tc netem`: 150 ms RTT, 30 ms jitter, 3% loss): intelligibility + p95 | intelligible; p95 ≤ 1,800 ms | 15 |
| Echo on phone speaker, no headphones (real device) | 0 NPC self-transcriptions | 10 |
| Barge-in: learner speaks → NPC audio stops | ≤ 300 ms | 10 |
| 45-minute session stability | no drops; memory growth < 10% | 10 |
| Cost per active hour (transport + infra) | lowest wins | 10 |
| Engineering cost: effort to integrate, operate, and keep upgraded | lowest wins | 10 |

**Decision rule:** highest weighted score wins. If A is within 5 points of the winner, keep A (reuse wins near-ties). If the winner is B, C or D, port Simupatient's STT/TTS adapters into it rather than rewriting them. Record the full scorecard, raw numbers and the decision in `docs/gates/phase-0.md`, and re-run the bake-off whenever a major new option appears.

---

## 5. System architecture

### 5.1 Planes

- **Live plane** (latency-critical): `VoiceTransport`, STT, NPC Actor, Contract Guard, TTS. Publishes turn events. Never waits on assessment.
- **Planning and assessment plane** (LangGraph): director, scene compiler, assessors, exam hall, lessons, consolidation.
- **Memory**: Postgres (+pgvector), object storage, `agent-memory`.

Learner turns flow down as events; only compiled scene contracts and short steering hints flow back up to the actor.

### 5.2 Module map (fresh repo)

```
apps/
  mobile/                 Expo app (iOS, Android, web)
services/
  api/                    FastAPI: REST + WS, auth, world API, admin
  live/                   Live plane worker: VoiceTransport impl, Actor, Guard
  graphs/                 LangGraph workers (one process type, many graphs)
  pronunciation/          Alignment, GOP, prosody, golden-self rendering
packages/
  agent-memory/           Memory library (lifted or new, see §2)
  contracts/              Pydantic schemas shared across services; TS types generated
  curriculum/             CurriculumGraph interface + Postgres impl, pack loader, CLB/NCLC mapping
  exam_packs/             IELTS GT + TEF Canada pack data and item generators
  economy/                Simulated CRS, stars, coins, Draw Day
  llm/                    LLM router lifted from Simupatient, with tiers
content/
  cities/ashford/         districts, locations, NPC cast (YAML)
  cities/rivemont/
  packs/ielts_gt/  packs/tef_canada/
  crs/                    CRS language grid + conversion tables (with source_url, as_of)
evals/
  datasets/  suites/  synthetic_learners/
tools/
  voicebench/  content_cli/  admin_scripts/
docs/
  REUSE_AUDIT.md  REUSE_PLAN.md  decisions/  gates/
```

### 5.3 Turn event (Redis Stream `turns`)

```json
{
  "event_id": "uuid", "trace_id": "uuid", "user_id": "uuid",
  "session_id": "uuid", "scene_id": "uuid", "turn_index": 14,
  "speaker": "learner",
  "language": "fr-FR",
  "transcript": "Si j'aurais su, je serais venu plus tôt.",
  "stt_confidence": 0.91,
  "audio_ref": "s3://audio/<user>/<session>/<turn>.opus",
  "timings_ms": {"speech_start": 0, "speech_end": 4210, "eot_decided": 5080},
  "pauses_ms": [380, 920],
  "npc_context": {"npc_id": "landlord_martin", "last_npc_line": "..."},
  "targets_active": ["fr.grammar.si_plus_pluperfect", "fr.func.express_regret"]
}
```

Consumers: `turn_assessment` graph, pronunciation service, analytics. Delivery: at-least-once; consumers idempotent on `event_id`.

---

## 6. Voice transport and live loop

### 6.1 Interface

```python
class VoiceTransport(Protocol):
    async def open(self, cfg: LiveSessionConfig) -> LiveSession: ...


class LiveSession(Protocol):
    events: AsyncIterator[LiveEvent]  # LearnerSpeechStarted, PartialTranscript,

    # LearnerTurnEnded, BargeIn, NetworkDegraded, Closed
    async def speak(self, stream: AsyncIterator[AudioChunk], utterance_id: str) -> None: ...
    async def cancel_speech(self, utterance_id: str) -> None: ...
    async def set_turn_policy(self, policy: TurnPolicy) -> None: ...
    async def close(self) -> None: ...
```

Implementations: the bake-off winner only (`SimupatientTransport`, `LiveKitTransport`, `PipecatTransport` or the scouted option). Bake-off adapters for losing candidates stay in `tools/voicebench/` and are not shipped.

### 6.2 Turn-taking for learners

- `TurnPolicy` = base end-of-turn silence by band, personalised: `eot_ms = max(base_by_band, p90(learner_intra_utterance_pauses) + 150)`, capped at 1,600 ms.
- Starting bases (tune with data): CLB/NCLC ≤4: 1,200 ms · 5–6: 950 · 7–8: 750 · 9–10: 600.
- If a semantic end-of-turn model is available, combine: end turn early when it is confident the utterance is complete.
- During long learner pauses the NPC may play a backchannel ("mm", "oui ?") from a pre-rendered set; never a full turn.
- Barge-in: learner speech > 250 ms during NPC audio → `cancel_speech`, actor gets the interruption in context.

### 6.3 Actor loop per turn

1. `LearnerTurnEnded` → build actor prompt: cached prefix (persona + scene contract + world facts) + rolling dialogue + any pending steering hint.
2. Stream actor tokens → split into sentences → each sentence through Contract Guard (§10.4) → TTS → `speak`.
3. Publish the turn event (§5.3) in parallel; never block on it.

### 6.4 Language enforcement

STT locale is the city's language. If the learner switches language, the NPC reacts in-world ("Sorry, I don't speak French") and never answers in the other language. A "help" button gives an out-of-world hint in the learner's chosen UI language, logged as a hint use.

---

## 7. Data model (Postgres)

All tables: `id uuid pk`, `created_at`, `updated_at`; user-owned tables also carry `tenant_id` (single tenant in v1, but present) and `user_id`. Alembic migrations. Row-level ownership enforced in the repository layer and covered by tests.

| Table | Key columns |
| --- | --- |
| `tenants` | name |
| `users` | display_name (unique, case-insensitive per tenant), pin_hash, role (`admin`/`learner`), ui_locale, failed_pin_attempts, locked_until |
| `invites` | code_hash, created_by, expires_at, used_by, used_at |
| `device_sessions` | user_id, device_label, refresh_token_hash, last_seen_at, revoked_at |
| `learner_profiles` | target_bands (JSON per pack/skill), crs_inputs (age band, education, work, spouse etc.), model_accent per language, consent flags |
| `voice_profiles` | user_id, provider (`voicebox`/`elevenlabs`), provider_profile_id, consent_at, sample_ref, status, deleted_at |
| `synthesis_cache` | key = hash(profile_id, text, engine_params), audio_ref, created_at, last_used_at |
| `curriculum_nodes` | key, kind (`cando`/`function`/`grammar`/`lexset`/`pron`/`tasktype`/`conj_cell`), language, band, skill, payload JSON, source_url, as_of, version |
| `curriculum_edges` | from_key, to_key, kind (`requires`/`exercises`/`assessed_by`/`prereq`) |
| `mastery` | user_id, node_key, p_mastery, evidence_count, contexts_count, last_evidence_at |
| `fsrs_items` | user_id, item_key, stability, difficulty, due_at, reps, lapses |
| `weakness_tickets` | user_id, node_key, severity, status (`open`/`closed`/`reopened`), examples JSON, interventions JSON, success_contexts JSON |
| `world_state` | user_id, city, district_unlocks, flat, job, inventory, story_flags JSON |
| `npcs` | key, city, persona JSON, voice_id, schedule JSON |
| `npc_relationships` | user_id, npc_key, affinity, shared_history_summary |
| `sessions` | user_id, kind (`live`/`glance`/`exam`/`lesson`/`placement`), started_at, ended_at, trace_id |
| `scenes` | session_id, contract JSON (§9), status, outcome JSON |
| `turns` | scene_id, index, speaker, transcript, audio_ref, timings JSON |
| `assessments` | turn_id or submission_id, pack, dimension_scores JSON, band_estimate, confidence, error_tags JSON, model_versions JSON |
| `pron_scores` | turn_id, phoneme_scores JSON, prosody JSON, intelligibility |
| `writing_submissions` | user_id, pack, task_type, prompt, text, word_count, scores JSON, rewrite |
| `mock_exams` | user_id, pack, sections JSON, raw_scores JSON, band_or_score JSON, clb_nclc JSON |
| `placements` | user_id, language, path (`quick`/`mock`/`skip`), result JSON |
| `lessons` | user_id, node_key, status, homework_scene_id |
| `wallet` | user_id, coins, stars_total |
| `ledger` | user_id, currency, delta, reason, ref_id (append-only) |
| `sim_crs_snapshots` | user_id, value, breakdown JSON, computed_at |
| `draws` | held_at, cutoff, source_note |
| `audit_log` | actor_id, action, target, at (auth events, deletions, admin actions) |

---

## 8. Curriculum graph and exam packs

### 8.1 Graph

- **Node kinds:** can-do statements (skill × band, CLB for English, NCLC for French), communicative functions, grammar points, lexical sets, pronunciation targets, exam task types (per pack), conjugation cells (verb × tense for French; irregular forms for English).
- **Edges:** `requires` (can-do → function/grammar/lexset), `exercises` (task type → can-do), `assessed_by` (can-do → rubric dimension), `prereq` (grammar → grammar).
- **Sources:** CLB descriptors (Centre for Canadian Language Benchmarks) and NCLC descriptors (public); official IELTS GT and TEF Canada format pages. Store `source_url` and `as_of` on every node.
- **Seeding:** LLM drafts nodes from the descriptors → founder reviews in an admin screen (`/admin/curriculum`) → versioned. No node is used in scenes until `reviewed = true`.

### 8.2 Exam pack format (`content/packs/<pack>/pack.yaml`)

Every number below must be verified against the official source at implementation time; fill `source_url` and `as_of`.

```yaml
id: ielts_gt
language: en
scale: {type: band, min: 0, max: 9, step: 0.5}
clb_conversion: content/crs/ielts_gt_to_clb.yaml
sections:
  - id: listening
    minutes: 30          # verify
    parts: 4
    items: 40
  - id: reading
    minutes: 60
    sections: 3
    items: 40
  - id: writing
    minutes: 60
    tasks:
      - {id: task1_letter, min_words: 150, rubric: [task_achievement, coherence_cohesion, lexical_resource, grammatical_range_accuracy]}
      - {id: task2_essay,  min_words: 250, rubric: [task_response, coherence_cohesion, lexical_resource, grammatical_range_accuracy]}
  - id: speaking
    minutes: [11, 14]
    parts: [interview, long_turn, discussion]
    rubric: [fluency_coherence, lexical_resource, grammatical_range_accuracy, pronunciation]
source_url: TODO-verify
as_of: TODO
```

```yaml
id: tef_canada
language: fr
scale: {type: points, per_module_max: {ce: 300, co: 360, ee: 450, eo: 450}}   # verify
nclc_conversion: content/crs/tef_canada_to_nclc.yaml
sections:
  - {id: comprehension_ecrite, minutes: 60, items: 40}
  - {id: comprehension_orale,  minutes: 40, items: 40}
  - id: expression_ecrite
    minutes: 60
    tasks:
      - {id: section_a, kind: continue_news_item}     # verify task definitions
      - {id: section_b, kind: argue_point_of_view}
  - id: expression_orale
    minutes: 15
    tasks:
      - {id: section_a, kind: obtain_information, minutes: 5}
      - {id: section_b, kind: persuade, minutes: 10}
source_url: TODO-verify
as_of: TODO
```

Each pack also provides: item generators per task type (original content, difficulty-tagged), rubric descriptors per band, band exemplars for scorer prompts, and a conversion to CLB/NCLC.

### 8.3 Calibration vault

`vault/` (gitignored, per-deployment, encrypted at rest). Holds official practice material the founder owns. Used only by the calibration suite (§20) as reference items and scored samples. Never served to any learner, never used to generate content, never committed.

---

## 9. Scene contract

```python
class SceneContract(BaseModel):
    scene_id: UUID
    city: Literal["ashford", "rivemont"]
    location_key: str
    cast: list[CastMember]  # npc_key, role in scene, mood, voice_id
    learner_goal: str  # visible: "Get your deposit back"
    targets: SceneTargets  # hidden
    elicitation: list[ElicitationTactic]  # how each target is drawn out
    approved_facts: list[str]  # NPC may state only these (+ world facts)
    npc_language_band: Band  # learner band + 1 (capped at 10)
    speech_rate: Literal["slow", "normal", "fast"]
    accent_variety: list[str]  # e.g. ["en-GB-standard"], later ["fr-CA-quebec"]
    correction_style: CorrectionPolicy  # recast / clarify / elicit; never explicit
    success_conditions: list[Condition]
    evidence_required: list[EvidenceSpec]  # what the assessor must see
    max_turns: int
    exits: list[Exit]  # graceful endings, in-world consequences
    intensity: Literal["calm", "tense", "heated"]  # capped by learner setting
    pack_alignment: list[str]  # e.g. ["tef_canada.eo.section_b"]
```

```json
{
  "city": "rivemont",
  "location_key": "rivemont.vieux_port.apartment_3b",
  "learner_goal": "Récupérer votre dépôt de garantie",
  "targets": {
    "functions": ["fr.func.complain_politely", "fr.func.negotiate"],
    "grammar": ["fr.grammar.conditionnel_present", "fr.grammar.si_imparfait"],
    "lexset": ["fr.lex.housing.deposit_repairs"],
    "pron": ["fr.pron.nasal_vowels"]
  },
  "elicitation": [
    {"target": "fr.grammar.si_imparfait", "tactic": "Landlord asks what the tenant would do if he refused"},
    {"target": "fr.func.negotiate", "tactic": "Landlord offers half; waits for a counter-offer"}
  ],
  "approved_facts": ["Deposit was 900 dollars", "Wall has a small crack", "Lease ended 1 October"],
  "npc_language_band": 7,
  "correction_style": {"default": "recast", "on_intelligibility_failure": "clarify"},
  "success_conditions": ["Learner proposes a counter-offer", "Learner references the lease"],
  "evidence_required": [{"target": "fr.grammar.si_imparfait", "min_uses": 1}],
  "max_turns": 24,
  "intensity": "tense",
  "pack_alignment": ["tef_canada.eo.section_b"]
}
```

Contracts are validated (schema + semantic checks: every target has a tactic, every required evidence has a success path, band within ±1 of learner) before use.

---
## 10. Agents

Model tiers are router config keys, not hard-coded IDs. Suggested defaults (verify availability): `fast` = Claude Haiku 5.5-class, `mid` = Claude Sonnet 5.5-class, `frontier` = Claude Opus 5.5-class. All prompts live in `prompts/` as versioned files; every LLM call logs prompt version to Langfuse.

| Agent | Plane | Tier | Input → Output | Hard rules |
| --- | --- | --- | --- | --- |
| Director | Planning | frontier | learner model, tickets, story state → `DayPlan` (ordered scene briefs, lesson slots) | 40–60% of targets from open tickets; no target repeated in the same setting where it failed |
| Scene Compiler | Planning | frontier | scene brief → `SceneContract` | Output must pass §9 validation; built on a new `ScenarioGenerator` (domain taxonomy, learner-targeted generation), reusing Simupatient's case structure where the audit allows |
| Narrative Keeper | Planning | mid | session outcome → world_state, npc_relationships updates | Never writes pedagogical data into world memory |
| NPC Actor | Live | fast | contract + dialogue → streamed NPC lines | Speaks only at `npc_language_band`; never explains grammar; never breaks character except via Exit |
| Contract Guard | Live | rules + small classifier; `fast` fallback | each NPC sentence → pass / rewrite / block | Blocks off-contract facts, wrong language, over-band vocabulary, unsafe content; adds ≤ 50 ms per sentence |
| Utterance Assessor | Assessment | mid | turn event → dimension scores, error tags mapped to curriculum nodes | Every tag cites the exact span; uncertain tags marked low-confidence, never shown as corrections |
| Pronunciation Engine | Assessment | non-LLM | audio + transcript → phoneme/prosody scores | See §13 |
| Writing Examiner | Assessment | frontier | submission → rubric scores, rewrite, tags | Rubric-anchored with band exemplars; 3 samples, median |
| Exam Hall Proctor | Assessment | frontier ensemble | mock sections → scores, band/points, CLB/NCLC | Exact official timing and task order; no hints |
| Teacher | Planning (build) + Live (deliver) | mid build, fast deliver | node + learner's own errors → `Lesson` | Examples come from the learner's real mistakes; ends with homework scene |
| Coach | Planning | frontier | session → night notebook (corrections, explanations, review cards) | Only shows corrections with confidence ≥ threshold (§12.3) |
| Curator | Planning | mid | assessments → mastery, FSRS, tickets, procedural memory | Deterministic where possible; LLM only for summarising examples |

Steering: the assessor may write one hint into the actor's working memory at most every 4 learner turns (e.g. "conditional not yet elicited; 3 turns left"). Hints never contain corrections.

---

## 11. LangGraph graphs

Postgres checkpointer. Each graph has typed state (Pydantic), idempotent nodes, retries with backoff, and a Langfuse trace linked by `trace_id`.

| Graph | Trigger | Nodes |
| --- | --- | --- |
| `placement` | learner starts placement | choose_path → adaptive_listening → adaptive_reading → writing_task → speaking_interview → read_aloud → score → seed_learner_model → pick_start_district |
| `day_planner` | session start | load_learner_model → select_targets → plan_story_beats → compile_scenes (fan-out) → validate → persist_day_plan |
| `turn_assessment` | each turn event | fetch_context → score_dimensions → tag_errors → map_to_nodes → update_evidence → maybe_steer |
| `writing_review` | writing submitted | score_x3 → aggregate → rewrite → tag_errors → update_evidence |
| `exam_hall` | mock started | run_section (timed, per section) → score_section → aggregate → convert_to_clb_nclc → persist |
| `lesson_builder` | director slot or ticket reopened twice | pick_examples_from_errors → build_explanation → build_games → build_homework_scene |
| `night_consolidation` | session end | summarise_session → coach_notebook → update_mastery → update_fsrs → update_tickets → update_sim_crs → award_rewards → memory_curate |

---

## 12. Assessment and scoring

### 12.1 Dimensions

Per pack rubric (§8.2). Each learner turn gets scored on the speaking dimensions that apply; writing on writing dimensions. Scores are stored per dimension with a confidence value.

### 12.2 Band estimation

- Per skill, maintain a posterior over band (e.g. Gaussian over the 0–9 IELTS scale, over module points for TEF), updated from turns (low weight), writing (medium), mocks (high).
- Display: point estimate + 80% interval. Never show a single number without the range.
- Convert to CLB/NCLC with the official tables in `content/crs/`.
- A calibration layer (isotonic regression) maps raw scorer output to human-rater bands, retrained when new rated data arrives (§20).

### 12.3 Correction confidence

A correction is shown to the learner only if: the error tag confidence ≥ 0.85, and a second independent check (rule check or second model call) agrees. Otherwise it is stored as low-confidence evidence only.

---

## 13. Pronunciation and accent studio

1. **Built new**: accent diagnostic, L1 transfer priors (French and English learners whose L1 is Arabic/Darija, plus a generic fallback), phoneme mastery tracking, prosody service, the shadowing loop and the Accent Studio screen.
2. **Scoring:** forced alignment + goodness-of-pronunciation (GOP) from an L2-tuned phoneme recogniser per language; prosody: F0 contour vs golden self (DTW), stress, rhythm, pause placement, rate. Intelligibility weighting by functional load. Two dials, always in this order: intelligibility, then target-accent proximity.
3. **Golden self:** native TTS renders the line → voice conversion into the learner's timbre (voicebox profile). Phase 4 evaluates candidate conversion models on: accent leakage (judged by a native-accent classifier), timbre similarity, artefacts. Cache in `synthesis_cache`.
4. **Studio loop:** hear golden self → shadow → phoneme heatmap + pitch overlay → max 3 retries → item scheduled in FSRS.
5. **In the world:** only intelligibility-critical errors (functional load above threshold) are passed to the actor as "you didn't understand this word".
6. **Target accents:** `en-GB` (standard Southern British) for Ashford; `fr-FR` standard for Rivemont, with `fr-CA` exposure from band 8 on. Learner can change model accent per language.
7. **Voice clone service** (new): create a clone once from the placement read-aloud or a dedicated 60 s recording, after explicit consent; store the provider profile id in `voice_profiles`; reuse it across sessions; voicebox primary, ElevenLabs fallback behind one `VoiceCloneProvider` interface; delete only on explicit user request, with the cascade in §23.1.

---

## 14. Learner model and memory

| Memory type | Stored where | Contents |
| --- | --- | --- |
| Working | LangGraph state / live session | contract, rolling dialogue, pending hint |
| Episodic | `agent-memory` episodic + `turns`, `scenes` | what happened, per-NPC shared history summaries |
| Semantic | `mastery`, `fsrs_items`, `weakness_tickets`, band posteriors, accent profile | what the learner can do |
| Procedural | `agent-memory` procedural | what works for this learner (correction styles, session length, hint habits) |

- **World memory and pedagogical memory never mix.** NPCs read only world memory and their own relationship history; pedagogy reaches them only through contracts.
- **Mastery:** Bayesian knowledge tracing per node, evidence weighted by context difficulty and assessor confidence.

---

## 15. Reinforcement loop

1. Assessor tags errors → curriculum nodes, with severity and span.
2. Curator opens/updates a `weakness_ticket`.
3. Director allocates 40–60% of next session's targets to open tickets, interleaved, in new settings.
4. Close a ticket after correct use in ≥ 3 distinct contexts across ≥ 2 days.
5. Recurrence reopens it with higher priority and a different intervention; second reopen → Teacher lesson.
6. A failed district gate or mock is regenerated around its gaps: new scenes, same targets.

All thresholds are config values (`config/pedagogy.yaml`), tuned by the synthetic-learner suite and real data.

---

## 16. The School

- One school per city: Ashford College, École du Vieux-Port. Teacher NPC + 2–4 classmate NPCs (learners slightly above/below the user).
- Lesson = one curriculum node, 5–10 min: rule → examples from the learner's own mistakes → practice games → homework scene the same day.
- Games (all scored, all feeding evidence): conjugation duel (timed, vs classmate), sentence-building race, spot-the-error, dictation, register switch (informal → formal).
- Conjugation mastery tracked per `conj_cell` (French: présent, passé composé, imparfait, plus-que-parfait, futur simple, conditionnel présent/passé, subjonctif présent; English: irregular past/participle forms, tense-aspect forms).
- Director can send the learner to class in-story ("your manager enrolled you").
- Every grammar node in the graph must have at least one lesson template before its band is playable.

---

## 17. Placement

Optional; learner picks per language.

| Path | Flow | Output confidence |
| --- | --- | --- |
| Quick (default) | §11 `placement` graph, ~25–35 min | moderate |
| Full mock | Exam Hall, full official format | high |
| Skip | Start at Arrivals with wide priors | low, narrows over 3 sessions |

Quick placement details:

- **Listening / reading:** adaptive item selection (start mid-band, 1-parameter IRT or a simple staircase; stop at SE below threshold or 15 items per skill).
- **Writing:** one short task (~120 words, form email), scored by the Writing Examiner.
- **Speaking:** "border interview" with an officer NPC, prompts escalating through describe → narrate past → compare → hypothesise → argue; stop after two consecutive failures at a level.
- **Read-aloud (60 s):** accent baseline; with explicit consent, also voice-clone enrolment.
- **Can be played in-fiction or as a plain test** (learner toggle).

Result writes: band posterior per skill, predicted IELTS band / TEF module points, initial sim CRS, starting district, first tickets, accent baseline. Retake any time from Exam Hall. Gameplay evidence overrides placement as it accumulates.

---

## 18. Gamification and economy (`packages/economy`)

### 18.1 Simulated CRS (main score)

- Inputs: predicted bands → CLB/NCLC per skill → CRS language points using the official grid stored in `content/crs/` (first and second official language, plus the French bonus rules), plus non-language factors the learner enters once in `learner_profiles.crs_inputs`.
- Recompute nightly and after every mock. Store snapshots with breakdown.
- Label everywhere as "simulated, for motivation; not an official assessment".

### 18.2 Currencies

| Currency | Earned by | Spent on | Rules |
| --- | --- | --- | --- |
| Residency Points (= sim CRS) | demonstrated level only | nothing (it is rank) | changes only when band posterior moves with confidence ≥ 0.8 |
| Stars (1–3 per level) | margin above the level gate | side stories, hidden places, bonus scenes | awarded once per level; re-earnable upward |
| Coins | quests, lessons, streaks | flat/avatar upgrades, cafés, flights between cities, NPC gifts, extra accent voices | nothing purchasable skips learning or assessment |

All balance changes go through the append-only `ledger`.

### 18.3 Events

- **Draw Day (weekly):** cutoff configured near recent real French-category cutoffs (`draws` table, entered by admin with `source_note`). Sim CRS ≥ cutoff → Invitation to Apply cutscene + coins.
- **Level gates:** stars and points only when assessor confidence is high.
- **Friends league:** weekly ranking by Residency Point gain (opt-in).
- **Landing Day finale:** unlocks after 3 consecutive mocks at target bands in both packs.
- Streaks with one free freeze per week; no punitive mechanics.

---

## 19. World and client

### 19.1 World model (renderer-independent)

`City → District (band-gated) → Location → Hotspot (NPC, object, sign)`. NPCs have schedules (where they are by in-game time). World state served by `GET /world/{city}` as JSON; the client only renders it. The same API will drive the 3D client later.

### 19.2 Client (Expo)

- 2.5D: layered illustrated district maps (parallax), sprite NPCs with idle/talk states, tap-to-walk. Rendering via `@shopify/react-native-skia` (verify current version); web via Expo web. Keep rendering isolated in `apps/mobile/src/world/renderer/`.
- Screens: Sign-in (name + PIN), Arrival/placement, City map, Scene (conversation view with optional captions, slow-replay, word gloss, help), Phone (texts, voicemail, email, news), Desk (writing), School, Night notebook, Accent studio, Exam Hall, Passport (bands, sim CRS), Wallet/rewards, Settings (consents, model accents, intensity, UI language).
- Ergonomics: one-thumb layout, headphone prompt before Live, open-mic default with push-to-talk toggle, haptic on turn start/end, captions fade by band, offline cache for Glance mode.
- UI strings via i18n (EN, FR now; AR later).

### 19.3 Glance mode

2–5 minute text/audio micro-quests from a pre-generated queue (cached offline), synced on reconnect.

---

## 20. Evals (`evals/`, run in CI)

| Suite | Data | Gate |
| --- | --- | --- |
| `band_calibration` | human-rated samples per pack (founder-recruited certified raters) + vault references | mean abs error ≤ 0.5 IELTS band / ≤ 1 NCLC level; QWK reported |
| `real_world_calibration` | learner-reported real results | tracked; north star |
| `correction_precision` | golden learner-error set per language (≥ 300 items each) | ≥ 95% |
| `pronunciation` | speechocean762 (EN) + own FR annotated set | at or above published baselines |
| `contract_adherence` | replayed + simulated scenes | fact violations 0; language leaks 0; targets elicited ≥ 85% |
| `npc_band_control` | level classifier on actor output | ≥ 90% of lines in band |
| `naturalness` | LLM judge + weekly founder review | "tutor-like" ≤ 10% |
| `coverage` | learner model | 100% of a band's nodes evidenced before band marked passed |
| `synthetic_learners` | simulated learners with planted error profiles living N simulated days | planted weaknesses detected, ticketed and closed |
| `placement_accuracy` | synthetic learners at known bands + founder/friends vs later mocks | within ±1 band |
| `latency` / `cost` | voicebench + cost logs | §22 budgets |

Any prompt, model or pack change runs the affected suites; regressions block merge.

---

## 21. Observability

- One `trace_id` per scene across live plane, events, graphs and DB writes.
- Langfuse: all LLM calls with prompt version, tier, tokens, cost, latency.
- OpenTelemetry metrics → dashboards: Voice (stage latencies, barge-ins, premature cut-offs, STT error samples), Pedagogy (band gain per active hour, ticket close/regress rates, coverage velocity), Experience (session length, D1/D7/D30, abandoned scenes, long silences), Quality (correction precision samples, guard blocks), Cost ($/active hour by component, cache hit rate).
- Alerts: p95 latency regression, any fact violation, correction precision drop, cost over budget, auth lockout spikes.

---

## 22. Budgets

**Latency (live):** end-of-turn decision → first NPC audio p50 ≤ 800 ms, p95 ≤ 1,300 ms. Guard ≤ 50 ms/sentence. Off-path: turn assessment ≤ 5 s, scene debrief ≤ 10 s, writing review ≤ 30 s.

**Cost:** target ≤ 1 USD per active Live hour with self-hosted TTS/STT; hard alert at 2 USD. Levers: prompt caching of actor prefix, single-pass assessment with ensemble only on evidence turns, batch APIs for nightly graphs, synthesis cache, Glance mode text-first. Replace all planning estimates with measured numbers in Phase 1.

---

## 23. Security, privacy, legal

### 23.1 Data

- Voice clones and embeddings are biometric: explicit opt-in consent, encrypted at rest, used only in the owner's sessions, never exportable, audio watermarked, deletable with a verified cascade across DB, object storage, voicebox and ElevenLabs, covered by tests.
- Raw learner audio retained 30 days (config), then features + transcripts only, unless the learner opts in to longer retention.
- Data export (JSON + audio) and full account deletion available to every learner.
- Applicable regimes to review before any sale or public launch: Morocco Law 09-08, GDPR, PIPEDA.

### 23.2 Auth: name + PIN (`AuthProvider` interface)

- **Invite-only.** Admin (founder) creates users or single-use invite codes (hashed, expiring). No public sign-up endpoint.
- **Sign-in:** display name (unique, case-insensitive, Unicode-normalised) + 6-digit PIN. Reject trivially weak PINs (`000000`, `123456`, repeats, sequences).
- **Storage:** PIN hashed with Argon2id (tuned to ~250 ms on server hardware), per-user salt; never logged, never in traces.
- **Brute-force protection:** 5 failures → lockout with exponential backoff (1 min, 5 min, 30 min, then admin reset); per-IP and per-name rate limits; generic error messages that don't reveal whether a name exists.
- **Sessions:** short-lived access token (15 min) + rotating refresh token bound to a device record (`device_sessions`); revoke per device; admin can revoke all.
- **Mobile unlock:** after first sign-in, device biometrics (Face ID / fingerprint via Expo LocalAuthentication) can unlock the stored refresh token held in secure storage (Expo SecureStore). PIN still required after 30 days or on new device.
- **PIN management:** learner changes own PIN (requires current PIN); admin reset issues a one-time PIN that must be changed at next sign-in.
- **Audit log:** sign-ins, failures, lockouts, resets, revocations.
- **Future:** `AuthProvider` allows adding email magic links, passkeys or OAuth before public launch without touching the rest of the app.

### 23.3 Content and claims

- Original content only in the repo; vault rules in §8.3.
- No official logos or claims of affiliation; all scores labelled "predicted".
- Contract Guard blocks harassment and unsafe advice; conflict scenes respect the learner's intensity cap; one-tap "pause the world".

---

## 24. Engineering quality and robustness

- **Tests:** unit tests for every package; contract tests for `VoiceTransport` implementations; integration tests per graph with recorded LLM responses (VCR-style fixtures); end-to-end smoke test of one full scene with synthetic audio.
- **CI:** lint, type-check, tests, eval suites affected by the diff, migration check, license check, secret scan.
- **Environments:** `local` (docker compose: api, live, graphs, pronunciation, postgres, redis, minio, langfuse, voicebox), `staging`, `prod` (single host for v1; GPU optional for pronunciation/TTS/STT). Infra as code; no manual server state.
- **Config:** typed settings (pydantic-settings), all thresholds in YAML, feature flags for every phase's features.
- **Resilience:** circuit breakers and fallbacks on every external provider (TTS → ElevenLabs fallback; STT fallback provider; LLM tier fallback). Live session survives a graphs-worker outage (assessment catches up from the stream).
- **Backups:** nightly Postgres backups + object storage versioning; tested restore.
- **API:** versioned (`/v1`), OpenAPI generated, TS client generated for the app.
- **Open-source readiness:** no hard-coded founder paths or keys; `LICENSE` choice deferred to founder; third-party licence inventory kept current.

---

## 25. Phases and gates

| Phase | Builds | Gate (evidence in `docs/gates/`) |
| --- | --- | --- |
| 0. Audit and foundations | §4 audit + voice bake-off; repo layout; contracts package; auth (§23.2); tracing; CI | Founder approves REUSE_PLAN; bake-off scorecard and voice decision recorded; auth tests incl. lockout pass |
| 1. One French street | Rivemont: one district, 3 NPCs, live loop, Contract Guard, turn assessment, scene contracts, 2.5D map for that district. All language-specific parts (STT/TTS locale, prompts, curriculum, Guard rules) built as per-language config | p50 ≤ 800 ms, p95 ≤ 1,300 ms; 0 fact violations over 50 scenes; targets elicited ≥ 85% |
| 1b. English street | Ashford: one district, 3 NPCs, English STT/TTS, English curriculum seed. Should be content and config only; any code change needed here is a defect in Phase 1's language abstraction, logged in `docs/decisions/` | Same gates as Phase 1, in English |
| 2. Learning loop + placement | Director, day planner, tickets, FSRS, night notebook, Teacher + School (both schools), quick placement (both languages), synthetic-learner harness | Synthetic learners in both languages: planted weaknesses detected and closed; placement within ±1 band |
| 3. Exam Hall and writing | Both packs, timed mocks, writing review, calibration with human raters, band posteriors, CLB/NCLC conversion | Mean abs error ≤ 0.5 IELTS band, ≤ 1 NCLC; correction precision ≥ 95% |
| 4. Accent studio | Golden self (voice conversion), pronunciation engine integration, studio loop | Pronunciation at/above baselines; golden-self accent leakage below threshold in blind test |
| 5. Full city + game (= v1) | Both cities at parity, all districts (Arrivals → Civic), economy, Draw Day, friends league, Glance mode, mock-based placement | Founder plays 2 weeks; D7 retention among friends; cost ≤ 1 USD/active hour measured |
| 6. Real-world validation | Founder (and friends) sit real IELTS GT / TEF Canada | Predicted vs actual recorded; calibration retrained |

---

## 26. Founder inputs needed

1. Your CRS non-language factors, for the simulated CRS.
2. Target bands (default: CLB 10 in all four English skills; NCLC 7 minimum, 10 ideal, in French).
3. Access to 2–3 certified raters (or a budget) for the calibration set in Phase 3.
4. Which official practice materials you own, for the private calibration vault.
5. Hosting choice for v1 (single VPS, home server, or cloud with GPU).

