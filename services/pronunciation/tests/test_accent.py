import numpy as np

from lingard_pronunciation.accent import PAD_FRAMES, analyse
from lingard_pronunciation.gop import PhonemeScore
from lingard_pronunciation.gym import Drill, partners, target_score

RATE = 16_000
VOWELS = {"o", "ə", "æ"}
WORDS = [("photograph", ["f", "o", "t", "ə", "ɡ", "r", "æ", "f"])]


def syllables(levels: list[tuple[float, float, float]]) -> tuple[bytes, list[PhonemeScore]]:
    """Speech-like audio: per vowel (seconds, loudness, Hz), each after a short consonant; spans in 20 ms frames."""
    chunks, spans, t = [], [], 0.0
    phonemes = WORDS[0][1]
    vowel_levels = iter(levels)
    for p in phonemes:
        seconds, amp, hz = next(vowel_levels) if p in VOWELS else (0.06, 0.02, 0.0)
        n = int(seconds * RATE)
        x = np.arange(n) / RATE
        chunks.append(amp * np.sin(2 * np.pi * hz * x) if hz else amp * np.random.default_rng(1).standard_normal(n))
        start = int(t / 0.02) + PAD_FRAMES
        t += seconds
        spans.append(PhonemeScore(p, start, int(t / 0.02) + PAD_FRAMES - 1, 0.0, 95.0, None))
    pcm = (np.concatenate(chunks) * 32767).astype(np.int16).tobytes()
    return pcm, spans


def test_word_stress_is_where_the_syllable_stands_out() -> None:
    model = syllables([(0.22, 0.5, 220), (0.08, 0.15, 170), (0.12, 0.25, 180)])  # PHO-to-graph
    wrong = syllables([(0.09, 0.15, 170), (0.22, 0.5, 230), (0.12, 0.25, 180)])  # pho-TO-graph
    result = analyse(wrong[0], wrong[1], model[0], model[1], WORDS, VOWELS)
    [word] = result["stress"]["words"]
    assert word["expected"] == 0 and word["yours"] == 1 and result["stress"]["score"] == 0
    assert word["syllables"][0].startswith("f")
    same = analyse(model[0], model[1], model[0], model[1], WORDS, VOWELS)
    assert same["stress"]["score"] == 100 and same["rhythm"]["score"] > 95


def test_pairs_set_each_trained_sound_against_its_partner_and_unchecked_sounds_go_by_ear() -> None:
    lexicon = {"rue": ["ʁ", "y"], "roue": ["ʁ", "u"], "tu": ["t", "y"], "tout": ["t", "u"]}
    drill = Drill("d", ("y", "u"), ("rue",), (("rue", "roue"), ("tu", "tout")), (), "x")
    assert partners(drill, lexicon.__getitem__) == {"y": ["u"], "u": ["y"]}
    words = [{"phonemes": [{"phoneme": "ʁ", "score": 90.0}, {"phoneme": "y", "score": 20.0, "checked": True}]}]
    assert target_score(drill, words) == (20.0, False)
    unchecked = [{"phonemes": [{"phoneme": "ʁ", "score": 90.0}, {"phoneme": "y", "score": 20.0, "checked": False}]}]
    assert target_score(drill, unchecked) == (90.0, True), "an unreliable contrast is compared by ear, not failed"


def test_a_contrast_separated_nine_times_in_ten_both_ways_decides_alone(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import yaml

    from lingard_pronunciation.calibration import load_calibration

    (tmp_path / "pronunciation").mkdir()
    data = {
        "model": "m",
        "scale": {},
        "contrasts": {
            "æ ʌ": {
                "threshold": -1.0,
                "width": 0.5,
                "native_pass": 1.0,
                "caught": 1.0,
                "reliable": True,
                "n": [12, 12],
            },
            "j ∅": {"threshold": 0.3, "width": 2.0, "native_pass": 1.0, "caught": 1.0, "reliable": True, "n": [4, 4]},
            "e ɛ": {"threshold": 0.0, "width": 0.5, "native_pass": 0.68, "caught": 0.48, "reliable": False},
        },
    }
    (tmp_path / "pronunciation" / "calibration_en.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    cal = load_calibration(tmp_path, "en", "m")
    assert cal is not None and cal.strong("æ", "ʌ") and not cal.strong("e", "ɛ")
    assert not cal.strong("j", "∅"), "four takes a side can't make a contrast decide alone"


def test_an_octave_slip_of_the_pitch_tracker_is_folded_back() -> None:
    import numpy as np

    from lingard_pronunciation.accent import fold_octaves

    folded = fold_octaves(np.array([0.5, -2.0, -13.1, 12.4, 7.0]))
    assert np.allclose(folded, [0.5, -2.0, -1.1, 0.4, 7.0]), "a jump of an octave is a tracking error; 7 is a real rise"
