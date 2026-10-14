# 0006: Language-abstraction defects found by the Phase 1b audit

- **Date:** 2026-10-14
- **Status:** fixed
- **Context:** SPEC §25 Phase 1b: adding English should be content and config only, and any code change needed for it is a
  defect in Phase 1's language abstraction, to be logged here.

## How they were found

A grep of `services/` and `packages/` for `== "fr"`, `== "en"`, `{"fr": `, `"rivemont"` and `"ashford"` outside tests.

## Defects and fixes

| Where | Defect | Fix |
| --- | --- | --- |
| `lesson_builder.py` | School names hard-coded per city | `school:` field in `content/cities/<city>/city.yaml`, on the `City` contract |
| `lesson_builder.py`, `placement.py` | `"French" if … else "English"` for prompt language names | `LANGUAGE_NAME` registry in `lingard_contracts.common` |
| `placement.py`, `routes/learning.py` | Language → city mapping written inline | `LANGUAGE_CITY` registry in `lingard_contracts.common` |
| `day_planner.py` `pack_alignment` | Exam speaking-part ids hard-coded per language | `scene_alignment:` in each `content/packs/<pack>/pack.yaml` |
| `routes/glance.py` | Quest prompt string in code per language | `choose_correct_prompt:` in `content/languages/<lang>.yaml` |
| `contracts/scene.py` | Accent prefix chosen by an if/else | Derived from the language code |
| `exam_hall.py` | Landing Day flag set only in Rivemont, although the finale spans both packs | Set in every city |
| `routes/speech.py` | STT locales and narrator voice ids per language in code | `stt_locale` / `narrator_voice` in `content/languages/<lang>.yaml` |
| actor, assessor, scene compiler, coach, exam generator, exam hall | 6 private copies of the language-name map and 4 of the NCLC/CLB scale map | `LANGUAGE_NAME` / `LANGUAGE_SCALE` in `lingard_contracts.common` |
| `writing.py`, `exam_hall.py` | Score-scale wording per pack in code | `scale_description:` in each `pack.yaml` |

## Deliberate exceptions (not defects)

- `lingard_curriculum.conjugation.FrenchConjugator` and the conjugation-duel game: morphology engines are per-language
  code by nature. Adding a language with rich verb morphology means adding an engine, not editing the loop.
- `lingard_contracts.common` registries (`CITY_LANGUAGE`, `LANGUAGE_PACK`, `LANGUAGE_CITY`, `LANGUAGE_NAME`, `LANGUAGE_SCALE`, the
  `Language` literal): this is the single place a new language is registered.
