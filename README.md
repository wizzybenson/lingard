# Lingard

A simulated-world exam trainer for **IELTS General Training** (English, set in the town of Ashford) and **TEF Canada**
(French, set in the city of Rivemont). Learners live short scenes with characters who speak only the target language.
Behind the scenes, every turn is assessed, weaknesses become tickets, and the next day is planned around closing
them. Timed mocks convert to CLB/NCLC levels for Express Entry.

- Spec: [`docs/SPEC.md`](docs/SPEC.md). Amendments: [`docs/decisions/`](docs/decisions/).
- Where each phase stands, with evidence: [`docs/gates/`](docs/gates/).
- Working rules for contributors and agents: [`AGENTS.md`](AGENTS.md).

## Status (2026-10-14)

| Phase | Gate |
| --- | --- |
| 0 Foundations | pass |
| 1 / 1b French and English streets | pass offline. Live latency and elicitation not measured (no provider keys) |
| 2 Learning loop + placement | pass offline (synthetic learners, 20 runs; placement 30/30 within ±1 band) |
| 3 Exam Hall + writing | **blocked**: needs human-rated calibration samples and native review of the drafted correction golden set |
| 4 Accent studio | built, not measured |
| 5 Full city (v1) | needs real play: founder for 2 weeks, friends' retention, measured cost |

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Docker (Postgres + pgvector, Redis, LiveKit, SeaweedFS for object storage)
- Node 20+ for the Expo app

## Run it locally

```sh
uv sync
docker compose up -d postgres redis livekit objects
uv run python -m lingard_api.cli migrate
uv run python -m lingard_api.cli seed                     # curriculum graph for both languages
uv run python -m lingard_api.cli bootstrap-admin --name <you>   # prompts for a 6-digit PIN
uv run python -m lingard_api.cli reset-pin --name <you>         # forgot it: sets a new one (prompted)
uv run uvicorn lingard_api.main:app --host 127.0.0.1 --port 58000
```

Accent Studio scoring (optional; needs `uv sync --extra models` in `services/pronunciation` for the recogniser):

```sh
uv run uvicorn --factory lingard_pronunciation.server:build_app --host 127.0.0.1 --port 58100
# then start the API with PRONUNCIATION_URL=http://127.0.0.1:58100
```

App (web, iOS simulator or Android emulator):

```sh
cd apps/mobile
npm ci
EXPO_PUBLIC_API_URL=http://localhost:58000 npx expo start --web
```

Sign in with the admin name and PIN. To add learners, create a single-use invite with `POST /v1/admin/invites`
(there is no admin screen in the app yet; the API docs are at http://localhost:58000/docs). The learner redeems it
on the sign-in screen.

### Provider keys

Without keys, the LLM, speech-to-text and text-to-speech paths only run against scripted test models. Copy
`.env.example` to `.env` (never commit it) and fill in what you have. Each group uses the first provider that is
configured and falls back to the next configured one, so one key per group is enough:

| Group | Providers, in preference order |
| --- | --- |
| Language models (`config/llm.yaml`) | per tier, see below |
| Speech-to-text | `VOICEBOX_URL` → `DEEPGRAM_API_KEY` → `OPENAI_API_KEY` → `ELEVENLABS_API_KEY` |
| Text-to-speech | `VOICEBOX_URL` → `ELEVENLABS_API_KEY` → `OPENAI_API_KEY` |
| Voice clone and golden self | `VOICEBOX_URL` or `ELEVENLABS_API_KEY` (golden self: ElevenLabs only) |

Tests never use these keys: a root fixture clears them, so a filled-in `.env` can't make a test call a paid API.

### Choosing models

Every model is set in `.env`; `.env.example` lists the defaults. Leaving a variable blank keeps the default.

- `LLM_FAST_MODELS` (NPCs), `LLM_GUARD_MODELS` (the Contract Guard's claim check), `LLM_MID_MODELS` (assessment,
  planning), `LLM_COMPILE_MODELS` (scene compiling, waited on when a day starts) and `LLM_FRONTIER_MODELS` (examiners,
  judges) take catalog names, comma-separated, in preference order. A model is skipped when its provider has no key.
  `LLM_<TIER>_EFFORT` sets the reasoning effort. New models go in the catalog in `config/llm.yaml` with their price
  and source, so cost reporting always knows what a call costs.
- `STT_ORDER` and `TTS_ORDER` set the speech provider preference (JSON lists), and `<PROVIDER>_STT_MODEL`,
  `<PROVIDER>_TTS_MODEL`, `ELEVENLABS_STS_MODEL` and `LINGARD_PRON_MODEL` set each provider's model.
- `CLAIM_CHECK`, `CLAIM_CHECK_DEADLINE_S`, `CLAIM_CHECK_CONTEXT_LINES`, `CLAIM_FREE_WORDS` and `FILLER_AFTER_MS` tune
  the claim check and the hesitation that covers it (decision 0012).

Defaults (decision 0009): NPCs on `claude-haiku-5-5`, assessment on `claude-sonnet-5-5`, judges and examiners on
`gpt-6.1-sol`. Opus and Astra are in the catalog but in no tier.

## Checks

```sh
bash scripts/check.sh                       # ruff, mypy --strict, all Python tests
cd apps/mobile && npx tsc --noEmit && npx jest
uv run python -m evals.run                  # offline eval suites (results in evals/results/)
uv run python -m evals.run --live           # needs provider keys
uv run python -m tools.voicebench.probe --write-profile   # time the configured STT/TTS/LLM providers (needs keys)
uv run python -m tools.content_cli.review_golden fr --reviewer NAME   # native review of drafted golden rows
uv run python -m tools.content_cli.review_golden fr --machine         # LLM review instead (stopgap, needs a key)
uv run python -m tools.content_cli.art      # regenerate location artwork from the city files
```

## Layout

```
apps/mobile         Expo app (expo-router, Skia 2.5D map, LiveKit)
services/api        FastAPI: auth (name + PIN), world, sessions, learning, economy, privacy
services/live       real-time voice loop: endpointer, actor, Contract Guard, STT/TTS
services/graphs     LangGraph workers: day planner, turn assessment, night notebook, lessons, placement, exams
services/pronunciation  prosody, GOP scoring, golden self
packages/           contracts, llm router, memory, curriculum, exam packs, economy, world, storage, db, telemetry
content/            cities, curriculum, exam packs, CRS tables, per-language config (all original content)
evals/              eval suites and the synthetic-learner harness
```

## Licence

No licence has been chosen yet; that is the founder's decision. Third-party licences:
[`docs/LICENSES.md`](docs/LICENSES.md).
