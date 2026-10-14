# 0005: Seed curriculum ships pre-reviewed by the content seed

- **Date:** 2026-10-14
- **Status:** accepted (reversible default; follows decision 0002)
- **Amends:** SPEC §8.1 ("No node is used in scenes until `reviewed = true`")

The v1 curriculum seed (`content/curriculum/{fr,en}/`) was written by the implementing agent from the CLB/NCLC
documents and the official exam formats, in original wording. With no approval stops (decision 0002), seeded nodes are
loaded with `reviewed = true, reviewed_by = "seed:lingard-content-v1"` so scenes can be compiled.

Safeguards that stay in force:

- Any edit to a node's content bumps `version` and clears `reviewed` (tested), so edited nodes need review again.
- `/admin/curriculum` lists every node with its reviewer; the founder can un-review a node, which removes it from
  scene compilation immediately.
- LLM-drafted nodes (SPEC §8.1 drafting flow) are always stored `reviewed = false`.
