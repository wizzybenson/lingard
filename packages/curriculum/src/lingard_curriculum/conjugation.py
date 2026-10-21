"""Conjugation engines. French derives compound tenses from verb data; English uses principal parts."""

from __future__ import annotations

import random
import unicodedata
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field

PERSONS_FR = ("je", "tu", "il", "nous", "vous", "ils")
PRESENT_ENDINGS = {
    "er": ("e", "es", "e", "ons", "ez", "ent"),
    "ir": ("is", "is", "it", "issons", "issez", "issent"),
}
OTHER_PRESENT_ENDINGS = (("s", "x"), ("s", "x"), ("t", "d"), ("ons",), ("ez",), ("ent",))
"""What most other verbs end in, in the present: shown apart where a form has it (je prend·s, il prend)."""
SUBJONCTIF_ENDINGS = ("e", "es", "e", "ions", "iez", "ent")
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

    def tables(self) -> Conjugations:
        """Every verb's full tables, each form split so the ending a learner must learn can be shown apart."""
        ...

    def focus(self, node_key: str) -> list[str]:
        """The tenses a grammar point is about, which its verb tables open on."""
        ...


class Form(BaseModel):
    """One cell of a table: « nous » + « parl » + « ons », or « j' » + « ai » (aux) + « parlé »."""

    subject: str
    aux: str = ""
    stem: str
    ending: str = ""
    """The part the rule is about, shown apart; empty when the form keeps no regular ending."""
    irregular: bool = False
    """The form breaks the tense's pattern (spelling change, own stem, own form): worth a second look."""

    @property
    def word(self) -> str:
        return " ".join(p for p in (self.aux, self.stem + self.ending) if p)


class TenseTable(BaseModel):
    tense: str
    label: str
    band: int
    forms: list[Form]


class VerbTables(BaseModel):
    key: str
    infinitive: str
    irregular: bool
    """Somewhere in its tables the verb goes its own way."""
    tenses: list[TenseTable]

    def words(self) -> set[str]:
        """Every single word a learner might tap to open this verb: its forms, participle and infinitive."""
        out = {self.infinitive.casefold()}
        for table in self.tenses:
            for form in table.forms:
                out.add((form.stem + form.ending).casefold())
        return out


class Conjugations(BaseModel):
    persons: list[str]
    tenses: list[TenseTable]
    """Each tense's name and level (no forms): the sheet's tabs, easiest first."""
    verbs: list[VerbTables]
    index: dict[str, str]
    """A word as it appears in a sentence (lower-cased, no elided pronoun) → the verb it belongs to."""


def index_words(verbs: list[VerbTables], skip: set[str]) -> dict[str, str]:
    """Word → verb; a word shared by two verbs (suis: être and suivre) goes to the first, in content order."""
    index: dict[str, str] = {}
    for verb in verbs:
        for word in verb.words():
            if word not in skip and " " not in word:
                index.setdefault(word, verb.key)
    return index


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
        """Follows the -er or -ir (finir) pattern in the present: what the regular-present lesson drills. The -ger
        and -cer spellings (nous mangeons, nous commençons) keep the sound and count as regular."""
        group = self.infinitive[-2:]
        return group in PRESENT_ENDINGS and self.present == regular_present(self.infinitive)

    @classmethod
    def derived(cls, infinitive: str, aux: str) -> FrenchVerb:
        """A regular -er or -ir (finir) verb, all of whose forms follow from its infinitive."""
        stem, group = infinitive[:-2], infinitive[-2:]
        if group not in PRESENT_ENDINGS:
            raise ValueError(f"{infinitive}: only -er and -ir (finir) verbs are derived")
        present = regular_present(infinitive)
        subj = stem + ("iss" if group == "ir" else "")
        return cls(
            infinitive=infinitive,
            aux=aux,
            participle=stem + ("é" if group == "er" else "i"),
            present=present,
            futur_stem=infinitive,
            subjonctif=[subj + e for e in SUBJONCTIF_ENDINGS],
        )


def regular_present(infinitive: str) -> list[str]:
    """The present of a regular -er or -ir verb; -ger and -cer verbs keep their sound before -ons."""
    stem, group = infinitive[:-2], infinitive[-2:]
    forms = [stem + e for e in PRESENT_ENDINGS[group]]
    if group == "er" and stem.endswith("g"):
        forms[3] = stem + "eons"
    elif group == "er" and stem.endswith("c"):
        forms[3] = stem[:-1] + "çons"
    return forms


def split(form: str, endings: tuple[str, ...]) -> tuple[str, str]:
    """(stem, ending) with the longest of ``endings`` the form ends in; the whole form as stem when none fits."""
    for ending in sorted(endings, key=len, reverse=True):
        if ending and form.endswith(ending) and len(form) > len(ending):
            return form[: -len(ending)], ending
    return form, ""


class FrenchConjugator:
    def __init__(
        self,
        verbs: dict[str, FrenchVerb],
        tenses: list[str],
        tense_bands: dict[str, int],
        tense_labels: dict[str, str] | None = None,
        persons: list[str] | None = None,
        drills: dict[str, list[str]] | None = None,
        not_tappable: list[str] | None = None,
    ) -> None:
        self.verbs = verbs
        self.not_tappable = set(not_tappable or [])
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
        for infinitive, aux in (data.get("regular") or {}).items():
            verbs.setdefault(plain_key(infinitive), FrenchVerb.derived(infinitive, aux))
        return cls(
            verbs,
            list(data["tenses"]),
            dict(data["tense_bands"]),
            dict(data.get("tense_labels", {})),
            list(data.get("persons", PERSONS_FR)),
            dict(data.get("drills", {})),
            data.get("not_tappable"),
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

    def focus(self, node_key: str) -> list[str]:
        return drilled(self.drills, node_key)

    def _subject(self, person: int, first_word: str, tense: str) -> str:
        """« je » or « j' » before a vowel, and « que » / « qu' » in the subjunctive."""
        label = self.persons[person]
        subject = "j'" if person == 0 and first_word.startswith(VOWEL_START) else label
        if tense == "subjonctif_present":
            subject = ("qu'" if subject.startswith(("il", "elle")) else "que ") + subject
        return subject

    def _cells(self, verb: FrenchVerb, tense: str) -> list[tuple[str, str, bool]]:
        """(stem, ending, irregular) for each person of a simple tense."""
        forms = self._simple(verb, tense)
        group = verb.infinitive[-2:]
        if tense == "present":
            if verb.regular:
                endings = PRESENT_ENDINGS[group]
                expected = [verb.infinitive[:-2] + e for e in endings]
                return [(*split(f, (e,)), f != x) for f, e, x in zip(forms, endings, expected, strict=True)]
            cells = [split(f, e) for f, e in zip(forms, OTHER_PRESENT_ENDINGS, strict=True)]
            if not all(ending for _, ending in cells):  # its own forms (je suis, nous sommes): learned whole
                return [(f, "", True) for f in forms]
            # The usual endings on a stem that moves (je prend·s, ils prenn·ent): forms off the nous stem stand out.
            return [(stem, ending, stem != cells[3][0]) for stem, ending in cells]
        if tense in ("imparfait", "futur_simple", "conditionnel_present"):
            endings = IMPARFAIT_ENDINGS if tense != "futur_simple" else FUTUR_ENDINGS
            regular_stem = (
                verb.present[3].removesuffix("ons") if tense == "imparfait" else verb.infinitive.removesuffix("e")
            )
            out = []
            for form, ending in zip(forms, endings, strict=True):
                stem, end = split(form, (ending,))
                plain = stem in (regular_stem, regular_stem.removesuffix("e"), regular_stem.replace("ç", "c"))
                out.append((stem, end, (tense == "imparfait" and verb.imparfait_stem is not None) or not plain))
            return out
        if tense == "subjonctif_present":
            ils, nous = verb.present[5].removesuffix("ent"), verb.present[3].removesuffix("ons")
            nous = nous.removesuffix("e") if nous.endswith("ge") else nous.replace("ç", "c")  # mangions, commencions
            return [
                (*split(f, (e,)), f != (nous if p in (3, 4) else ils) + e)
                for p, (f, e) in enumerate(zip(forms, SUBJONCTIF_ENDINGS, strict=True))
            ]
        raise KeyError(tense)

    def table(self, key: str, tense: str) -> list[Form]:
        verb = self._verb(key)
        if tense in COMPOUND_AUX_TENSE:
            helper = self._verb("etre" if verb.aux == "être" else "avoir")
            aux = self._simple(helper, COMPOUND_AUX_TENSE[tense])
            # The participle's regular ending (parlé, fini, attendu) is the part to learn, with any agreement (allés).
            regular_end = {"er": "é", "ir": "i", "re": "u"}.get(verb.infinitive[-2:], "")
            stem, end = split(verb.participle, (regular_end,))
            if stem != verb.infinitive[:-2] and not (regular_end == "i" and stem + "ir" == verb.infinitive):
                stem, end = verb.participle, ""  # its own participle (eu, fait, pris): learned whole
            out = []
            for p in range(6):
                agreement = self._participle(verb, p).removeprefix(verb.participle)
                out.append(Form(subject=self._subject(p, aux[p], tense), aux=aux[p], stem=stem, ending=end + agreement))
            return out
        return [
            Form(subject=self._subject(p, stem + ending, tense), stem=stem, ending=ending, irregular=irregular)
            for p, (stem, ending, irregular) in enumerate(self._cells(verb, tense))
        ]

    def tables(self) -> Conjugations:
        tenses = sorted(self.tenses, key=lambda t: (self.tense_bands[t], self.tenses.index(t)))
        verbs = []
        for key, verb in self.verbs.items():
            tables = [
                TenseTable(tense=t, label=self.label(t), band=self.tense_bands[t], forms=self.table(key, t))
                for t in tenses
            ]
            irregular = any(f.irregular for table in tables for f in table.forms)
            verbs.append(VerbTables(key=key, infinitive=verb.infinitive, irregular=irregular, tenses=tables))
        heads = [TenseTable(tense=t, label=self.label(t), band=self.tense_bands[t], forms=[]) for t in tenses]
        index = index_words(verbs, self.not_tappable)
        return Conjugations(persons=self.persons, tenses=heads, verbs=verbs, index=index)


def plain_key(infinitive: str) -> str:
    """« être » → ``etre``: verb keys are written without accents."""
    return unicodedata.normalize("NFKD", infinitive).encode("ascii", "ignore").decode()


class EnglishVerb(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base: str
    past: str
    participle: str
    third_person: str | None = None
    ing: str | None = None
    present: list[str] | None = Field(default=None, min_length=5, max_length=5)
    """Its own present (I am, you are, …), for the one verb that has one."""
    irregular: bool = True

    @classmethod
    def regular(cls, base: str, past: str | None) -> EnglishVerb:
        """A regular verb: -ed for the past and the participle (lived, studied), unless its spelling is given."""
        if past is None:
            past = base + "d" if base.endswith("e") else base[:-1] + "ied" if consonant_y(base) else base + "ed"
        return cls(base=base, past=past, participle=past, irregular=False)


def consonant_y(word: str) -> bool:
    return word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou"


def third_person(base: str) -> tuple[str, str]:
    """(stem, ending) of the he/she/it form: works, watches, goes, studies."""
    if consonant_y(base):
        return base[:-1], "ies"
    if base.endswith(("s", "sh", "ch", "x", "z", "o")):
        return base, "es"
    return base, "s"


def past_split(form: str, irregular: bool) -> tuple[str, str, bool]:
    if irregular:
        return form, "", True
    if form.endswith("ied"):
        return form[:-3], "ied", False
    return (form[:-2], "ed", False) if form.endswith("ed") else (form, "", False)


class EnglishConjugator:
    def __init__(
        self,
        verbs: dict[str, EnglishVerb],
        drills: dict[str, list[str]] | None = None,
        form_labels: dict[str, str] | None = None,
        *,
        regular: dict[str, EnglishVerb] | None = None,
        persons: list[str] | None = None,
        tenses: list[str] | None = None,
        tense_labels: dict[str, str] | None = None,
        tense_bands: dict[str, int] | None = None,
        focus: dict[str, list[str]] | None = None,
        not_tappable: list[str] | None = None,
    ) -> None:
        self.verbs = verbs
        self.drills = drills or {}
        self.form_labels = form_labels or {}
        self.regular_verbs = regular or {}
        """Regular verbs: in the tables a learner looks up, never in the irregular-verb duel."""
        self.persons = persons or ["I", "you", "he/she/it", "we", "they"]
        self.tenses = tenses or []
        self.tense_labels = tense_labels or {}
        self.tense_bands = tense_bands or {}
        self.focus_hints = focus or {}
        self.not_tappable = set(not_tappable or [])

    @classmethod
    def load(cls, path: str | Path) -> EnglishConjugator:
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text())
        verbs = {key: EnglishVerb.model_validate(raw) for key, raw in data["verbs"].items()}
        regular = {base: EnglishVerb.regular(base, past) for base, past in (data.get("regular") or {}).items()}
        return cls(
            verbs,
            dict(data.get("drills", {})),
            dict(data.get("form_labels", {})),
            regular=regular,
            persons=data.get("persons"),
            tenses=data.get("tenses"),
            tense_labels=data.get("tense_labels"),
            tense_bands=data.get("tense_bands"),
            focus=data.get("focus"),
            not_tappable=data.get("not_tappable"),
        )

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

    def focus(self, node_key: str) -> list[str]:
        return drilled(self.focus_hints, node_key)

    def _past(self, verb: EnglishVerb, person: int) -> str:
        """« was/were »: was for I and he/she/it, were for the others."""
        if "/" not in verb.past:
            return verb.past
        singular, plural = verb.past.split("/", 1)
        return singular if person in (0, 2) else plural

    def table(self, verb: EnglishVerb, tense: str) -> list[Form]:
        forms = []
        for p, subject in enumerate(self.persons):
            if tense == "present_simple":
                if verb.present:
                    forms.append(Form(subject=subject, stem=verb.present[p], irregular=True))
                elif p == 2:
                    stem, ending = third_person(verb.base)
                    own = verb.third_person is not None and verb.third_person != stem + ending
                    forms.append(
                        Form(subject=subject, stem=verb.third_person, irregular=True)
                        if own and verb.third_person
                        else Form(subject=subject, stem=stem, ending=ending)
                    )
                else:
                    forms.append(Form(subject=subject, stem=verb.base))
            elif tense == "past_simple":
                stem, ending, irregular = past_split(self._past(verb, p), verb.irregular)
                forms.append(Form(subject=subject, stem=stem, ending=ending, irregular=irregular))
            elif tense in ("present_perfect", "past_perfect"):
                aux = "had" if tense == "past_perfect" else "has" if p == 2 else "have"
                stem, ending, irregular = past_split(verb.participle, verb.irregular)
                forms.append(Form(subject=subject, aux=aux, stem=stem, ending=ending, irregular=irregular))
            else:
                raise KeyError(tense)
        return forms

    def tables(self) -> Conjugations:
        tenses = sorted(self.tenses, key=lambda t: (self.tense_bands[t], self.tenses.index(t)))
        verbs = []
        for key, verb in [*self.verbs.items(), *self.regular_verbs.items()]:
            tables = [
                TenseTable(
                    tense=t, label=self.tense_labels.get(t, t), band=self.tense_bands[t], forms=self.table(verb, t)
                )
                for t in tenses
            ]
            irregular = any(f.irregular for table in tables for f in table.forms)
            verbs.append(VerbTables(key=key, infinitive=verb.base, irregular=irregular, tenses=tables))
        heads = [
            TenseTable(tense=t, label=self.tense_labels.get(t, t), band=self.tense_bands[t], forms=[]) for t in tenses
        ]
        # A regular verb's bare form is as often a noun (an answer, a book, the work): only its inflected forms link.
        nouns_too = {verb.base for verb in self.regular_verbs.values()}
        return Conjugations(
            persons=self.persons, tenses=heads, verbs=verbs, index=index_words(verbs, self.not_tappable | nouns_too)
        )
