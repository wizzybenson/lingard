# 0002: Phase gates are self-verified; no approval stops

- **Date:** 2026-10-14
- **Status:** accepted (founder decision)
- **Amends:** SPEC §0.1 ("founder has approved"), §0.5, §0.7, §25

The founder asked the implementing agent not to stop for approvals. Each phase proceeds when its gate is verified by
automated tests/evals, with evidence in `docs/gates/phase-N.md`. Where a gate needs something an agent can't produce
(real exam results, certified human raters, real phones, provider API keys), the gate file states exactly what was verified,
how, and what remains open. Nothing is claimed as passed when it wasn't measured.

Irreversible or outward-facing actions (pushing to GitHub, spending money, deleting data) still require explicit founder
consent.
