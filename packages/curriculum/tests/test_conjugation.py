import random
from pathlib import Path

from lingard_curriculum.conjugation import EnglishConjugator, FrenchConjugator

CONJUGATION = Path(__file__).resolve().parents[3] / "content" / "curriculum" / "fr" / "conjugation.yaml"
ENGLISH = CONJUGATION.parents[1] / "en" / "conjugation.yaml"


def test_regular_verbs_are_read_from_their_present_forms() -> None:
    verbs = FrenchConjugator.load(CONJUGATION).verbs
    assert verbs["parler"].regular and verbs["finir"].regular
    assert not verbs["etre"].regular and not verbs["devoir"].regular and not verbs["partir"].regular


def test_tense_names_come_from_the_content() -> None:
    conjugator = FrenchConjugator.load(CONJUGATION)
    assert conjugator.label("passe_compose") == "passé composé"
    assert all(t in conjugator.tense_labels for t in conjugator.tenses)


def test_a_grammar_point_drills_the_longest_matching_entry() -> None:
    """« si + imparfait » drills the conditional as well, not just the imparfait its key also contains."""
    conjugator = FrenchConjugator.load(CONJUGATION)
    labels = {prompt.split("(")[-1] for prompt, _ in conjugator.drill("fr.grammar.si_imparfait", random.Random(1))}
    assert labels == {"imparfait)", "conditionnel présent)"}
    assert conjugator.drill("fr.grammar.articles", random.Random(1)) == []


def test_english_drills_irregular_principal_parts() -> None:
    conjugator = EnglishConjugator.load(ENGLISH)
    past = dict(conjugator.drill("en.grammar.past_simple", random.Random(1)))
    assert past["go (past simple)"] == "went" and not any("/" in a for a in past.values())
    both = {
        p.split("(")[-1] for p, _ in conjugator.drill("en.grammar.present_perfect_or_past_simple", random.Random(1))
    }
    assert both == {"past simple)", "past participle)"}
