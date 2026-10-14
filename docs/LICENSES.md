# Third-party licence inventory

As of 2026-10-14. Built from installed package metadata (114 Python distributions, 931 npm packages), not from
memory. Lingard's own licence is still the founder's decision. Nothing below forces a particular choice, but the
**obligations** column must be honoured whichever licence is chosen.

## Needs attention

| Component | Licence | Where | Obligation |
| --- | --- | --- | --- |
| `psycopg`, `psycopg-binary`, `psycopg-pool` | LGPL-3.0-only | server (DB driver) | Used unmodified as a dynamically imported library: keep the licence notice and let users swap the library. No effect on Lingard's own licence. If the binary wheel is shipped inside an image, include the LGPL text |
| `av` (PyAV) wheels | BSD-3-Clause, but the wheels **bundle FFmpeg** (LGPL-2.1+) | server (speech decoding, `/v1/speech/transcribe`) | Same as above: ship the FFmpeg licence notice in server images. Don't build FFmpeg with `--enable-gpl` |
| `wordfreq` data | Code Apache-2.0; word-list **data CC BY-SA 4.0** | server (Contract Guard rare-word check) | Used at runtime, not redistributed. Attribution is needed if the data (or lists derived from it) is ever shipped in content or the app |
| `certifi`, `orjson` (part), `pathspec` | MPL-2.0 | server / tooling | File-level copyleft: only applies if those files are modified |
| `node-forge` | BSD-3-Clause OR GPL-2.0 | app tooling (Expo CLI) | Dual-licensed: we use it under BSD-3-Clause |
| Redis 7.4+ | RSALv2 / SSPLv1 (/ AGPLv3 from 8.0) | **avoided**: replaced by Valkey ([0007](decisions/0007-valkey-instead-of-redis.md)) | n/a |
| espeak / espeak-ng | GPL-3.0 | **avoided**: not a dependency (phonemisation uses our own lexicons in `content/pronunciation/`) | n/a |

## Permissive (no action beyond keeping notices)

- **Python (server):** FastAPI, Starlette, Pydantic, SQLAlchemy, Alembic, LangChain / LangGraph, `anthropic`, `fsrs`,
  PyJWT, `argon2-cffi`, `pgvector`, `redis` client and PyYAML (MIT). `livekit` SDKs, OpenTelemetry, `boto3`, `ftfy`
  and `msgpack` (Apache-2.0). NumPy, `httpx` and `uvicorn` (BSD-3-Clause).
- **App:** 25 of 28 direct dependencies MIT (Expo, React Native, Skia, expo-router and others). The LiveKit React
  Native SDKs are Apache-2.0. No GPL-only, AGPL, SSPL or CC BY-SA packages in the 931-package tree (node-forge is dual BSD/GPL, above). CI enforces
  this with `license-checker --failOn "GPL-3.0;AGPL-3.0"`.
- **Services (Docker):** PostgreSQL + pgvector (PostgreSQL licence), Valkey (BSD-3-Clause), LiveKit server
  (Apache-2.0), SeaweedFS (Apache-2.0), Langfuse v2 (MIT core).

## Optional components

- wav2vec2 phone recogniser (`services/pronunciation` extra): `transformers` and `torch` are Apache-2.0 / BSD-style.
  The default checkpoint is `facebook/wav2vec2-lv-60-espeak-cv-ft` (model card: Apache-2.0; its training labels came
  from espeak, but the model doesn't link espeak). **Re-check the licence of any checkpoint** before shipping it;
  some phoneme checkpoints are CC BY-NC.

## Content

Everything in `content/` is original (cities, NPCs, stories, items). External facts (CLB/NCLC tables, exam formats,
CRS grid) are factual data with `source_url` and `as_of`, not copied text. Official practice materials stay in
`vault/`, which is never committed.

## Re-check

```sh
uv run python -c "from importlib.metadata import distributions as d; [print(x.metadata['Name'], x.metadata.get('License-Expression') or x.metadata.get('License','')[:40]) for x in d()]"
cd apps/mobile && npx license-checker --production --summary
```
