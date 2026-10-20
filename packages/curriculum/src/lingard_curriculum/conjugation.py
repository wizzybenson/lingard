"""Conjugation engines. French derives compound tenses from verb data; English uses principal parts."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Protocol

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


class Conjugator(Protocol):
    def drill(self, node_key: str, rng: random.Random) -> list[tuple[str, str]]:
        """(prompt, answer) pairs for a grammar point's conjugation duel; empty when it drills no verb forms."""
        ...


def drilled(drills: dict[str, list[str]], node_key: str) -> list[str]:
    """The forms a grammar point drills: the entry whose key is the longest found in the node key."""
    matches = [hint for hint in drills if hint in node_key.rsplit(".", 1)[-1]]
    return drills[max(matches, key=len)] if matches else []


def load_conjugator(path: Path) -> Conjugator | None:
    """The language's engine, named by the file's ``engine``; None when the language has no conjugation data."""
    if not path.exists():
        return None
    engine = yaml.safe_load(path.read_text()).get("engine")
    engines: dict[str, Any] = {"french": FrenchConjugator, "english": EnglishConjugator}
    loaded: Conjugator = engines[engine].load(path)
    return loaded


class FrenchVerb(BaseModel):
    model_config = ConfigDict(extra="forbid")

    infinitive: str
    aux: str = Field(pattern="^(avoir|être)$")
    participle: str
    present: list[str] = Field(min_length=6, max_length=6)
    futur_stem: str
    subjonctif: list[str] = Field(min_length=6, max_length=6)
    imparfait_stem: str | None = None

    @property
    def regular(self) -> bool:
        """Follows the -er or -ir (finir) pattern in the present: what the regular-present lesson drills."""
        stem, ending = self.infinitive[:-2], self.infinitive[-2:]
        patterns = {"er": ["e", "es", "e", "ons", "ez", "ent"], "ir": ["is", "is", "it", "issons", "issez", "issent"]}
        return ending in patterns and self.present == [stem + e for e in patterns[ending]]


class FrenchConjugator:
    def __init__(
        self,
        verbs: dict[str, FrenchVerb],
        tenses: list[str],
        tense_bands: dict[str, int],
        tense_labels: dict[str, str] | None = None,
        persons: list[str] | None = None,
        drills: dict[str, list[str]] | None = None,
    ) -> None:
        self.verbs = verbs
        self.tenses = tenses
        self.tense_bands = tense_bands
        self.tense_labels = tense_labels or {}
        self.persons = persons or list(PERSONS_FR)
        self.drills = drills or {}

    def label(self, tense: str) -> str:
        """The tense's name as a learner reads it (« passé composé »), from the content."""
        return self.tense_labels.get(tense, tense.replace("_", " "))

    @classmethod
    def load(cls, path: str | Path) -> FrenchConjugator:
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text())
        verbs = {key: FrenchVerb.model_validate(raw) for key, raw in data["verbs"].items()}
        return cls(
            verbs,
            list(data["tenses"]),
            dict(data["tense_bands"]),
            dict(data.get("tense_labels", {})),
            list(data.get("persons", PERSONS_FR)),
            dict(data.get("drills", {})),
        )

    def drill(self, node_key: str, rng: random.Random) -> list[tuple[str, str]]:
        """Two persons of each verb in each drilled tense; a lesson on (ir)regular verbs drills only those."""
        regularity = False if "irregular" in node_key else True if "regular" in node_key else None
        pairs = []
        for tense in drilled(self.drills, node_key):
            for key, verb in self.verbs.items():
                if regularity is not None and verb.regular != regularity:
                    continue
                forms = self.conjugate(key, tense)
                for person in rng.sample(range(6), 2):
                    pairs.append((f"{self.persons[person]} — {verb.infinitive} ({self.label(tense)})", forms[person]))
        return pairs

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
    def __init__(
        self,
        verbs: dict[str, EnglishVerb],
        drills: dict[str, list[str]] | None = None,
        form_labels: dict[str, str] | None = None,
    ) -> None:
        self.verbs = verbs
        self.drills = drills or {}
        self.form_labels = form_labels or {}

    @classmethod
    def load(cls, path: str | Path) -> EnglishConjugator:
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text())
        verbs = {key: EnglishVerb.model_validate(raw) for key, raw in data["verbs"].items()}
        return cls(verbs, dict(data.get("drills", {})), dict(data.get("form_labels", {})))

    def drill(self, node_key: str, rng: random.Random) -> list[tuple[str, str]]:
        """Each irregular verb's drilled principal parts (went, gone). Forms with two answers (was/were) are left out:
        the duel takes one answer."""
        pairs = []
        for form in drilled(self.drills, node_key):
            for verb in self.verbs.values():
                answer = str(getattr(verb, form))
                if "/" not in answer:
                    pairs.append((f"{verb.base} ({self.form_labels.get(form, form)})", answer))
        rng.shuffle(pairs)
        return pairs

    def principal_parts(self, key: str) -> tuple[str, str, str]:
        verb = self.verbs[key]
        return verb.base, verb.past, verb.participle
