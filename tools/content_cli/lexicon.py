"""Build the Accent Studio pronunciation lexicons from espeak-ng (decision 0028).

Every text the studio scores (lines, drill words, pairs, phrases, sentences) needs its expected phonemes, in the
recogniser's own symbols. espeak-ng is the phonemiser the recogniser's training labels came from, so its output, cut
into ``content/pronunciation/recognizer_inventory.txt`` symbols with the per-language rules in ``g2p_<lang>.yaml``,
matches what the recogniser can hear. A phrase keeps one phoneme group per written word (``|`` between them), so
liaison and linking are scored and results can be shown word by word. ``lexicon_overrides_<lang>.yaml`` wins over
espeak for any key.

    uv run python -m tools.content_cli.lexicon [fr en]      # free; needs espeak-ng (brew install espeak-ng)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import yaml

from lingard_pronunciation.gym import load_gym

ROOT = Path(__file__).resolve().parents[2]
PRON = ROOT / "content" / "pronunciation"
WORD = re.compile(r"[\w'’-]+", re.UNICODE)
DROPPED = {"ˈ", "ˌ", "‍", "-", ".", "‿"}
ATTACHED = {"ː", "̃", "̩", "̪", "ʰ", "ʲ"}
"""Marks that belong to the symbol before them: length, nasal tilde, syllabic, dental, aspiration, palatal."""


def key(text: str) -> str:
    """The lexicon key of a word or phrase: its words, case-folded, NFC, joined by single spaces."""
    words = WORD.findall(text.replace("’", "'"))
    return " ".join(unicodedata.normalize("NFC", w.casefold()) for w in words)


def inventory() -> set[str]:
    lines = (PRON / "recognizer_inventory.txt").read_text().splitlines()
    return {line for line in lines if line and not line.startswith("#")}


def symbols(ipa_word: str, units: list[str], replace: dict[str, str]) -> list[str]:
    """One espeak word cut into sounds: each base letter with its attached marks, listed units merged, then replaced."""
    clean = "".join(ch for ch in unicodedata.normalize("NFC", ipa_word) if ch not in DROPPED)
    pieces: list[str] = []
    for ch in clean:
        if pieces and (ch in ATTACHED or unicodedata.combining(ch)):
            pieces[-1] += ch
        else:
            pieces.append(ch)
    merged: list[str] = []
    i = 0
    while i < len(pieces):
        pair = pieces[i] + pieces[i + 1] if i + 1 < len(pieces) else None
        if pair is not None and pair in units:
            merged.append(pair)
            i += 2
        else:
            merged.append(pieces[i])
            i += 1
    return [replace.get(s, s) for s in merged]


def espeak(text: str, voice: str) -> list[str]:
    binary = shutil.which("espeak-ng")
    if binary is None:
        raise SystemExit("espeak-ng is not installed (brew install espeak-ng)")
    # The texts are the repo's own content, passed as one argument with no shell.
    out = subprocess.run([binary, "-v", voice, "-q", "--ipa=3", text], capture_output=True, text=True, check=True)  # noqa: S603
    return out.stdout.split()


def texts(language: str) -> list[str]:
    """Everything the studio scores in this language: its lines and every drill text."""
    lines = yaml.safe_load((PRON / f"studio_{language}.yaml").read_text())["lines"]
    return list(dict.fromkeys([*(str(item["line"]) for item in lines), *load_gym(ROOT / "content", language).texts()]))


def build(language: str) -> tuple[dict[str, str], list[str]]:
    rules = yaml.safe_load((PRON / f"g2p_{language}.yaml").read_text())
    known = inventory()
    overrides_path = PRON / f"lexicon_overrides_{language}.yaml"
    raw = (yaml.safe_load(overrides_path.read_text()) or {}) if overrides_path.exists() else {}
    overrides = {key(k): v for k, v in raw.items()}
    lexicon: dict[str, str] = {}
    problems: list[str] = []
    for text in texts(language):
        words = key(text).split(" ")
        k = " ".join(words)
        if k in overrides:
            lexicon[k] = overrides[k]
            continue
        ipa = espeak(text, rules["voice"])
        if len(ipa) != len(words):
            problems.append(f"{text!r}: {len(words)} words but espeak gave {ipa}; add it to {overrides_path.name}")
            continue
        groups = [symbols(w, rules.get("units", []), rules.get("replace", {})) for w in ipa]
        unknown = sorted({s for g in groups for s in g if s not in known})
        if unknown:
            problems.append(f"{text!r}: symbols the recogniser lacks {unknown}; map them in g2p_{language}.yaml")
            continue
        lexicon[k] = " | ".join(" ".join(g) for g in groups)
        if len(words) > 1:  # each word of a phrase is a lexicon entry too (its citation form)
            for word in words:
                if word not in lexicon and word not in overrides:
                    w_ipa = espeak(word, rules["voice"])
                    if len(w_ipa) == 1:
                        lexicon[word] = " ".join(symbols(w_ipa[0], rules.get("units", []), rules.get("replace", {})))
    for k, v in overrides.items():
        lexicon.setdefault(k, v)
    return dict(sorted(lexicon.items())), problems


def write(language: str, lexicon: dict[str, str]) -> None:
    header = (
        f'# Pronunciation lexicon ({language}) for the Accent Studio: recogniser symbols, "|" between the\n'
        "# words of a phrase. Generated by tools/content_cli/lexicon.py from espeak-ng;\n"
        "# edit lexicon_overrides_<lang>.yaml, not this.\n"
    )
    body = yaml.safe_dump(lexicon, allow_unicode=True, sort_keys=True, width=1000)
    (PRON / f"lexicon_{language}.yaml").write_text(header + body)


def main() -> None:
    failed = False
    for language in sys.argv[1:] or ["fr", "en"]:
        lexicon, problems = build(language)
        write(language, lexicon)
        print(f"{language}: {len(lexicon)} entries")
        for problem in problems:
            failed = True
            print(f"  ! {problem}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
