"""Refresh ``content/crs/draws.yaml`` from IRCC's Express Entry rounds data (Draw Day cutoffs, SPEC §18.3).

Run: ``python -m tools.content_cli.draws`` (free: one download from canada.ca), then
``python -m lingard_api.cli seed`` to load new rounds into the ``draws`` table.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "content" / "crs" / "draws.yaml"
SOURCE_URL = (
    "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/mandate/"
    "policies-operational-instructions-agreements/ministerial-instructions/express-entry-rounds.html"
)
DATA_URL = "https://www.canada.ca/content/dam/ircc/documents/json/ee_rounds_123_en.json"
CATEGORY = "French-language proficiency"
KEEP_DAYS = 365


def render(rounds: list[dict[str, Any]], today: date) -> str:
    """The YAML file for the French-language rounds of the last year, newest first."""
    since = (today - timedelta(days=KEEP_DAYS)).isoformat()
    french = [r for r in rounds if "french" in r["drawName"].lower() and r["drawDate"] >= since]
    french.sort(key=lambda r: r["drawDate"], reverse=True)
    lines = [
        "# Express Entry rounds in the French-language proficiency category: the Draw Day cutoffs (SPEC §18.3).",
        "# Copied from IRCC's rounds data; refresh with tools/content_cli/draws (rewrites this file from the source).",
        f"source_url: {SOURCE_URL}",
        f"data_url: {DATA_URL}",
        f'as_of: "{today.isoformat()}"',
        f"category: {CATEGORY}",
        "draws:  # newest first",
    ]
    for r in french:
        number, held, cutoff, size = r["drawNumber"], r["drawDate"], r["drawCRS"], r["drawSize"].replace(",", "")
        lines.append(f'  - {{number: {number}, held_on: "{held}", cutoff: {cutoff}, invitations: {size}}}')
    return "\n".join(lines) + "\n"


def main() -> None:
    response = httpx.get(DATA_URL, timeout=60, follow_redirects=True)
    response.raise_for_status()
    TARGET.write_text(render(response.json()["rounds"], date.today()))
    sys.stdout.write(f"wrote {TARGET.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
