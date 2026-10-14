# Band calibration data (SPEC §20 `band_calibration`)

One JSON object per line in `<pack>.<skill>.jsonl`:

```json
{"id": "...", "pack": "ielts_gt", "skill": "writing", "task": "task1_letter", "prompt": "...", "response": "...",
 "human_scores": [7.0, 6.5], "rater_ids": ["r1", "r2"], "consent": true}
```

- Responses come from consenting learners (founder and friends) or from the private calibration vault; vault items stay
  in `vault/` (gitignored) and are referenced by id only.
- At least two certified raters per sample; the gate uses the mean human score.
- Until at least 30 samples per pack and skill exist, the suite reports "insufficient data" instead of a pass.

## Synthetic sanity samples (`*.synthetic.jsonl`)

Original responses written to a target level (`target_band`: IELTS band, or NCLC level for TEF) from the published
level descriptors, marked `"origin": "synthetic"`. They are **not human-rated** and never count toward the gate. In
live mode they report `synthetic_rank_corr` (does the examiner rank weaker scripts below stronger ones?) and
`synthetic_mae` (distance from the intended level) as a smoke test of the scoring pipeline.

Public human-scored data that could replace them, if its licence suits (accepting a licence is the founder's call):
- Write & Improve 2024 (Cambridge): ~23k CEFR-labelled English essays; non-commercial research licence; its terms
  ask that the essays not be sent to hosted LLMs without no-retention terms.
- TCFLE-8: ~6.5k French TCF essays, each scored by two raters; availability and licence to confirm.
- speechocean762: English read speech with human pronunciation scores, CC BY 4.0 (for the Accent Studio).
