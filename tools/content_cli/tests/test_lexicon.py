from pathlib import Path

from lingard_pronunciation.g2p import LexiconG2P
from tools.content_cli.lexicon import symbols

ROOT = Path(__file__).resolve().parents[3]


def test_espeak_words_are_cut_into_recogniser_symbols() -> None:
    assert symbols("pwazˈɔ̃", [], {}) == ["p", "w", "a", "z", "ɔ̃"]
    assert symbols("ma\u200dɪ", ["aɪ"], {"a": "æ"}) == ["m", "aɪ"]
    assert symbols("kˈat", ["aɪ"], {"a": "æ"}) == ["k", "æ", "t"]


def test_every_studio_text_is_in_the_lexicon_in_recogniser_symbols() -> None:
    """Lines, drill words, pairs, phrases and sentences all score; every phoneme is one the recogniser can emit."""
    import yaml

    from tools.content_cli.lexicon import inventory, texts, writable

    g2p = LexiconG2P(ROOT / "content")
    for language in ("fr", "en"):
        known = inventory(language)
        for text in texts(language):
            words = g2p.words(text, language)  # raises KeyError on anything missing
            assert all(writable(p, known) for _, phonemes in words for p in phonemes), text
        gym = yaml.safe_load((ROOT / "content" / "pronunciation" / f"sounds_{language}.yaml").read_text())
        for drill in gym["drills"]:
            assert all(s in gym["phonemes"] for s in drill["sounds"]), drill["key"]
