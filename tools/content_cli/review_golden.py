"""Native-speaker review of drafted correction-golden rows.

Run: ``python -m tools.content_cli.review_golden fr --reviewer NAME``.

Walks the rows of ``evals/datasets/correction_golden/<lang>.drafted.jsonl`` still marked ``"reviewed": false`` and
asks for one decision per row. The file is rewritten after every decision, so quitting part-way loses nothing. Only
reviewed rows count towards the Phase 3 gate (≥ 300 per language, SPEC §20).

Decisions: ``a`` accept as is · ``c`` the row is right but the correction should read differently · ``f`` flip the
label (it's actually correct / actually wrong) · ``d`` delete (ambiguous, unnatural or register-dependent) · ``s`` skip
for now · ``q`` quit.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lingard_curriculum.seed import load_seed

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "evals" / "datasets" / "correction_golden"

Row = dict[str, Any]
Ask = Callable[[str], str]


def load(path: Path) -> list[Row]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def save(path: Path, rows: list[Row]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    tmp.replace(path)


def describe(row: Row) -> str:
    lines = [f"  {row['text']}"]
    if row["has_error"]:
        lines.append(f"  marked WRONG ({row['node_key']}) → {row['correction']}")
    else:
        lines.append("  marked CORRECT: the assessor must not correct it")
    if note := row.get("note"):
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def decide(row: Row, choice: str, ask: Ask, reviewer: str, nodes: frozenset[str] = frozenset()) -> Row | None:
    """Apply one decision. Returns the updated row, or ``None`` to delete it; ``ValueError`` if it can't apply."""
    stamp = {"reviewed": True, "reviewer": reviewer}
    if choice == "a":
        return {**row, **stamp}
    if choice == "c":
        if not row["has_error"]:
            raise ValueError("only rows marked wrong have a correction; use f to flip the label")
        return {**row, "correction": ask("corrected sentence: ").strip(), **stamp}
    if choice == "f":
        if row["has_error"]:
            flipped = {k: v for k, v in row.items() if k not in ("node_key", "accept_node_keys", "correction")}
            return {**flipped, "has_error": False, **stamp}
        node_key = ask("curriculum node key (e.g. fr.grammar.subjonctif_present): ").strip()
        if nodes and node_key not in nodes:
            raise ValueError(f"unknown node key {node_key!r}; the row is unchanged")
        correction = ask("corrected sentence: ").strip()
        return {**row, "has_error": True, "node_key": node_key, "correction": correction, **stamp}
    if choice == "d":
        return None
    raise ValueError("choose a, c, f, d, s or q")


def review(
    path: Path,
    reviewer: str,
    nodes: frozenset[str] = frozenset(),
    ask: Ask = input,
    out: Callable[[str], None] = print,
) -> int:
    """Interactive loop; returns how many rows were decided this run."""
    rows: list[Row | None] = list(load(path))
    pending = [i for i, r in enumerate(rows) if r is not None and r.get("reviewed") is False]
    decided = 0
    out(f"{len(pending)} rows to review in {path.name}. a accept · c correction · f flip · d delete · s skip · q quit")
    for n, index in enumerate(pending, 1):
        row = rows[index]
        assert row is not None
        out(f"\n[{n}/{len(pending)}]\n{describe(row)}")
        while True:
            choice = ask("> ").strip().lower()
            if choice in ("s", "q"):
                break
            try:
                rows[index] = decide(row, choice, ask, reviewer, nodes)
            except ValueError as exc:
                out(f"  {exc}")
                continue
            save(path, [r for r in rows if r is not None])
            decided += 1
            break
        if choice == "q":
            break
    remaining = sum(r is not None and r.get("reviewed") is False for r in rows)
    out(f"\n{decided} decided this run, {remaining} still unreviewed.")
    return decided


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("language", help="language code, e.g. fr or en")
    parser.add_argument("--reviewer", required=True, help="who is reviewing (recorded on each row)")
    args = parser.parse_args()
    path = FOLDER / f"{args.language}.drafted.jsonl"
    if not path.exists():
        sys.exit(f"no drafted rows for {args.language!r}: {path.relative_to(ROOT)} is missing")
    nodes = frozenset(n.key for n in load_seed(ROOT / "content", args.language).nodes)
    review(path, args.reviewer, nodes)


if __name__ == "__main__":
    main()
