"""Logical NPC voice ids (``fr_m_58_martin``) → each TTS provider's own voice.

Content names voices by language, gender and character, never by provider. A provider voice is chosen by an
override in ``config/voices.yaml`` if there is one, otherwise picked stably from the provider's voices of the same
gender, so every NPC keeps one voice across sessions and two NPCs rarely share one.
"""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import Any

import yaml

OPENAI_VOICES: dict[str, list[str]] = {
    "f": ["coral", "nova", "shimmer", "sage", "marin"],
    "m": ["ash", "echo", "onyx", "cedar", "verse"],
}
"""Built-in gpt-4o-mini-tts voices, split by how they present (https://platform.openai.com/docs/guides/text-to-speech)."""


def gender_of(logical_id: str) -> str:
    """``fr_m_58_martin`` → ``m``; ids without a gender part count as ``f``."""
    parts = logical_id.split("_")
    return parts[1] if len(parts) > 1 and parts[1] in ("f", "m") else "f"


def choose_pool(catalogue: list[dict[str, Any]], language: str, accents: list[str], gender: str) -> list[str]:
    """Voice ids for a line: the account's voices of its language (and an allowed accent, if any has one) and gender,
    widening step by step (any accent, any gender, any voice) so a pick always exists."""

    def labels(voice: dict[str, Any]) -> dict[str, str]:
        return {k: str(v).lower() for k, v in (voice.get("labels") or {}).items()}

    speaks = [v for v in catalogue if not language or labels(v).get("language") == language]
    accented = [v for v in speaks if labels(v).get("accent") in accents]
    for pool in (accented, speaks, catalogue):
        same = [v["voice_id"] for v in pool if labels(v).get("gender", "")[:1] == gender]
        if same:
            return same
        if pool:
            return [v["voice_id"] for v in pool]
    return []


def pick(pool: list[str], logical_id: str) -> str:
    return pool[zlib.crc32(logical_id.encode()) % len(pool)]


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    """``{provider: {logical_id: provider_voice}}`` from ``config/voices.yaml``; missing file → none."""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {
        str(provider): {str(k): str(v) for k, v in (voices or {}).items()}
        for provider, voices in data.items()
        if provider != "accents"
    }


def load_accents(path: Path) -> dict[str, list[str]]:
    """``{language: [accent, …]}``: the accents a voice may have for each language (``config/voices.yaml``)."""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {str(lang): [str(a) for a in accents] for lang, accents in (data.get("accents") or {}).items()}
