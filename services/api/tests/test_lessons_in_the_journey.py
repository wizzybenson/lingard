"""Lessons woven into the journey (decision 0025): a rule learned by using it, a rule taught in a mission brief, and
verb tables a learner opens by tapping a verb."""

import uuid
from datetime import UTC, datetime

from lingard_curriculum.seed import load_seed, seed_graph
from lingard_graphs.pedagogy.mastery import MasteryState

from .test_phase2_to_5_api import learner


async def test_a_rule_used_well_in_the_city_counts_as_learned(api) -> None:  # type: ignore[no-untyped-def]
    await seed_graph(api.state.curriculum, load_seed(api.settings.content_root, "fr"))
    token, user_id = await learner(api)
    auth = api.bearer(token)
    key = "fr.grammar.present_regular"
    store = api.state.graph_deps.store
    owner = uuid.UUID(user_id)
    await store.save_mastery(owner, [MasteryState(key, p_mastery=0.6, evidence_count=2)], datetime.now(UTC))
    path = {k["node_key"]: k for k in (await api.client.get("/v1/key-points?language=fr", headers=auth)).json()}
    assert path[key]["status"] == "new", "some good uses are not mastery yet"
    await store.save_mastery(owner, [MasteryState(key, p_mastery=0.9, evidence_count=3)], datetime.now(UTC))
    path = {k["node_key"]: k for k in (await api.client.get("/v1/key-points?language=fr", headers=auth)).json()}
    assert path[key]["status"] == "done" and path[key]["learned_in_use"] is True


async def test_a_rule_card_teaches_without_opening_a_lesson(api) -> None:  # type: ignore[no-untyped-def]
    await seed_graph(api.state.curriculum, load_seed(api.settings.content_root, "fr"))
    token, _ = await learner(api)
    card = await api.client.get("/v1/key-points/fr.grammar.present_regular/card", headers=api.bearer(token))
    assert card.status_code == 200
    body = card.json()
    assert body["rule"] and body["teach"] and body["models"] and body["watch_out"]
    assert any(step.get("verb") for step in body["teach"]), "the regular present shows a verb's table"
    lessons = (await api.client.get("/v1/lessons", headers=api.bearer(token))).json()
    assert lessons == [], "reading the card opens no lesson"
    missing = await api.client.get("/v1/key-points/fr.grammar.nope/card", headers=api.bearer(token))
    assert missing.status_code == 404

    from lingard_live.tts import ScriptedTts

    api.state.tts = tts = ScriptedTts()  # the card can be heard, right before speaking
    say = "/v1/key-points/fr.grammar.present_regular/say"
    for part, line in (("model", body["models"][0]), ("better", body["watch_out"][0]["better"])):
        heard = await api.client.get(say, params={"part": part, "index": 0}, headers=api.bearer(token))
        assert heard.status_code == 200 and heard.content[:4] == b"RIFF" and tts.spoken[-1] == line
    teach = [x.replace("**", "") for step in body["teach"] for x in step["examples"]]
    heard = await api.client.get(say, params={"part": "teach", "index": 0}, headers=api.bearer(token))
    assert heard.status_code == 200 and tts.spoken[-1] == teach[0]
    beyond = await api.client.get(say, params={"part": "model", "index": 99}, headers=api.bearer(token))
    assert beyond.status_code == 404


async def test_a_lesson_teaches_before_its_games(api) -> None:  # type: ignore[no-untyped-def]
    from lingard_live.tts import ScriptedTts

    await seed_graph(api.state.curriculum, load_seed(api.settings.content_root, "en"))
    token, _ = await learner(api)
    auth = api.bearer(token)
    opened = await api.client.post("/v1/key-points/en.grammar.present_simple_continuous", headers=auth)
    lesson_id = opened.json()["id"]
    content = (await api.client.get(f"/v1/lessons/{lesson_id}", headers=auth)).json()["content"]
    assert content["teach"] and content["games"]
    examples = [x for step in content["teach"] for x in step["examples"]]
    assert examples, "the teaching has examples to hear"
    api.state.tts = tts = ScriptedTts()
    said = await api.client.get(f"/v1/lessons/{lesson_id}/say", params={"part": "teach", "index": 0}, headers=auth)
    assert said.status_code == 200 and tts.spoken[-1] == examples[0].replace("**", "")


async def test_verb_tables_open_from_any_verb_in_a_sentence(api) -> None:  # type: ignore[no-untyped-def]
    from lingard_live.tts import ScriptedTts

    token, _ = await learner(api)
    auth = api.bearer(token)
    node = {"node": "fr.grammar.present_regular"}
    fr = (await api.client.get("/v1/conjugations/fr", params=node, headers=auth)).json()
    assert fr["focus"] == ["present"]
    assert fr["index"]["travaillons"] == "travailler" and fr["index"]["suis"] == "etre" and fr["index"]["ai"] == "avoir"
    assert "été" not in fr["index"], "« l'été » is the summer far more often"
    assert fr["tenses"][0]["tense"] == "present", "the easiest tense first"

    parler = (await api.client.get("/v1/conjugations/fr/parler", headers=auth)).json()
    present = next(t for t in parler["tenses"] if t["tense"] == "present")["forms"]
    assert [(f["stem"], f["ending"]) for f in present] == [
        ("parl", "e"),
        ("parl", "es"),
        ("parl", "e"),
        ("parl", "ons"),
        ("parl", "ez"),
        ("parl", "ent"),
    ]
    assert not parler["irregular"]
    aller = (await api.client.get("/v1/conjugations/fr/aller", headers=auth)).json()
    passe = next(t for t in aller["tenses"] if t["tense"] == "passe_compose")["forms"]
    assert (passe[0]["subject"], passe[0]["aux"], passe[0]["stem"], passe[0]["ending"]) == ("je", "suis", "all", "é")
    assert passe[3]["ending"] == "és", "the participle's ending, with agreement after être"
    assert aller["irregular"]

    api.state.tts = tts = ScriptedTts()
    heard = await api.client.get(
        "/v1/conjugations/fr/avoir/say", params={"tense": "passe_compose", "person": 0}, headers=auth
    )
    assert heard.status_code == 200 and tts.spoken[-1] == "j'ai eu"
    assert (await api.client.get("/v1/conjugations/fr/nope", headers=auth)).status_code == 404

    en = (await api.client.get("/v1/conjugations/en", params={"node": "en.grammar.past_simple"}, headers=auth)).json()
    assert en["focus"] == ["past_simple"] and en["index"]["went"] == "go" and en["index"]["studied"] == "study"
    assert "answer" not in en["index"] and en["index"]["answered"] == "answer", "a bare regular form may be a noun"
    study = (await api.client.get("/v1/conjugations/en/study", headers=auth)).json()
    third = next(t for t in study["tenses"] if t["tense"] == "present_simple")["forms"][2]
    assert (third["stem"], third["ending"]) == ("stud", "ies")
