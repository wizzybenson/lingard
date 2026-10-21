from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import create_async_engine

from lingard_contracts.common import Language, Skill
from lingard_curriculum.conjugation import FrenchConjugator
from lingard_curriculum.graph import CurriculumGraph, InMemoryCurriculumGraph
from lingard_curriculum.models import CurriculumNode
from lingard_curriculum.packs import PackLibrary, ielts_overall
from lingard_curriculum.seed import SeedBundle, lesson_gaps, load_seed, seed_graph
from lingard_curriculum.sql import SqlCurriculumGraph, curriculum_tables

CONTENT = Path(__file__).resolve().parents[3] / "content"


@pytest.mark.parametrize("language", ["fr", "en"])
def test_seed_loads_and_every_grammar_node_has_a_lesson(language: Language) -> None:
    bundle = load_seed(CONTENT, language)
    kinds = {n.kind for n in bundle.nodes}
    assert kinds == {"cando", "function", "grammar", "lexset", "pron", "tasktype", "conj_cell"}
    assert lesson_gaps(bundle) == []
    assert all(n.source_url and n.as_of for n in bundle.nodes)
    candos = [n for n in bundle.nodes if n.kind == "cando"]
    assert {(n.skill, n.band) for n in candos} == {(s, b) for s in Skill for b in range(4, 11)}


# The scope audited on 2026-10-20 against the British Council/EAQUALS Core Inventory (English) and France Éducation
# international's inventory of CEFR key content (French), banded with North & Piccardo's CLB/NCLC–CEFR alignment
# (CLB 4 = A2, 5–7 = B1, 8 = B2, 9 = B2+, 10 = C1). Removing any of these is a gap in what a learner is taught.
SCOPE: dict[str, set[str]] = {
    "fr": {
        "present_regular",
        "present_irregular",
        "cest_il_est_il_y_a",
        "articles_gender",
        "adjectifs_accord",
        "possessifs_demonstratifs",
        "prepositions_lieu",
        "negation",
        "quantites",
        "questions",
        "futur_proche",
        "verbes_pronominaux",
        "passe_recent_en_train_de",
        "passe_compose_avoir",
        "passe_compose_etre",
        "imparfait",
        "passe_compose_ou_imparfait",
        "expressions_de_temps",
        "comparatif_superlatif",
        "imperatif",
        "pronoms_cod_coi",
        "pronoms_y_en",
        "adverbes",
        "indefinis_ne_que",
        "futur_simple",
        "conditionnel_present",
        "relatifs_qui_que_ou",
        "si_present_futur",
        "si_imparfait",
        "relatif_dont",
        "doubles_pronoms",
        "pronoms_demonstratifs_possessifs",
        "plus_que_parfait",
        "subjonctif_present",
        "gerondif",
        "connecteurs_logiques",
        "conditionnel_passe",
        "futur_anterieur",
        "accord_participe_avoir",
        "si_plus_que_parfait",
        "subjonctif_vs_indicatif",
        "subjonctif_conjonctions",
        "discours_rapporte",
        "voix_passive",
        "infinitif_passe_participe_present",
        "concordance_des_temps",
        "subjonctif_passe",
        "relatifs_composes",
        "nominalisation",
        "mise_en_relief",
        "hypothese_concession_nuancees",
    },
    "en": {
        "present_simple_continuous",
        "there_is_it_is",
        "subject_verb_agreement",
        "adverbs_of_frequency",
        "articles",
        "pronouns_possessives",
        "prepositions_time_place",
        "past_simple",
        "comparatives",
        "questions",
        "can_could_be_able_to",
        "countable_uncountable",
        "quantifiers",
        "present_perfect",
        "past_continuous",
        "future_forms",
        "zero_conditional_time_clauses",
        "modals_obligation",
        "first_conditional",
        "relative_clauses",
        "gerund_infinitive",
        "used_to_would",
        "present_perfect_or_past_simple",
        "too_enough_so_such",
        "phrasal_verbs",
        "substitution_ellipsis",
        "second_conditional",
        "past_perfect",
        "passive_voice",
        "linking_words",
        "question_tags",
        "present_perfect_continuous",
        "modals_of_deduction",
        "unless_in_case",
        "word_formation",
        "third_conditional",
        "reported_speech",
        "non_defining_relatives",
        "wish_if_only",
        "past_modals",
        "causative",
        "future_continuous_perfect",
        "mixed_conditionals",
        "participle_clauses",
        "cleft_sentences",
        "hedging",
        "nominalisation",
        "inversion",
    },
}


@pytest.mark.parametrize("language", ["fr", "en"])
def test_the_audited_grammar_scope_is_taught_in_order(language: Language) -> None:
    nodes = {n.key: n for n in load_seed(CONTENT, language).nodes if n.kind == "grammar"}
    assert {k.split(".")[-1] for k in nodes} >= SCOPE[language]
    bundle = load_seed(CONTENT, language)
    for edge in (e for e in bundle.edges if e.kind == "prereq" and e.from_key in nodes):
        assert edge.to_key in nodes, f"{edge.from_key} needs a missing {edge.to_key}"
        assert nodes[edge.to_key].band <= nodes[edge.from_key].band, f"{edge.from_key} needs a later {edge.to_key}"
    for node in nodes.values():
        lesson = node.payload["lesson"]
        assert len(lesson["examples"]) >= 2 and lesson["common_errors"], node.key
    assert {n.band for n in nodes.values()} == set(range(4, 11)), "grammar at every band from 4 to 10"


def test_vocabulary_functions_and_sounds_cover_the_same_ground_in_both_languages() -> None:
    def keys(language: Language, kind: str) -> set[str]:
        return {n.key.split(".", 2)[2] for n in load_seed(CONTENT, language).nodes if n.kind == kind}

    for kind in ("lexset", "function"):
        assert keys("fr", kind) == keys("en", kind), kind
    assert len(keys("fr", "lexset")) >= 30 and len(keys("fr", "function")) >= 30
    for language in ("fr", "en"):
        assert len(keys(language, "pron")) >= 15, language


def test_auto_requires_and_task_exercises() -> None:
    bundle = load_seed(CONTENT, "fr")
    edges = {(e.from_key, e.to_key, e.kind) for e in bundle.edges}
    assert ("fr.cando.speaking.nclc7", "fr.grammar.si_imparfait", "requires") in edges
    assert ("fr.cando.listening.nclc7", "fr.grammar.si_imparfait", "requires") not in edges
    assert ("fr.task.tef_eo_section_b", "fr.cando.speaking.nclc8", "exercises") in edges
    assert ("fr.grammar.si_plus_que_parfait", "fr.grammar.plus_que_parfait", "prereq") in edges


def test_every_band_4_to_10_has_speaking_requirements_in_both_languages() -> None:
    for language in ("fr", "en"):
        bundle = load_seed(CONTENT, language)
        for band in range(4, 11):
            cando = f"{language}.cando.speaking.{'nclc' if language == 'fr' else 'clb'}{band}"
            assert any(e.from_key == cando and e.kind == "requires" for e in bundle.edges), cando


def test_french_conjugation_engine() -> None:
    fr = FrenchConjugator.load(CONTENT / "curriculum/fr/conjugation.yaml")
    assert fr.with_subjects("aller", "passe_compose")[3] == "nous sommes allés"
    assert fr.with_subjects("etre", "imparfait")[0] == "j'étais"
    assert fr.with_subjects("avoir", "subjonctif_present")[2] == "qu'il ait"
    assert fr.with_subjects("devoir", "conditionnel_passe")[0] == "j'aurais dû"
    assert fr.conjugate("faire", "futur_simple")[5] == "feront"
    assert fr.conjugate("finir", "imparfait")[3] == "finissions"


def test_pack_conversion_tables() -> None:
    library = PackLibrary(CONTENT)
    ielts = library.conversion("ielts_gt")
    assert ielts.to_level(Skill.LISTENING, 8.5) == 10
    assert ielts.to_level(Skill.LISTENING, 8.0) == 9
    assert ielts.to_level(Skill.READING, 3.0) == 0
    assert ielts.min_score_for(Skill.WRITING, 9) == 7.0
    assert ielts.min_score_for(Skill.WRITING, 12) == 7.5
    tef = library.conversion("tef_canada")
    assert tef.to_level(Skill.SPEAKING, 310) == 7
    assert tef.to_level(Skill.SPEAKING, 309) == 6
    assert tef.to_level(Skill.READING, 263) == 10
    pack = library.pack("tef_canada")
    assert [s.id for s in pack.ordered_sections()] == [
        "comprehension_ecrite",
        "comprehension_orale",
        "expression_ecrite",
        "expression_orale",
    ]
    assert pack.max_score(Skill.LISTENING) == 360
    assert library.pack("ielts_gt").section("writing").tasks[1].min_words == 250


def test_ielts_overall_rounding() -> None:
    assert ielts_overall([6.5, 6.5, 5.0, 7.0]) == 6.5  # 6.25 → 6.5
    assert ielts_overall([4.0, 3.5, 4.0, 4.0]) == 4.0  # 3.875 → 4.0
    assert ielts_overall([6.0, 6.0, 6.0, 6.5]) == 6.0  # 6.125 → 6.0
    assert ielts_overall([7.0, 7.0, 7.0, 8.0]) == 7.5  # 7.25 → 7.5
    assert ielts_overall([6.5, 6.5, 7.0, 7.0]) == 7.0  # 6.75 → 7.0


@pytest.fixture(params=["memory", "postgres"])
async def graph(request: pytest.FixtureRequest) -> AsyncIterator[CurriculumGraph]:
    if request.param == "memory":
        yield InMemoryCurriculumGraph()
        return
    async with request.getfixturevalue("pg_schema_factory")() as (url, schema):
        engine = create_async_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
        metadata = MetaData(schema=schema)
        nodes, edges = curriculum_tables(metadata)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        yield SqlCurriculumGraph(engine, nodes, edges)
        await engine.dispose()


async def test_graph_contract_seed_query_and_rereview_on_edit(graph: CurriculumGraph) -> None:
    bundle = load_seed(CONTENT, "fr")
    await seed_graph(graph, bundle)
    band7 = await graph.nodes("fr", kinds=["grammar"], band=7)
    assert "fr.grammar.si_imparfait" in {n.key for n in band7}
    assert all(n.reviewed for n in band7)
    requires = await graph.edges("fr.cando.speaking.nclc7", "requires")
    assert any(e.to_key == "fr.func.negotiate" for e in requires)
    incoming = await graph.edges("fr.grammar.plus_que_parfait", "prereq", direction="in")
    assert {e.from_key for e in incoming} >= {"fr.grammar.si_plus_que_parfait"}

    node = await graph.get("fr.grammar.si_imparfait")
    assert node is not None
    edited: CurriculumNode = node.model_copy(update={"title": "Si + imparfait (révisé)"})
    stored = await graph.upsert_node(edited)
    assert stored.version == 2 and not stored.reviewed
    assert "fr.grammar.si_imparfait" not in {n.key for n in await graph.nodes("fr", kinds=["grammar"], band=7)}
    await graph.mark_reviewed("fr.grammar.si_imparfait", "founder")
    again = await graph.get("fr.grammar.si_imparfait")
    assert again is not None and again.reviewed and again.reviewed_by == "founder"
    unchanged = await graph.upsert_node(again)
    assert unchanged.version == 2 and unchanged.reviewed

    # Seeding: a lesson changed in the repository stays reviewed (repository content is reviewed content), while a
    # node someone un-reviewed stays out until it is reviewed again.
    changed = next(n for n in bundle.nodes if n.key == "fr.grammar.imparfait")
    payload = {**changed.payload, "lesson": {**changed.payload["lesson"], "rule": "Règle réécrite dans le dépôt."}}
    await seed_graph(graph, SeedBundle(nodes=[changed.model_copy(update={"payload": payload})]))
    rewritten = await graph.get("fr.grammar.imparfait")
    assert rewritten is not None and rewritten.version == 2 and rewritten.reviewed
    await graph.unmark_reviewed("fr.grammar.futur_simple")
    await seed_graph(graph, bundle)
    held = await graph.get("fr.grammar.futur_simple")
    assert held is not None and not held.reviewed


@pytest.mark.parametrize("language", ["fr", "en"])
def test_every_word_set_and_phrase_set_has_a_lesson(language: Language) -> None:
    for node in load_seed(CONTENT, language).nodes:
        if node.kind in ("lexset", "function"):
            lesson = node.payload["lesson"]
            assert lesson["rule"] and len(lesson["examples"]) >= 2 and lesson["common_errors"], node.key
            assert all(e["wrong"] != e["right"] for e in lesson["common_errors"]), node.key


@pytest.mark.parametrize("language", ["fr", "en"])
def test_every_rule_is_taught_before_it_is_practised(language: Language) -> None:
    """Every grammar point teaches a step at a time (decision 0025): at least two steps, each verb table naming a verb
    and tense the conjugation content has, and every highlight closed."""
    from lingard_contracts.planning import TeachStep
    from lingard_curriculum.conjugation import load_conjugator

    root = Path(__file__).resolve().parents[3] / "content"
    conjugator = load_conjugator(root / "curriculum" / language / "conjugation.yaml")
    assert conjugator is not None
    tables = {v.key: {t.tense for t in v.tenses} for v in conjugator.tables().verbs}
    grammar = [n for n in load_seed(root, language).nodes if n.kind == "grammar"]
    for node in grammar:
        steps = [TeachStep.model_validate(s) for s in node.payload["lesson"].get("teach", [])]
        assert len(steps) >= 2, f"{node.key} is not taught step by step"
        for step in steps:
            lines = [step.say, *step.examples, *(c for row in (step.table.rows if step.table else []) for c in row)]
            assert all(line.count("**") % 2 == 0 for line in lines), f"{node.key}: unclosed highlight"
            if step.verb:
                assert step.tense in tables.get(step.verb, set()), f"{node.key}: no table {step.verb}/{step.tense}"
