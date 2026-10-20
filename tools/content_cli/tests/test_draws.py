from datetime import date
from pathlib import Path

from lingard_economy.events import load_draws
from tools.content_cli.draws import render

ROOT = Path(__file__).resolve().parents[3]


def _round(number: str, day: str, name: str, crs: str) -> dict[str, str]:
    return {"drawNumber": number, "drawDate": day, "drawName": name, "drawSize": "5,000", "drawCRS": crs}


def test_only_the_last_years_french_rounds_are_kept_newest_first(tmp_path: Path) -> None:
    rounds = [
        _round("400", "2026-03-01", "French-Language proficiency 2026-Version 2", "397"),
        _round("401", "2026-04-01", "Canadian Experience Class", "515"),
        _round("402", "2026-05-01", "French-Language proficiency 2026-Version 2", "409"),
        _round("300", "2025-01-01", "French language proficiency (Version 1)", "410"),
    ]
    path = tmp_path / "draws.yaml"
    path.write_text(render(rounds, date(2026, 10, 20)))
    draws = load_draws(path)
    assert [d.number for d in draws] == [402, 400]
    assert draws[0].cutoff == 409 and "canada.ca" in draws[0].note and "2026-10-20" in draws[0].note


def test_the_shipped_draws_carry_their_source() -> None:
    draws = load_draws(ROOT / "content" / "crs" / "draws.yaml")
    assert draws and all(300 <= d.cutoff <= 600 for d in draws)
    assert draws == sorted(draws, key=lambda d: d.held_on, reverse=True)
