from datetime import UTC, datetime, timedelta
from pathlib import Path

from lingard_contracts.common import Skill
from lingard_curriculum.packs import PackLibrary
from lingard_graphs.pedagogy.bands import BandPosterior, IsotonicCalibrator, observe, prior, summarise
from lingard_graphs.pedagogy.config import load_pedagogy
from lingard_graphs.pedagogy.mastery import MasteryState, apply_evidence, bkt_update
from lingard_graphs.pedagogy.review import due_at, new_card, review
from lingard_graphs.pedagogy.selection import Candidate, plan_targets
from lingard_graphs.pedagogy.tickets import Example, Success, record_error, record_success

P = load_pedagogy()
CONTENT = Path(__file__).resolve().parents[3] / "content"
T0 = datetime(2026, 10, 1, 10, tzinfo=UTC)


def test_bkt_moves_in_the_right_direction_and_weight_matters() -> None:
    p = P.bkt.p_init
    up, down = bkt_update(p, True, P.bkt), bkt_update(p, False, P.bkt)
    assert up > p > down - P.bkt.p_transit
    assert bkt_update(p, True, P.bkt, weight=0.2) < up


def test_mastery_reaches_threshold_with_consistent_success() -> None:
    state = MasteryState("fr.grammar.si_imparfait", P.bkt.p_init)
    for i in range(8):
        apply_evidence(state, True, confidence=0.9, difficulty=0.6, context=f"scene{i % 4}", params=P.bkt)
    assert state.p_mastery >= P.bkt.mastered
    assert len(state.contexts) == 4


def test_ticket_lifecycle_open_close_reopen_lesson() -> None:
    rules = P.tickets
    key = "fr.grammar.si_imparfait"
    ticket, events = record_error(None, key, Example(T0, "si j'aurais", "landlord"), 0.6, [], rules)
    assert ticket is None and events == []
    ticket, events = record_error(None, key, Example(T0 + timedelta(hours=2), "si j'aurais", "cafe"), 0.6, [T0], rules)
    assert ticket is not None and [e.kind for e in events] == ["opened"]

    assert record_success(ticket, Success(T0 + timedelta(days=1), "bank"), rules) == []
    assert record_success(ticket, Success(T0 + timedelta(days=1), "cafe"), rules) == []
    assert record_success(ticket, Success(T0 + timedelta(days=1, hours=1), "cafe"), rules) == []
    closed = record_success(ticket, Success(T0 + timedelta(days=2), "landlord"), rules)
    assert [e.kind for e in closed] == ["closed"] and ticket.status == "closed"

    ticket, events = record_error(ticket, key, Example(T0 + timedelta(days=5), "si j'aurais", "cafe"), 0.7, [], rules)
    assert ticket is not None and ticket.status == "reopened" and [e.kind for e in events] == ["reopened"]
    assert ticket.interventions[-1] != ticket.interventions[0], "reopen switches intervention"
    for day, ctx in ((6, "a"), (7, "b"), (7, "c")):
        record_success(ticket, Success(T0 + timedelta(days=day), ctx), rules)
    assert ticket.status == "closed"  # type: ignore[comparison-overlap]  # mypy keeps the "reopened" narrowing
    _, events = record_error(ticket, key, Example(T0 + timedelta(days=9), "x", "y"), 0.7, [], rules)
    assert [e.kind for e in events] == ["reopened", "lesson_needed"]


def test_director_ticket_share_and_failed_setting_rule() -> None:
    tickets = [
        Candidate(f"fr.grammar.t{i}", 0.9 - i / 10, frozenset({"landlord"}) if i == 0 else frozenset())
        for i in range(5)
    ]
    fresh = [Candidate(f"fr.func.f{i}", 0.5) for i in range(10)]
    slots = plan_targets(tickets, fresh, ["landlord", "cafe", "bank"], P.director)
    all_targets = [t for s in slots for t in s.targets]
    share = sum(len(s.ticket_targets) for s in slots) / len(all_targets)
    assert P.director.ticket_share_min <= share <= P.director.ticket_share_max
    landlord = next(s for s in slots if s.setting == "landlord")
    assert "fr.grammar.t0" not in landlord.targets
    assert len(set(all_targets)) == len(all_targets)


def test_band_posterior_narrows_and_reports_interval_and_clb() -> None:
    library = PackLibrary(CONTENT)
    pack, conversion = library.pack("ielts_gt"), library.conversion("ielts_gt")
    post = prior(pack, Skill.SPEAKING, 5.5, P.bands)
    wide = post.interval(0.8)
    for score in (6.5, 6.0, 6.5):
        post = observe(post, pack, Skill.SPEAKING, score, "mock", P.bands)
    narrow = post.interval(0.8)
    assert narrow[1] - narrow[0] < (wide[1] - wide[0]) / 2
    estimate = summarise(post, pack, Skill.SPEAKING, conversion, P.bands, "ielts_gt")
    assert estimate.low80 < estimate.mean < estimate.high80
    assert estimate.clb_nclc_mean in (7, 8)


def test_tef_posterior_uses_point_scale() -> None:
    library = PackLibrary(CONTENT)
    pack = library.pack("tef_canada")
    post = prior(pack, Skill.LISTENING, None, P.bands)
    assert post.mean == 180
    post = observe(post, pack, Skill.LISTENING, 300, "mock", P.bands)
    assert 250 < post.mean <= 300


def test_isotonic_calibration_is_monotone() -> None:
    calibrate = IsotonicCalibrator().fit([5.0, 6.0, 6.5, 7.0, 8.0], [5.5, 5.8, 5.6, 6.5, 7.5])
    outputs = [calibrate(x) for x in (5.0, 6.0, 6.25, 6.5, 7.0, 8.0, 9.0)]
    assert outputs == sorted(outputs)
    assert IsotonicCalibrator()(6.3) == 6.3
    assert BandPosterior(6, 1).probability_at_least(6) == 0.5


def test_fsrs_scheduling_spaces_reviews() -> None:
    card = new_card()
    after_good = review(card, True, now=T0)
    after_again = review(card, False, now=T0)
    assert due_at(after_good) > due_at(after_again)


def test_key_points_put_prerequisites_first_then_the_authored_order() -> None:
    from lingard_curriculum.models import CurriculumNode
    from lingard_graphs.pedagogy.key_points import ordered

    def node(key: str, band: int) -> CurriculumNode:
        return CurriculumNode(
            key=f"fr.grammar.{key}", kind="grammar", language="fr", band=band, title=key, source_url="x", as_of="2026"
        )

    a, b, c, d = node("a", 4), node("b", 4), node("c", 5), node("d", 5)
    order = {n.key: i for i, n in enumerate([b, a, d, c])}
    assert [n.key[-1] for n in ordered([a, b, c, d], {}, order)] == ["b", "a", "d", "c"]
    assert [n.key[-1] for n in ordered([a, b, c, d], {"fr.grammar.d": ["fr.grammar.c"]}, order)] == ["b", "a", "c", "d"]
    cycle = {"fr.grammar.a": ["fr.grammar.b"], "fr.grammar.b": ["fr.grammar.a"]}
    assert len(ordered([a, b], cycle, order)) == 2, "a bad cycle never loops or drops a node"


def test_key_points_lessons_need_no_model_and_cover_every_rule_word_set_and_phrase_set() -> None:
    import random
    from pathlib import Path

    from lingard_curriculum.conjugation import FrenchConjugator
    from lingard_curriculum.seed import load_seed
    from lingard_graphs.graphs.lesson_builder import key_points_lesson
    from lingard_world import load_city

    root = Path(__file__).resolve().parents[3] / "content"
    for language, city in (("fr", "rivemont"), ("en", "ashford")):
        conjugator = FrenchConjugator.load(root / "curriculum/fr/conjugation.yaml") if language == "fr" else None
        for n in load_seed(root, language).nodes:  # type: ignore[arg-type]
            if n.kind not in ("grammar", "lexset", "function"):
                continue
            lesson = key_points_lesson(n, load_city(root, city), n.band, conjugator, random.Random(n.key))
            assert lesson.kind == "key_points" and lesson.models and lesson.examples and lesson.games, n.key
            if n.kind == "lexset":
                gaps = next((g for g in lesson.games if g.kind == "fill_the_gap"), None)
                assert gaps is not None and len(gaps.items) >= 2, f"{n.key}: model sentences use the set's words"
                for item in gaps.items:
                    assert "___" in item.prompt and item.answer not in item.distractors, n.key
