# 0019: The full range of both exams, authored, part by part

- **Date:** 2026-10-20
- **Status:** accepted (reversible)

## Context

The founder: "make sure it captures the full range of the exams", "get all the info you need online, reputable
sources". The item bank held 12 single-question multiple-choice items per skill. A mock topped up its 40-question
sections with LLM-generated items when it started (slow and paid every time). IELTS question types (gap-fills with
word limits, True/False/Not Given, matching headings, map labelling, multi-select…) could not be expressed at all.

Verified on 2026-10-20:
- IELTS GT (ielts.org format pages): Listening 4 parts × 10, heard once; Reading 3 sections, 40 questions,
  2,150–2,375 words; the official lists of question types and word-limit rules.
- TEF Canada (CCIP « le français des affaires » page, 2023 change notice, 2026 handbook): CE 40 questions in 60 min,
  free navigation and auto-submit; CO 40 in 40 min, forward only; EE A ≥ 80 words (25 min) and B ≥ 200 words (35 min);
  EO A "obtenir des renseignements" (5 min) and B "présenter un document, argumenter pour convaincre" (10 min).
  The publisher lists the activity types but not per-activity counts, so the split in `pack.yaml` is ours.
- IRCC's NCLC and CLB tables are unchanged (TEF still uses the "équivalence ancien score" column).

## Decision

- **Items** can share a text or recording (`set_id`), be answered by one option, several (`multi`), or typed words
  (`text`, with `accepted` spellings and the official `word_limit`, where a number is not a word). They also carry
  `part`, per-question `instructions`, a monospace `figure` (plans, charts, diagrams), `shuffle: false` for
  T/F/NG and letter lists, and `plays` (TEF interviews are heard twice).
- **Pack blueprints** list each receptive section's parts, with question counts that must add up to the official
  total and the task types each part uses. A content test makes sure the bank fills every part and covers every
  listed type.
- **Content:** two complete IELTS papers (A and B, 160 questions) covering every official question type, and one
  complete TEF paper (80 questions) across all eight activity types. Everything is original. Speaking and writing
  tasks for mocks come from authored prompt files.
- **Exam Hall** assembles each part from whole sets in the bank, picked afresh each attempt. The LLM only tops up a part
  the bank can't fill, and only generates tasks when the prompt files are missing. A mock now starts instantly and
  costs nothing until the writing and speaking are scored. A set is one screen and one round trip.
- **Listening audio:** scripts tag speakers (`M1:`, `F2:`) and each gets a stable voice of that gender. Rendered audio
  is cached in object storage by provider and text, so each recording is synthesised once.

## Still open

- TEF speaking in a mock is recorded as a monologue; the real Section A/B is an interaction with an examiner.
- (Done the same day: TEF paper B, so both exams have two complete papers and mocks mix them part by part.)
- IELTS Reading lets candidates move between sections; here a set is answered before the next appears.
