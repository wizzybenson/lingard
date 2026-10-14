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
