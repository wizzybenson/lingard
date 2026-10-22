"""Grapheme-to-phoneme seam. Lexicon-based by default (permissive licences only; espeak-ng is GPL, see licences)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Protocol

import yaml


class G2P(Protocol):
    def words(self, text: str, language: str) -> list[tuple[str, list[str]]]:
        """Each written word of ``text`` with its expected phonemes (in context, so liaison and linking count)."""
        ...

    def phonemes(self, text: str, language: str) -> list[str]: ...

    def variants(self, language: str) -> dict[str, list[str]]:
        """Phoneme → other realisations native speakers use, all scored as correct."""
        ...

    def competitors(self, language: str) -> set[str]: ...

    def vowels(self, language: str) -> set[str]: ...


WORD = re.compile(r"[\w'’-]+", flags=re.UNICODE)


class LexiconG2P:
    """Text → phonemes from ``content/pronunciation/lexicon_<lang>.yaml``; unknown words raise, never guess.

    An entry is one word, or a whole phrase with ``|`` between its words' phonemes (generated with the words in
    context, decision 0028). A text found whole is used as is; otherwise each of its words is looked up alone."""

    def __init__(self, content_root: Path) -> None:
        self._root = content_root
        self._lexicons: dict[str, dict[str, list[list[str]]]] = {}

    def _lexicon(self, language: str) -> dict[str, list[list[str]]]:
        if language not in self._lexicons:
            path = self._root / "pronunciation" / f"lexicon_{language}.yaml"
            raw = yaml.safe_load(path.read_text()) if path.is_file() else {}
            self._lexicons[language] = {
                self._norm(str(k)): [group.split() for group in str(v).split("|")] for k, v in (raw or {}).items()
            }
        return self._lexicons[language]

    def variants(self, language: str) -> dict[str, list[str]]:
        path = self._root / "pronunciation" / f"variants_{language}.yaml"
        raw = yaml.safe_load(path.read_text()) if path.is_file() else {}
        return {str(k): [str(v) for v in values] for k, values in (raw or {}).items()}

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join(unicodedata.normalize("NFC", w.casefold()) for w in WORD.findall(text.replace("’", "'")))

    def words(self, text: str, language: str) -> list[tuple[str, list[str]]]:
        lexicon = self._lexicon(language)
        written = WORD.findall(text)
        whole = lexicon.get(self._norm(text))
        if whole is not None and len(whole) == len(written):
            return list(zip(written, whole, strict=True))
        out: list[tuple[str, list[str]]] = []
        for word in written:
            entry = lexicon.get(self._norm(word))
            if entry is None or len(entry) != 1:
                raise KeyError(f"no pronunciation for {word!r} ({language}); add it to the lexicon")
            out.append((word, entry[0]))
        return out

    def phonemes(self, text: str, language: str) -> list[str]:
        return [p for _, phonemes in self.words(text, language) for p in phonemes]

    def vowels(self, language: str) -> set[str]:
        """The language's vowels (syllable nuclei), from the sound gym's features."""
        path = self._root / "pronunciation" / f"sounds_{language}.yaml"
        if not path.is_file():
            return set()
        features = yaml.safe_load(path.read_text())["features"]
        return {str(p) for p, f in features.items() if f.get("kind") in ("vowel", "diphthong")}

    def competitors(self, language: str) -> set[str]:
        """What a sound is judged against: every sound of the language (its lexicon and native variants) and every
        mistake learners make with them (the sound gym's confusions)."""
        own = {p for entry in self._lexicon(language).values() for group in entry for p in group}
        own |= {v for values in self.variants(language).values() for v in values}
        path = self._root / "pronunciation" / f"sounds_{language}.yaml"
        if path.is_file():
            gym = yaml.safe_load(path.read_text())
            own |= {str(heard) for sound in gym["phonemes"].values() for heard in (sound.get("confusions") or {})}
        return own
