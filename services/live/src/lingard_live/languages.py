"""Per-language live config loaded from ``content/languages/<lang>.yaml``, plus language identification."""

from __future__ import annotations

import random
import re
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from lingard_contracts.common import Language

_WORD = re.compile(r"[\w']+", re.UNICODE)


class LanguageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    language: Language
    stt_locale: str
    function_words: list[str]
    other_language_reply: list[str]
    clarify: list[str]
    unsure: list[str]
    """The NPC's reply when the Guard withheld every sentence of it as an unsupported claim."""
    backchannels: list[str]
    fillers: list[str]
    """Hesitations the NPC says when its first sentence is still held by the claim check."""
    question_marks: list[str]
    continuation_words: list[str]
    """Words an utterance can't end on ("et", "parce", "de"): after one the learner is still mid-sentence."""
    abbreviations: list[str]
    tutor_markers: list[str]
    character_break_markers: list[str]
    unsafe_markers: list[str]
    help_hint_ui: dict[str, str]
    months: list[str]
    weekdays: list[str]
    number_words: dict[str, int]
    capitalised_common: list[str]
    choose_correct_prompt: str
    narrator_voice: str
    """TTS voice id that reads exam listening items aloud."""
    learner_address: str
    """How on-screen instructions address the learner (scene goals), for the Scene Compiler (decision 0015)."""

    def pick(self, options: list[str], rng: random.Random | None = None) -> str:
        return (rng or random).choice(options)


@cache
def load_language(content_root: Path, language: Language) -> LanguageConfig:
    return LanguageConfig.model_validate(yaml.safe_load((content_root / "languages" / f"{language}.yaml").read_text()))


def words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD.findall(text)]


class LanguageIdentifier:
    """Function-word voting between the exam languages. Cheap, deterministic and good on short utterances."""

    def __init__(self, configs: list[LanguageConfig], min_hits: int = 2) -> None:
        sets = {c.language: {w.casefold() for w in c.function_words} for c in configs}
        shared = set.intersection(*sets.values()) if len(sets) > 1 else set()
        self._sets = {lang: words - shared for lang, words in sets.items()}  # shared words carry no signal
        self._min_hits = min_hits

    def scores(self, text: str) -> dict[str, int]:
        tokens = words(text)
        return {lang: sum(1 for t in tokens if t in vocab) for lang, vocab in self._sets.items()}

    def identify(self, text: str) -> str | None:
        """The dominant language, or None when there is no clear signal."""
        scores = self.scores(text)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        if not ranked or ranked[0][1] < self._min_hits:
            return None
        if len(ranked) > 1 and ranked[0][1] < 2 * ranked[1][1] and ranked[0][1] - ranked[1][1] < 2:
            return None
        return ranked[0][0]
