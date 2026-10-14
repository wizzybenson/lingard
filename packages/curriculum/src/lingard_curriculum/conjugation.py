"""Conjugation engines. French derives compound tenses from verb data; English uses principal parts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

PERSONS_FR = ("je", "tu", "il", "nous", "vous", "ils")
IMPARFAIT_ENDINGS = ("ais", "ais", "ait", "ions", "iez", "aient")
FUTUR_ENDINGS = ("ai", "as", "a", "ons", "ez", "ont")
VOWEL_START = tuple("aeéèêiîoôuhâ")
COMPOUND_AUX_TENSE = {
    "passe_compose": "present",
    "plus_que_parfait": "imparfait",
    "conditionnel_passe": "conditionnel_present",
}


class FrenchVerb(BaseModel):
    model_config = ConfigDict(extra="forbid")

    infinitive: str
    aux: str = Field(pattern="^(avoir|être)$")
    participle: str
    present: list[str] = Field(min_length=6, max_length=6)
    futur_stem: str
    subjonctif: list[str] = Field(min_length=6, max_length=6)
    imparfait_stem: str | None = None


class FrenchConjugator:
    def __init__(self, verbs: dict[str, FrenchVerb], tenses: list[str], tense_bands: dict[str, int]) -> None:
        self.verbs = verbs
        self.tenses = tenses
        self.tense_bands = tense_bands

    @classmethod
    def load(cls, path: str | Path) -> FrenchConjugator:
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text())
        verbs = {key: FrenchVerb.model_validate(raw) for key, raw in data["verbs"].items()}
        return cls(verbs, list(data["tenses"]), dict(data["tense_bands"]))

    def _verb(self, key: str) -> FrenchVerb:
        try:
            return self.verbs[key]
        except KeyError as exc:
            raise KeyError(f"unknown verb {key!r}") from exc

    def _imparfait(self, verb: FrenchVerb) -> list[str]:
        stem = verb.imparfait_stem or verb.present[3].removesuffix("ons")
        # The nous stem keeps -ge/-ç (mangeons, commençons); before -ions/-iez they revert (mangions, commencions).
        forms = []
        for ending in IMPARFAIT_ENDINGS:
            base = stem
            if ending.startswith("i") and base.endswith("ge"):
                base = base[:-1]
            if ending.startswith("i") and base.endswith("ç"):
                base = base[:-1] + "c"
            forms.append(base + ending)
        return forms

    def _simple(self, verb: FrenchVerb, tense: str) -> list[str]:
        if tense == "present":
            return list(verb.present)
        if tense == "imparfait":
            return self._imparfait(verb)
        if tense == "futur_simple":
            return [verb.futur_stem + e for e in FUTUR_ENDINGS]
        if tense == "conditionnel_present":
            return [verb.futur_stem + e for e in IMPARFAIT_ENDINGS]
        if tense == "subjonctif_present":
            return list(verb.subjonctif)
        raise KeyError(tense)

    def _participle(self, verb: FrenchVerb, person: int) -> str:
        """Agreement with être shown for a masculine subject; plural persons take -s (unless already -s)."""
        if verb.aux != "être" or person < 3 or verb.participle.endswith("s"):
            return verb.participle
        return verb.participle + "s"

    def conjugate(self, key: str, tense: str) -> list[str]:
        """Six forms, without subject pronouns."""
        verb = self._verb(key)
        compound = {
            "passe_compose": "present",
            "plus_que_parfait": "imparfait",
            "conditionnel_passe": "conditionnel_present",
        }
        if tense in compound:
            aux = self._simple(self._verb("etre" if verb.aux == "être" else "avoir"), compound[tense])
            return [f"{aux[p]} {self._participle(verb, p)}" for p in range(6)]
        return self._simple(verb, tense)

    def with_subjects(self, key: str, tense: str) -> list[str]:
        forms = self.conjugate(key, tense)
        out = []
        for person, form in zip(PERSONS_FR, forms, strict=True):
            phrase = f"j'{form}" if person == "je" and form.startswith(VOWEL_START) else f"{person} {form}"
            if tense == "subjonctif_present":
                phrase = ("qu'" if person in ("il", "ils") else "que ") + phrase
            out.append(phrase)
        return out


class EnglishVerb(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base: str
    past: str
    participle: str
    third_person: str | None = None
    ing: str | None = None


class EnglishConjugator:
    def __init__(self, verbs: dict[str, EnglishVerb]) -> None:
        self.verbs = verbs

    @classmethod
    def load(cls, path: str | Path) -> EnglishConjugator:
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text())
        return cls({key: EnglishVerb.model_validate(raw) for key, raw in data["verbs"].items()})

    def principal_parts(self, key: str) -> tuple[str, str, str]:
        verb = self.verbs[key]
        return verb.base, verb.past, verb.participle
