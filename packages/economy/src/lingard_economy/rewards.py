"""Stars, coins and the append-only ledger (SPEC §18.2). Nothing purchasable skips learning or assessment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Currency = Literal["coins", "stars"]
SHOP = {
    "flat_upgrade": 400,
    "avatar_item": 120,
    "cafe_visit": 30,
    "flight_between_cities": 250,
    "npc_gift": 60,
    "extra_accent_voice": 300,
}
"""Coin prices. Every item is cosmetic or narrative; none changes assessment, gates or the learner model."""
COINS = {
    "quest_complete": 40,
    "mission_accomplished": 30,
    "mission_partial": 10,
    "lesson_complete": 25,
    "streak_day": 10,
    "draw_invitation": 150,
    "mock_complete": 80,
}
"""Coins per reason. A mission pays ``quest_complete`` for being played and a bonus for how it went."""


@dataclass(frozen=True)
class LedgerEntry:
    currency: Currency
    delta: int
    reason: str
    ref_id: str
    idempotency_key: str


@dataclass
class Wallet:
    coins: int = 0
    stars_total: int = 0
    stars_by_level: dict[str, int] = field(default_factory=dict)
    entries: list[LedgerEntry] = field(default_factory=list)
    _keys: set[str] = field(default_factory=set)

    def apply(self, entry: LedgerEntry) -> bool:
        """Idempotent on ``idempotency_key``; refuses overdrafts."""
        if entry.idempotency_key in self._keys:
            return False
        if entry.currency == "coins" and self.coins + entry.delta < 0:
            raise ValueError("insufficient coins")
        self._keys.add(entry.idempotency_key)
        self.entries.append(entry)
        if entry.currency == "coins":
            self.coins += entry.delta
        else:
            self.stars_total += entry.delta
        return True


def stars_for_margin(margin: float, step: float) -> int:
    """1–3 stars by how far the demonstrated level clears the gate (in score steps)."""
    if margin < 0:
        return 0
    if margin >= 2 * step:
        return 3
    return 2 if margin >= step else 1


def award_stars(
    wallet: Wallet, level_key: str, stars: int, *, confidence: float, min_confidence: float, ref_id: str
) -> LedgerEntry | None:
    """Stars once per level, re-earnable upward only, and only on high-confidence assessment (SPEC §18.3)."""
    if confidence < min_confidence:
        return None
    previous = wallet.stars_by_level.get(level_key, 0)
    if stars <= previous:
        return None
    entry = LedgerEntry("stars", stars - previous, f"level:{level_key}", ref_id, f"stars:{level_key}:{stars}")
    if wallet.apply(entry):
        wallet.stars_by_level[level_key] = stars
        return entry
    return None


def earn(wallet: Wallet, reason: str, ref_id: str) -> LedgerEntry | None:
    entry = LedgerEntry("coins", COINS[reason], reason, ref_id, f"coins:{reason}:{ref_id}")
    return entry if wallet.apply(entry) else None


def spend(wallet: Wallet, item: str, ref_id: str) -> LedgerEntry:
    entry = LedgerEntry("coins", -SHOP[item], f"shop:{item}", ref_id, f"spend:{item}:{ref_id}")
    wallet.apply(entry)
    return entry
