"""Logical NPC voice ids (``fr_m_58_martin``) → each TTS provider's own voice.

Content names voices by language, gender and character, never by provider. A provider voice is chosen by an
override in ``config/voices.yaml`` if there is one, otherwise picked stably from the provider's voices of the same
gender, so every NPC keeps one voice across sessions and two NPCs rarely share one.
"""

from __future__ import annotations

import zlib
from pathlib import Path

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


def pick(pool: list[str], logical_id: str) -> str:
    return pool[zlib.crc32(logical_id.encode()) % len(pool)]


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    """``{provider: {logical_id: provider_voice}}`` from ``config/voices.yaml``; missing file → none."""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {str(provider): {str(k): str(v) for k, v in (voices or {}).items()} for provider, voices in data.items()}
