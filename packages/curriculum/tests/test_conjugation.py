from pathlib import Path

from lingard_curriculum.conjugation import FrenchConjugator

CONJUGATION = Path(__file__).resolve().parents[3] / "content" / "curriculum" / "fr" / "conjugation.yaml"


def test_regular_verbs_are_read_from_their_present_forms() -> None:
    verbs = FrenchConjugator.load(CONJUGATION).verbs
    assert verbs["parler"].regular and verbs["finir"].regular
    assert not verbs["etre"].regular and not verbs["devoir"].regular and not verbs["partir"].regular


def test_tense_names_come_from_the_content() -> None:
    conjugator = FrenchConjugator.load(CONJUGATION)
    assert conjugator.label("passe_compose") == "passé composé"
    assert all(t in conjugator.tense_labels for t in conjugator.tenses)
