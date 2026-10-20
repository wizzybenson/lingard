"""Grapheme-to-phoneme seam. Lexicon-based by default (permissive licences only; espeak-ng is GPL, see licences)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Protocol

import yaml


class G2P(Protocol):
    def phonemes(self, text: str, language: str) -> list[str]: ...

    def variants(self, language: str) -> dict[str, list[str]]:
        """Phoneme → other realisations native speakers use, all scored as correct."""
        ...


class LexiconG2P:
    """Word → phoneme list from ``content/pronunciation/lexicon_<lang>.yaml``; unknown words raise, never guess."""

    def __init__(self, content_root: Path) -> None:
        self._root = content_root
        self._lexicons: dict[str, dict[str, list[str]]] = {}

    def _lexicon(self, language: str) -> dict[str, list[str]]:
        if language not in self._lexicons:
            path = self._root / "pronunciation" / f"lexicon_{language}.yaml"
            raw = yaml.safe_load(path.read_text()) if path.is_file() else {}
            self._lexicons[language] = {self._norm(k): list(v.split()) for k, v in (raw or {}).items()}
        return self._lexicons[language]

    def variants(self, language: str) -> dict[str, list[str]]:
        path = self._root / "pronunciation" / f"variants_{language}.yaml"
        raw = yaml.safe_load(path.read_text()) if path.is_file() else {}
        return {str(k): [str(v) for v in values] for k, values in (raw or {}).items()}

    @staticmethod
    def _norm(word: str) -> str:
        return unicodedata.normalize("NFC", word.casefold())

    def phonemes(self, text: str, language: str) -> list[str]:
        lexicon = self._lexicon(language)
        out: list[str] = []
        for word in re.findall(r"[\w'’-]+", text, flags=re.UNICODE):
            key = self._norm(word.replace("’", "'"))
            if key not in lexicon:
                raise KeyError(f"no pronunciation for {word!r} ({language}); add it to the lexicon")
            out += lexicon[key]
        return out
