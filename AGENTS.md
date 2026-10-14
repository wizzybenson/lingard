# Lingard — agent guide

Lingard is a simulated-world exam trainer for **IELTS General Training** (English, city "Ashford") and **TEF Canada**
(French, city "Rivemont"). The spec is `docs/SPEC.md`. Decisions that amend it are in `docs/decisions/` and take precedence
over the spec where they conflict.

## Working rules

1. **Never stop for approval at phase gates.** Verify each gate with tests and evals, write the evidence to
   `docs/gates/phase-N.md`, and carry on (decision 0002). Only pause for irreversible or outward actions: pushing,
   spending money, deleting data.
2. **No voice bake-off.** The transport is LiveKit, plus `LoopbackTransport` for tests (decision 0001).
3. **Reuse source is Simupatient only** (`../simupatient`, read-only, never modified). Lifted files start with
   `# Lifted from simupatient@69e1bd5:<path>` and get a row in `docs/REUSE_PLAN.md`.
4. **Reversible choice → pick a sensible default, record it in `docs/decisions/NNNN-<topic>.md`, continue.**
   A locked decision (SPEC §2) that evidence says is wrong → write `docs/decisions/CHALLENGE-<topic>.md`.
5. **Time-sensitive facts** (model IDs, prices, exam formats, CLB/NCLC tables, CRS grid) are verified when implemented,
   and every stored external fact carries `source_url` and `as_of`.
6. **Never commit** secrets, learner audio, voice embeddings, PINs or `vault/` content.
7. **Language-agnostic code.** Anything French- or English-specific lives in per-language config or content under
   `content/`, never in code branches. Phase 1b (English) must need no code changes.
8. **Report honestly.** If a gate can't be measured here (no API keys, no real phone, no human raters), say what was
   verified and what is still open. Never claim a pass that wasn't measured.

## Layout

```
apps/mobile/            Expo app (iOS, Android, web)
services/api            FastAPI REST + WS, auth, world API          import: lingard_api
services/live           VoiceTransport, Actor, Contract Guard        import: lingard_live
services/graphs         LangGraph workers                            import: lingard_graphs
services/pronunciation  alignment, GOP, prosody, golden self         import: lingard_pronunciation
packages/contracts      shared Pydantic schemas (TS generated)       import: lingard_contracts
packages/llm            LangChain router, fast/mid/frontier tiers    import: lingard_llm
packages/agent-memory   framework-agnostic memory library            import: agent_memory
packages/curriculum     CurriculumGraph, pack loader, CLB/NCLC       import: lingard_curriculum
packages/exam_packs     IELTS GT + TEF Canada packs, generators      import: lingard_exam_packs
packages/economy        simulated CRS, stars, coins, ledger          import: lingard_economy
content/                cities, packs, CRS tables (YAML, original content only)
evals/                  eval suites + synthetic learners
tools/                  voicebench, content_cli, admin_scripts
prompts/                versioned prompt files (every LLM call logs its prompt version)
```

Each Python member uses a `src/` layout with `tests/` next to it.

## Commands

```bash
uv sync                                   # install the whole workspace (Python 3.12)
uv run pytest                             # all Python tests (integration tests skip without docker services)
uv run pytest -m integration              # needs: docker compose up -d postgres redis
uv run ruff check . && uv run ruff format --check .
uv run mypy packages services             # --strict is configured in pyproject.toml
docker compose up -d                      # local stack (postgres+pgvector, redis, SeaweedFS "objects", langfuse, livekit)
cd apps/mobile && npm test && npx tsc --noEmit
```

## Code standards

- Python 3.12, type hints everywhere, Pydantic v2, `ruff` + `mypy --strict` must stay clean. TypeScript `strict`.
- Small modules, tests alongside code, no dead code. Match the surrounding code's style and comment density.
- Model tiers are config keys (`fast`/`mid`/`frontier`), never hard-coded model IDs in call sites.
- LLM-dependent tests use recorded or fake chat models. CI never calls a real provider.
- World memory and pedagogical memory never mix. NPCs only see pedagogy through scene contracts.
- Corrections reach the learner only at confidence ≥ 0.85 plus an agreeing second check (SPEC §12.3).
