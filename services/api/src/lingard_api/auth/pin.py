"""PIN policy and hashing (SPEC §23.2). PINs are never logged or traced."""

from __future__ import annotations

import itertools
import secrets
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

PIN_LENGTH = 6


class WeakPinError(ValueError):
    pass


def normalise_name(display_name: str) -> str:
    """Unicode NFKC + case folding + collapsed whitespace: the uniqueness key for display names."""
    return " ".join(unicodedata.normalize("NFKC", display_name).casefold().split())


def validate_display_name(display_name: str) -> str:
    cleaned = " ".join(unicodedata.normalize("NFKC", display_name).split())
    if not 2 <= len(cleaned) <= 40:
        raise ValueError("display name must be 2–40 characters")
    if any(unicodedata.category(c).startswith("C") for c in cleaned):
        raise ValueError("display name contains control characters")
    return cleaned


def pin_weakness(pin: str) -> str | None:
    """Reason the PIN is weak, or None. Rejects repeats, sequences and near-repeats."""
    if len(pin) != PIN_LENGTH or not pin.isascii() or not pin.isdigit():
        return "PIN must be exactly 6 digits"
    digits = [int(c) for c in pin]
    if len(set(digits)) <= 2:
        return "PIN uses too few different digits"
    steps = {(b - a) % 10 for a, b in itertools.pairwise(digits)}
    if steps in ({1}, {9}):
        return "PIN is a sequence"
    if pin[:3] == pin[3:]:
        return "PIN repeats itself"
    doubled = pin[0] == pin[1] and pin[2] == pin[3] and pin[4] == pin[5]
    if doubled or pin[:3] == pin[3:][::-1]:
        return "PIN follows a simple pattern"
    return None


def ensure_strong(pin: str) -> None:
    reason = pin_weakness(pin)
    if reason:
        raise WeakPinError(reason)


def generate_pin() -> str:
    while True:
        pin = f"{secrets.randbelow(10**PIN_LENGTH):06d}"
        if pin_weakness(pin) is None:
            return pin


class PinHasher:
    """Argon2id with per-hash random salt. Tune parameters to ~250 ms on server hardware."""

    def __init__(self, time_cost: int, memory_kib: int, parallelism: int) -> None:
        self._hasher = PasswordHasher(time_cost=time_cost, memory_cost=memory_kib, parallelism=parallelism)
        self._dummy = self._hasher.hash(generate_pin())

    def hash(self, pin: str) -> str:
        return self._hasher.hash(pin)

    def verify(self, pin_hash: str, pin: str) -> bool:
        try:
            return self._hasher.verify(pin_hash, pin)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def burn(self, pin: str) -> None:
        """Spend the same time as a real verification, so unknown names are not revealed by timing."""
        self.verify(self._dummy, pin)

    def needs_rehash(self, pin_hash: str) -> bool:
        return self._hasher.check_needs_rehash(pin_hash)
