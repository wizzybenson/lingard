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
import yaml

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "content" / "crs" / "draws.yaml"
SOURCE_URL = (
    "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/mandate/"
    "policies-operational-instructions-agreements/ministerial-instructions/express-entry-rounds.html"
)
DATA_URL = "https://www.canada.ca/content/dam/ircc/documents/json/ee_rounds_123_en.json"
KEEP_DAYS = 365


def render(rounds: list[dict[str, Any]], categories: dict[str, dict[str, Any]], today: date) -> str:
    """The YAML file: for each category (kept from the current file), its rounds of the last year, newest first."""
    since = (today - timedelta(days=KEEP_DAYS)).isoformat()
    lines = [
        "# Express Entry rounds whose cutoffs Draw Day uses (SPEC §18.3, decision 0024). A learner follows the first",
        "# category whose packs include one of their exams. Round lists are copied from IRCC's rounds data; refresh",
        "# them with tools/content_cli/draws (it keeps the categories and rewrites the rounds).",
        f"source_url: {SOURCE_URL}",
        f"data_url: {DATA_URL}",
        f'as_of: "{today.isoformat()}"',
        "categories:",
    ]
    for key, category in categories.items():
        name = str(category["round_name"])
        chosen = [r for r in rounds if name.lower() in r["drawName"].lower() and r["drawDate"] >= since]
        chosen.sort(key=lambda r: r["drawDate"], reverse=True)
        lines += [
            f"  {key}:",
            f"    round_name: {name}  # IRCC's round name contains this",
            f"    packs: [{', '.join(category['packs'])}]",
            "    draws:  # newest first",
        ]
        for r in chosen:
            number, held, cutoff, size = r["drawNumber"], r["drawDate"], r["drawCRS"], r["drawSize"].replace(",", "")
            lines.append(f'      - {{number: {number}, held_on: "{held}", cutoff: {cutoff}, invitations: {size}}}')
    return "\n".join(lines) + "\n"


def main() -> None:
    response = httpx.get(DATA_URL, timeout=60, follow_redirects=True)
    response.raise_for_status()
    categories = yaml.safe_load(TARGET.read_text())["categories"]
    TARGET.write_text(render(response.json()["rounds"], categories, date.today()))
    sys.stdout.write(f"wrote {TARGET.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
