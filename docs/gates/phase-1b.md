# Phase 1b gate: English street (Ashford)

**Verdict: PASS offline, with defects logged.** The Phase 1 gates are language-agnostic offline, and the same
numbers apply (latency profile and Guard). The live measurements are outstanding for the same reason as Phase 1: no
provider keys.

## Content and config only?

Ashford was added as content: `content/cities/ashford/`, `content/curriculum/en/`, `content/languages/en.yaml`,
`content/packs/ielts_gt/`. The Phase 1b audit (a grep for language and city literals in `services/` and `packages/`)
found **language-specific code in 14 files**. All are fixed and logged in
[decision 0006](../decisions/0006-language-abstraction-defects.md). Two deliberate exceptions are recorded there: the
per-language conjugation engine, and the one registry where languages are declared.

## English-specific checks

- Guard rules for English (tutor markers, character-break and unsafe patterns) live in `content/languages/en.yaml`
  and are exercised by the `contract_adherence` suite, which plants violations in both languages.
- The language identifier (function-word voting) is tested on FR/EN mixes in `services/live/tests`.
- English placement is covered in Phase 2.

## Reproduce

```sh
grep -rnE '== "(fr|en)"|"(rivemont|ashford)"|\{"fr": ' services packages | grep '\.py:' | grep -v /tests/
uv run python -m evals.run --suite contract_adherence
```
