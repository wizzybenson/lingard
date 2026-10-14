"""Build the correction-precision golden set from reviewed curriculum content (``python -m tools.content_cli.golden``).

Positives: each lesson's ``common_errors`` wrong sentence, with its node and correction. Negatives: the corrected
sentence and every lesson example, where a correct assessor must show NO correction. The seed is small; human-labelled
learner errors are appended to the same files as they are collected (SPEC §20 asks for ≥ 300 per language).
``<lang>.drafted.jsonl`` holds hand-drafted rows marked ``"reviewed": false`` until a native speaker checks them; a row
may list ``accept_node_keys`` when its error fits more than one node.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lingard_curriculum.seed import load_seed

ROOT = Path(__file__).resolve().parents[2]


def build(language: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for node in load_seed(ROOT / "content", language).nodes:  # type: ignore[arg-type]
        lesson = node.payload.get("lesson")
        if not isinstance(lesson, dict):
            continue
        for error in lesson.get("common_errors", []):
            rows.append(
                {
                    "text": error["wrong"],
                    "has_error": True,
                    "node_key": node.key,
                    "correction": error["right"],
                    "origin": "curriculum",
                }
            )
            rows.append({"text": error["right"], "has_error": False, "origin": "curriculum"})
        for example in lesson.get("examples", []):
            rows.append({"text": example, "has_error": False, "origin": "curriculum"})
    return rows


def main() -> None:
    for language in ("fr", "en"):
        rows = build(language)
        path = ROOT / "evals" / "datasets" / "correction_golden" / f"{language}.curriculum.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(f"{path.relative_to(ROOT)}: {len(rows)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
