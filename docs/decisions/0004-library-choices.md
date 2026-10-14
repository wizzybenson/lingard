# 0004: Reversible library and tooling defaults

- **Date:** 2026-10-14
- **Status:** accepted (reversible default, SPEC §0.7)

| Area | Choice | Reason |
| --- | --- | --- |
| Python workspace | `uv` workspace, Python 3.12 | one lockfile; fast; members per package/service |
| JWT | `PyJWT` | python-jose is poorly maintained |
| PIN hashing | `argon2-cffi` (Argon2id) | SPEC §23.2; passlib unmaintained |
| ORM / migrations | SQLAlchemy 2 (async, psycopg 3) + Alembic | matches Simupatient patterns |
| Background work | Redis Streams consumers + LangGraph workers; no RQ | SPEC §5.3, §11 |
| Spaced repetition | `fsrs` (open-spaced-repetition, MIT) | reference FSRS implementation |
| LLM | LangChain (`langchain-anthropic`, optional `langchain-openai`) via `packages/llm` | locked decision |
| Default tiers | fast = `claude-haiku-5-5`, mid = `claude-sonnet-5-5`, frontier = `claude-opus-5-5` | verified 2026-10-14 (Anthropic model table cached 2026-10-06) |
| TS types | JSON Schema from Pydantic → `json-schema-to-typescript` | SPEC §5.2 contracts |
| Client rendering | `@shopify/react-native-skia` | SPEC §19.2 |
| Lifted file header | `# Lifted from simupatient@69e1bd5:<path>` | REUSE_PLAN |
