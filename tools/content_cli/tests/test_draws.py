from datetime import date
from pathlib import Path

from lingard_economy.events import draw_category, load_draws
from tools.content_cli.draws import render

ROOT = Path(__file__).resolve().parents[3]
CATEGORIES = {
    "french": {"round_name": "French", "packs": ["tef_canada"]},
    "cec": {"round_name": "Canadian Experience Class", "packs": ["ielts_gt"]},
}


def _round(number: str, day: str, name: str, crs: str) -> dict[str, str]:
    return {"drawNumber": number, "drawDate": day, "drawName": name, "drawSize": "5,000", "drawCRS": crs}


def test_each_category_keeps_its_last_year_of_rounds_newest_first(tmp_path: Path) -> None:
    rounds = [
        _round("400", "2026-03-01", "French-Language proficiency 2026-Version 2", "397"),
        _round("401", "2026-04-01", "Canadian Experience Class", "515"),
        _round("402", "2026-05-01", "French-Language proficiency 2026-Version 2", "409"),
        _round("403", "2026-05-02", "Provincial Nominee Program", "700"),
        _round("300", "2025-01-01", "French language proficiency (Version 1)", "410"),
    ]
    path = tmp_path / "draws.yaml"
    path.write_text(render(rounds, CATEGORIES, date(2026, 10, 20)))
    draws = load_draws(path)
    assert [(d.category, d.number) for d in draws] == [("french", 402), ("french", 400), ("cec", 401)]
    assert draws[0].cutoff == 409 and "canada.ca" in draws[0].note and "2026-10-20" in draws[0].note


def test_the_learners_exams_choose_the_category() -> None:
    path = ROOT / "content" / "crs" / "draws.yaml"
    assert draw_category(path, {"tef_canada", "ielts_gt"}) == "french", "French-language rounds come first"
    assert draw_category(path, {"ielts_gt"}) == "cec"
    assert draw_category(path, set()) is None


def test_the_shipped_draws_carry_their_source() -> None:
    draws = load_draws(ROOT / "content" / "crs" / "draws.yaml")
    assert {d.category for d in draws} == {"french", "cec"}
    assert all(300 <= d.cutoff <= 700 for d in draws)
    for category in ("french", "cec"):
        mine = [d for d in draws if d.category == category]
        assert mine == sorted(mine, key=lambda d: d.held_on, reverse=True)
