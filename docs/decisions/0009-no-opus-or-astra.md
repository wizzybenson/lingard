# 0009: No Opus or Astra; Anthropic and OpenAI capped at 2 / 10 USD per million tokens

- **Date:** 2026-10-15
- **Status:** accepted (founder's instruction)

## Context

With only an OpenAI key set, the frontier tier (golden review, judges, examiners) fell through to `gpt-6-astra` at
10 / 50 USD per million tokens. A 5-row sample of `review_golden --machine` cost 0.144 USD, so the 438 drafted rows
would have cost about 12.60 USD. The founder said not to use Astra because it is too expensive.

## Decision

The OpenAI entry of the `frontier` tier in `config/llm.yaml` is `gpt-6.1-sol` with `effort: high` (2 / 10 USD per
million tokens, the same model the `mid` tier uses at medium effort). Anthropic and Google entries are unchanged.

Later the same day, with an Anthropic key added, the founder asked that Anthropic be no dearer than that OpenAI choice.
`claude-opus-5-5` (4 / 20 USD) is removed from both `mid` (a fallback) and `frontier` (first choice), so the frontier tier
then starts with `claude-sonnet-5-5`. No call had run on Opus.

The founder then set the final order: `gpt-6.1-sol` (high effort) leads the `frontier` tier in Opus's place, and NPCs
use `claude-haiku-5-5` with `gpt-6-luna` removed from the `fast` tier (Sonnet at low effort is the fallback). The
measured fast-tier first token: Haiku 785 ms, Luna 1,427 ms (2026-10-15 probe).

## Consequences

Frontier calls on OpenAI cost about a fifth as much. Judging quality on OpenAI may be lower than Astra; the machine
golden review is already a stopgap until native reviewers sign off, so this does not change any gate.

## Reverting

Put `gpt-6-astra` / `claude-opus-5-5` back in `config/llm.yaml` and in `packages/llm/tests/test_router.py`.
