# Phase 0 gate: audit and foundations

**Verdict: PASS** (with the founder's change of scope, below). Evidence collected 2026-10-14; gates are self-verified per
[decision 0002](../decisions/0002-gates-self-verified.md).

| Gate (SPEC §25) | Status | Evidence |
| --- | --- | --- |
| Founder approves REUSE_PLAN | PASS | [REUSE_PLAN.md](../REUSE_PLAN.md) approved. Scope: Simupatient only ([0003](../decisions/0003-reuse-scope-simupatient-only.md)) |
| Bake-off scorecard and voice decision recorded | WAIVED by founder | The founder removed the bake-off; LiveKit chosen and recorded in [0001](../decisions/0001-no-voice-bakeoff-livekit.md). Latency is checked offline by `tools/voicebench` instead (see Phase 1) |
| Auth tests incl. lockout pass | PASS | `services/api/tests/test_auth_flow.py` and `test_pin_policy.py`, below |

## Auth tests (all passing in `scripts/check.sh`, 173 Python tests total)

- `test_lockout_escalates_then_requires_admin_reset`: escalating lockout, then an admin reset is required
- `test_sign_in_and_generic_errors`: wrong name and wrong PIN give the same generic error (no account enumeration)
- `test_rate_limit_per_name`
- `test_refresh_rotation_and_reuse_detection`: a reused refresh token revokes the family
- `test_refresh_requires_pin_after_reverify_window`
- `test_invites_single_use_and_name_uniqueness`
- `test_change_pin_revokes_other_devices_and_ownership`, `test_learner_cannot_revoke_someone_elses_session`
- `test_weak_pins_rejected`, `test_generated_pins_are_strong`, `test_hasher_uses_argon2id_with_unique_salts`,
  `test_name_normalisation_is_unicode_and_case_insensitive`

## Foundations delivered

- Repo layout per SPEC §5: uv workspace (Python 3.12), `ruff` + `mypy --strict` clean, Expo app in `apps/mobile`.
- `packages/contracts`: shared Pydantic contracts (scene contract, events, assessments, planning, world).
- Tracing: `packages/telemetry` (OpenTelemetry), with a `trace_id` carried on every event and LLM call.
- CI: `.github/workflows/ci.yml` runs `scripts/check.sh`, the mobile `tsc` and `jest`, and the offline evals.

## Reproduce

```sh
bash scripts/check.sh
uv run pytest services/api/tests/test_auth_flow.py -q
```
