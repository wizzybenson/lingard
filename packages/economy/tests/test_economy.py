from datetime import date, timedelta
from pathlib import Path

import pytest

from lingard_economy.crs import CrsInputs, LanguageLevels, compute
from lingard_economy.events import draw_day, landing_day_unlocked, league, streak
from lingard_economy.rewards import SHOP, Wallet, award_stars, earn, spend, stars_for_margin

GRID = Path(__file__).resolve().parents[3] / "content/crs/crs_grid.yaml"
ALL = ("listening", "reading", "writing", "speaking")


def levels(n: int) -> dict[str, int]:
    return dict.fromkeys(ALL, n)


def test_single_applicant_worked_example() -> None:
    """Hand-computed from the IRCC grid: age 30, master's, 3 yrs foreign work, CLB 9 English, NCLC 7 French."""
    inputs = CrsInputs(age=30, education="masters", foreign_work_years=3)
    result = compute(inputs, LanguageLevels(first=levels(9), first_is_french=False, second=levels(7)), GRID)
    assert result.core == {
        "age": 105,
        "education": 135,
        "first_language": 124,
        "second_language": 12,
        "canadian_work": 0,
    }
    assert result.transferability["education"] == 50  # master's + CLB 9 all
    assert result.transferability["foreign_work"] == 50  # 3+ yrs + CLB 9 all
    assert result.transferability["capped_total"] == 100
    assert result.additional["french"] == 50  # NCLC 7 all + CLB 5+ all
    assert result.total == 105 + 135 + 124 + 12 + 100 + 50


def test_french_first_language_bonus_without_english() -> None:
    inputs = CrsInputs(age=29, education="bachelors")
    result = compute(inputs, LanguageLevels(first=levels(7), first_is_french=True), GRID)
    assert result.additional["french"] == 25
    assert result.core["first_language"] == 4 * 17


def test_spouse_columns_and_caps() -> None:
    inputs = CrsInputs(
        age=35,
        education="phd",
        has_spouse_coming=True,
        spouse_education="bachelors",
        spouse_language_clb=levels(9),
        spouse_canadian_work_years=7,
        canadian_work_years=2,
    )
    result = compute(inputs, LanguageLevels(first=levels(10), first_is_french=False), GRID)
    assert result.core["age"] == 70 and result.core["education"] == 140 and result.core["first_language"] == 128
    assert result.spouse == {"education": 8, "language": 20, "canadian_work": 10}
    assert result.core["canadian_work"] == 46
    assert "not an official assessment" in result.disclaimer


def test_wallet_idempotent_no_overdraft_and_stars_upward_only() -> None:
    wallet = Wallet()
    assert earn(wallet, "quest_complete", "scene-1") is not None
    assert earn(wallet, "quest_complete", "scene-1") is None
    with pytest.raises(ValueError):
        spend(wallet, "flat_upgrade", "x")
    assert award_stars(wallet, "rivemont.vieux_port", 2, confidence=0.9, min_confidence=0.8, ref_id="m1")
    assert award_stars(wallet, "rivemont.vieux_port", 1, confidence=0.9, min_confidence=0.8, ref_id="m2") is None
    assert award_stars(wallet, "rivemont.vieux_port", 3, confidence=0.5, min_confidence=0.8, ref_id="m3") is None
    assert award_stars(wallet, "rivemont.vieux_port", 3, confidence=0.9, min_confidence=0.8, ref_id="m4")
    assert wallet.stars_total == 3
    assert stars_for_margin(-0.5, 0.5) == 0 and stars_for_margin(1.0, 0.5) == 3
    assert all(price > 0 for price in SHOP.values())


def test_draw_streak_league_landing() -> None:
    assert draw_day(431, 420).invited and not draw_day(410, 420).invited
    today = date(2026, 10, 14)
    days = [today - timedelta(days=d) for d in (0, 1, 2, 4, 5)]
    assert streak(days, today) == (5, 1, [])
    friday = date(2026, 10, 16)  # Thursday and Tuesday missed in the same week: the free freeze covers only one
    week = [friday - timedelta(days=d) for d in (0, 2, 4, 5)]
    tuesday = date(2026, 10, 13)
    assert streak(week, friday) == (2, 1, [])
    assert streak(week, friday, spare=1) == (4, 2, [tuesday]), "a bought freeze covers the second miss"
    assert streak(week, friday, covered=frozenset({tuesday})) == (4, 2, []), "spent once, covered for good"
    assert league({"a": 12, "b": 30, "c": 50}, {"a", "b"}) == [("b", 30), ("a", 12)]
    good = {"ielts_gt": True, "tef_canada": True}
    assert landing_day_unlocked([good, good, good])
    assert not landing_day_unlocked([good, good, {"ielts_gt": True, "tef_canada": False}, good])
