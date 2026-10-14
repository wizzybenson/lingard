"""Primitive types shared by every Lingard service."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["fr", "en"]
"""Exam language. Everything language-specific is keyed by this, never hard-coded."""

Locale = Literal["fr-FR", "fr-CA", "en-GB"]
CityKey = Literal["ashford", "rivemont"]
UiLocale = Literal["en", "fr", "ar"]
PackId = Literal["ielts_gt", "tef_canada"]

Band = Annotated[int, Field(ge=1, le=12)]
"""A CLB (English) or NCLC (French) level. Both scales run 1–12."""

NodeKey = Annotated[str, Field(pattern=r"^(fr|en)\.[a-z_]+(\.[a-z0-9_]+)+$")]
"""Curriculum node key, e.g. ``fr.grammar.si_imparfait``. The prefix is the language."""

CITY_LANGUAGE: dict[str, Language] = {"rivemont": "fr", "ashford": "en"}
CITY_LOCALE: dict[str, Locale] = {"rivemont": "fr-FR", "ashford": "en-GB"}
LANGUAGE_PACK: dict[str, PackId] = {"fr": "tef_canada", "en": "ielts_gt"}
LANGUAGE_CITY: dict[str, CityKey] = {"fr": "rivemont", "en": "ashford"}
LANGUAGE_NAME: dict[str, str] = {"fr": "French", "en": "English", "ar": "Arabic"}
"""English names of exam and interface languages, used inside prompts (which are written in English)."""
LANGUAGE_SCALE: dict[str, str] = {"fr": "NCLC", "en": "CLB"}
"""The Canadian benchmark scale each exam language reports on."""


class Skill(StrEnum):
    LISTENING = "listening"
    READING = "reading"
    WRITING = "writing"
    SPEAKING = "speaking"


class Frozen(BaseModel):
    """Base for immutable value objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Strict(BaseModel):
    """Base for mutable schemas that reject unknown fields."""

    model_config = ConfigDict(extra="forbid")


def node_language(key: str) -> Language:
    prefix = key.split(".", 1)[0]
    if prefix not in ("fr", "en"):
        raise ValueError(f"curriculum key {key!r} has no language prefix")
    return "fr" if prefix == "fr" else "en"
