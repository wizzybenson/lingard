from lingard_api.coach import WARMUP_CARDS, Signals, Slip, Sound, plan_path
from lingard_graphs.agents.learning_coach import CoachPlan, Reasons

SOUND = Sound("fr.pron.u_vs_ou", "/y/ et /u/", "rue", 41.0)
SLIP = Slip("fr.grammar.passe_compose_etre", "Passé composé avec être", "j'ai allé", "je suis allé")
OTHER = Slip("fr.grammar.articles", "Les articles", "le maison", "la maison")
RULES = (("fr.grammar.x", "X"), ("fr.grammar.y", "Y"))


def kinds(signals: Signals) -> list[str]:
    return [stop.kind for stop in plan_path(signals)]


def test_nothing_before_the_goal_and_level_are_known() -> None:
    assert plan_path(Signals(story_ready=False, reviews_due=30, sounds=(SOUND,))) == []


def test_remember_mend_use_then_tune() -> None:
    path = plan_path(Signals(story_ready=True, reviews_due=40, slips=(SLIP,), rules=RULES, sounds=(SOUND,)))
    assert [s.kind for s in path] == ["warmup", "fix", "story", "sounds"], "a slip to mend displaces the new rule"
    assert path[0].count == WARMUP_CARDS, "a handful of cards, never the whole pile"
    assert (path[1].said, path[1].better) == ("j'ai allé", "je suis allé"), "the reason is the learner's own words"
    assert path[3].example == "rue"
    assert all(s.why is None for s in path), "without the coach's plan the app words the reasons"


def test_a_new_rule_comes_after_the_story_and_only_one_a_day() -> None:
    assert kinds(Signals(story_ready=True, rules=RULES)) == ["story", "learn"]
    learned = plan_path(Signals(story_ready=True, rules=RULES, done=frozenset({"lesson"})))
    assert learned[-1].done and learned[-1].node_key is None, "the stop is ticked, not refilled with the next rule"


def test_done_today_ticks_stops_without_hiding_them() -> None:
    path = plan_path(Signals(story_ready=True, reviews_due=0, sounds=(SOUND,), done=frozenset({"review", "story"})))
    assert [(s.kind, s.done) for s in path] == [("warmup", True), ("story", True), ("sounds", False)]


def test_the_coachs_choices_fill_the_path_with_its_reasons() -> None:
    plan = CoachPlan(
        fix="fr.grammar.articles",
        learn="fr.grammar.y",
        why=Reasons(fix="Gender trips you up most.", story="Use it at the bank.", learn="Y comes up next."),
    )
    path = plan_path(Signals(story_ready=True, slips=(SLIP, OTHER), sounds=(SOUND,)), plan)
    assert (path[0].node_key, path[0].why) == ("fr.grammar.articles", "Gender trips you up most.")
    assert path[1].why == "Use it at the bank."
    assert path[2].why is None, "no reason for a sound the coach didn't choose"
    stale = CoachPlan(learn="fr.grammar.gone", why=Reasons(learn="Learn gone."))
    learn = plan_path(Signals(story_ready=True, rules=RULES), stale)[-1]
    assert (learn.node_key, learn.why) == ("fr.grammar.x", None), "a choice no longer offered falls back, unexplained"
