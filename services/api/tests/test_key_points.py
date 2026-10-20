from lingard_curriculum.seed import load_seed, seed_graph

from .test_phase2_to_5_api import learner


async def test_key_points_come_before_the_story_and_open_at_once(api) -> None:  # type: ignore[no-untyped-def]
    await seed_graph(api.state.curriculum, load_seed(api.settings.content_root, "fr"))
    token, _ = await learner(api)
    auth = api.bearer(token)
    await api.client.patch("/v1/me", json={"exam_dates": {"tef_canada": "2027-03-01"}}, headers=auth)
    await api.client.post("/v1/placement", json={"language": "fr", "path": "skip"}, headers=auth)

    path = (await api.client.get("/v1/key-points", params={"language": "fr"}, headers=auth)).json()
    keys = [k["node_key"] for k in path]
    assert keys[:2] == ["fr.grammar.present_regular", "fr.grammar.present_irregular"]  # authored teaching order
    assert all(k["status"] == "new" and k["lesson_id"] is None for k in path)
    assert any(k["core"] for k in path) and any(k["preview"] for k in path)
    assert not any(k["preview"] for k in path if k["core"])
    assert {k["kind"] for k in path} == {"grammar", "lexset", "function"}, "rules, words and phrases"
    first_band = [k["kind"] for k in path if k["band"] == path[0]["band"]]
    assert first_band == sorted(first_band, key=["grammar", "lexset", "function"].index), "rules first in a level"

    today = (await api.client.get("/v1/today", headers=auth)).json()
    first_core = next(k for k in path if k["core"] and k["kind"] == "grammar")
    assert today["next_step"] == "key_points"
    assert today["next_key_point"] == {"node_key": first_core["node_key"], "title": first_core["title"]}

    opened = await api.client.post(f"/v1/key-points/{first_core['node_key']}", headers=auth)
    assert opened.status_code == 201
    lesson_id = opened.json()["id"]
    again = await api.client.post(f"/v1/key-points/{first_core['node_key']}", headers=auth)
    assert again.json()["id"] == lesson_id, "reopening returns the same lesson, never a duplicate"
    lesson = (await api.client.get(f"/v1/lessons/{lesson_id}", headers=auth)).json()["content"]
    assert lesson["kind"] == "key_points" and lesson["rule"] and lesson["models"] and lesson["examples"]
    assert lesson["games"] and lesson["homework"]["targets"] == [first_core["node_key"]]

    await api.client.post(f"/v1/lessons/{lesson_id}/complete", json={"correct": 5, "total": 5}, headers=auth)
    after = {k["node_key"]: k for k in (await api.client.get("/v1/key-points?language=fr", headers=auth)).json()}
    assert after[first_core["node_key"]]["status"] == "done"
    nxt = (await api.client.get("/v1/today", headers=auth)).json()["next_key_point"]
    assert nxt is None or nxt["node_key"] != first_core["node_key"]

    assert (await api.client.post("/v1/key-points/fr.grammar.nope", headers=auth)).status_code == 404
    words = next(k for k in path if k["kind"] == "lexset")
    opened_words = await api.client.post(f"/v1/key-points/{words['node_key']}", headers=auth)
    assert opened_words.status_code == 201
    games = (await api.client.get(f"/v1/lessons/{opened_words.json()['id']}", headers=auth)).json()["content"]["games"]
    assert any(g["kind"] == "fill_the_gap" for g in games)
    assert (await api.client.post("/v1/key-points/fr.task.tef_ce", headers=auth)).status_code == 404


async def test_an_english_key_point_opens_too(api) -> None:  # type: ignore[no-untyped-def]
    """English verb data has its own shape; opening an English lesson must not try to read it as French."""
    await seed_graph(api.state.curriculum, load_seed(api.settings.content_root, "en"))
    token, _ = await learner(api)
    auth = api.bearer(token)
    opened = await api.client.post("/v1/key-points/en.grammar.subject_verb_agreement", headers=auth)
    assert opened.status_code == 201
    lesson = (await api.client.get(f"/v1/lessons/{opened.json()['id']}", headers=auth)).json()["content"]
    assert lesson["kind"] == "key_points" and lesson["games"]
    assert "The controls look complicated." in lesson["models"]
