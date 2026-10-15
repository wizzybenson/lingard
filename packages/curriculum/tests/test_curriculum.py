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
from lingard_curriculum.seed import lesson_gaps, load_seed, seed_graph
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
