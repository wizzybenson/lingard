"""CLI: ``python -m evals.run [--suite NAME ...] [--live] [--changed-only --base REF]``. Exit 1 on any failed gate."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys

from dotenv import load_dotenv

import evals.suites  # noqa: F401  (registers suites)
from evals.framework import REGISTRY, Mode, SuiteResult


def changed_paths(base: str) -> list[str]:
    output = subprocess.run(  # noqa: S603 - fixed argv, only the git ref is variable
        ["git", "diff", "--name-only", f"{base}...HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in output.stdout.splitlines() if line]


async def run_suites(names: list[str], mode: Mode) -> list[SuiteResult]:
    results = []
    for name in names:
        suite = REGISTRY[name]
        if suite.live_only and mode == "offline":
            continue
        result = await suite.run(mode)
        result.save()
        print(f"[{result.status}] {name} ({mode}) {result.metrics}")
        for failure in result.failures():
            print(f"    gate failed: {failure}")
        for note in result.notes:
            print(f"    note: {note}")
        results.append(result)
    return results


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", action="append", default=[])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--changed-only", action="store_true")
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args()
    names = args.suite or sorted(REGISTRY)
    if args.changed_only:
        changed = changed_paths(args.base)
        names = [n for n in names if any(p.startswith(w) for p in changed for w in REGISTRY[n].watches)]
    results = asyncio.run(run_suites(names, "live" if args.live else "offline"))
    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
