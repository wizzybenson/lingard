# 0007: Valkey instead of Redis for the queue and cache

- **Date:** 2026-10-14
- **Status:** accepted (reversible default, per AGENTS.md rule 4)

## Context

The compose file used `redis:7.4-alpine`. From 7.4, Redis is licensed RSALv2 / SSPLv1 (8.0 adds AGPLv3 as a third
option). Self-hosting it is allowed, but offering Lingard to institutions as a hosted service would push the SSPL and
AGPL terms into scope, which complicates the licence choice the founder still has to make.

## Decision

Use **Valkey** (`valkey/valkey:8.1-alpine`, BSD-3-Clause), the Linux Foundation fork of Redis 7.2. It speaks the same
protocol, so the `redis` Python client (MIT) and the code are unchanged.

## Verified

Streams (`XADD`/`XLEN`), ping and `uv run pytest -m integration` all ran against Valkey 8.1.10 on 2026-10-14.

## Reverting

Change the image back. No code depends on Valkey-specific features.
