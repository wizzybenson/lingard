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

Without keys, the LLM, speech-to-text and text-to-speech paths only run against scripted test models. Put keys in
`.env` (never commit it):

- `ANTHROPIC_API_KEY`: the fast/mid/frontier LLM tiers (`config/llm.yaml`)
- STT: `VOICEBOX_URL` (self-hosted) or `OPENAI_API_KEY`
- TTS: `VOICEBOX_URL`, `ELEVENLABS_API_KEY` or `OPENAI_API_KEY`

## Checks

```sh
bash scripts/check.sh                       # ruff, mypy --strict, all Python tests
cd apps/mobile && npx tsc --noEmit && npx jest
uv run python -m evals.run                  # offline eval suites (results in evals/results/)
uv run python -m evals.run --live           # needs provider keys
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
