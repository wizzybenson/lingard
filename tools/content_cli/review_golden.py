"""Native-speaker review of drafted correction-golden rows.

Run: ``python -m tools.content_cli.review_golden fr --reviewer NAME``.

Walks the rows of ``evals/datasets/correction_golden/<lang>.drafted.jsonl`` still marked ``"reviewed": false`` and
asks for one decision per row. The file is rewritten after every decision, so quitting part-way loses nothing. Only
reviewed rows count towards the Phase 3 gate (≥ 300 per language, SPEC §20).

``--machine`` runs the same review with the frontier LLM tier instead of a person (``machine_review`` on each row,
``reviewed`` stays false: that flag means a native speaker checked it). Machine verdicts are a stopgap with a caveat:
the set measures an LLM assessor, so an LLM reviewer can share its blind spots. Rows it calls ambiguous get
``excluded: true`` and are left out of scoring, but stay in the file for a human to look at.

Decisions: ``a`` accept as is · ``c`` the row is right but the correction should read differently · ``f`` flip the
label (it's actually correct / actually wrong) · ``d`` delete (ambiguous, unnatural or register-dependent) · ``s`` skip
for now · ``q`` quit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from lingard_contracts.common import LANGUAGE_CITY, LANGUAGE_NAME
from lingard_curriculum.seed import load_seed
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry
from lingard_world import load_city

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


class MachineVerdict(BaseModel):
    verdict: Literal["accept", "fix", "flip", "delete"]
    correction: str | None = None
    node_key: str | None = None
    reason: str


def apply_verdict(row: Row, verdict: MachineVerdict, model: str, nodes: frozenset[str]) -> Row:
    """The row after a machine verdict; a fix or flip naming an unknown node is kept as a note, not applied."""
    note: dict[str, Any] = {"model": model, "verdict": verdict.verdict, "reason": verdict.reason}
    updated = {**row, "machine_review": note}
    wants_error = verdict.verdict == "fix" or (verdict.verdict == "flip" and not row["has_error"])
    if wants_error and (verdict.node_key not in nodes or not verdict.correction):
        note["verdict"], note["unapplied"] = "accept", verdict.model_dump()
        return updated
    if verdict.verdict == "fix":
        note["original"] = {"correction": row.get("correction"), "node_key": row.get("node_key")}
        return {**updated, "correction": verdict.correction, "node_key": verdict.node_key}
    if verdict.verdict == "flip" and row["has_error"]:
        kept = {k: v for k, v in updated.items() if k not in ("node_key", "accept_node_keys", "correction")}
        return {**kept, "has_error": False}
    if verdict.verdict == "flip":
        return {**updated, "has_error": True, "correction": verdict.correction, "node_key": verdict.node_key}
    if verdict.verdict == "delete":
        return {**updated, "excluded": True}
    return updated


async def machine_review(
    path: Path, language: str, router: LLMRouter, prompts: PromptRegistry, nodes: frozenset[str], region: str
) -> dict[str, int]:
    """Reviews every unreviewed row without a machine verdict yet; saves after each one. Returns verdict counts."""
    prompt = prompts.get("golden_review")
    model = router.specs("frontier")[0].model
    rows = load(path)
    counts: dict[str, int] = {}
    for i, row in enumerate(rows):
        if row.get("reviewed") is not False or "machine_review" in row:
            continue
        label = "WRONG (the learner made a mistake)" if row["has_error"] else "CORRECT (no correction allowed)"
        detail = f"Expected correction: {row['correction']} (node {row['node_key']})" if row["has_error"] else ""
        system, per_call = prompt.render_split(
            language_name=LANGUAGE_NAME[language],
            region=region,
            label=label,
            detail=detail,
            candidate_nodes=", ".join(sorted(nodes)),
            text=row["text"],
        )
        verdict = await router.structured(
            "frontier", prompt, MachineVerdict, router.messages("frontier", system, per_call)
        )
        rows[i] = apply_verdict(row, verdict, model, nodes)
        counts[rows[i]["machine_review"]["verdict"]] = counts.get(rows[i]["machine_review"]["verdict"], 0) + 1
        save(path, rows)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("language", help="language code, e.g. fr or en")
    parser.add_argument("--reviewer", help="who is reviewing (recorded on each row)")
    parser.add_argument("--machine", action="store_true", help="review with the frontier LLM tier (needs an LLM key)")
    args = parser.parse_args()
    path = FOLDER / f"{args.language}.drafted.jsonl"
    if not path.exists():
        sys.exit(f"no drafted rows for {args.language!r}: {path.relative_to(ROOT)} is missing")
    nodes = frozenset(n.key for n in load_seed(ROOT / "content", args.language).nodes)
    if args.machine:
        load_dotenv()
        router = LLMRouter(LLMConfig.load(ROOT / "config" / "llm.yaml"))
        region = load_city(ROOT / "content", LANGUAGE_CITY[args.language]).city.country
        counts = asyncio.run(
            machine_review(path, args.language, router, PromptRegistry(ROOT / "prompts"), nodes, region)
        )
        print(f"machine verdicts: {counts}; spend: {router.sink.total_cost():.2f} USD", file=sys.stderr)  # type: ignore[attr-defined]
        return
    if not args.reviewer:
        sys.exit("--reviewer NAME is required for a human review (or pass --machine)")
    review(path, args.reviewer, nodes)


if __name__ == "__main__":
    main()
