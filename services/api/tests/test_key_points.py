from lingard_curriculum.seed import load_seed, seed_graph

from .test_phase2_to_5_api import learner


async def test_key_points_are_offered_beside_the_story_and_open_at_once(api) -> None:  # type: ignore[no-untyped-def]
    """Lessons never stand between the learner and the city (founder, 2026-10-21; decision 0025)."""
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
    assert today["next_step"] == "story", "the day can start with no lesson learned"
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
    today = (await api.client.get("/v1/today", headers=auth)).json()
    nxt = today["next_key_point"]
    assert nxt is None or nxt["node_key"] != first_core["node_key"]
    assert today["next_step"] == "story"

    library = (await api.client.get("/v1/key-points?language=fr&every_level=true", headers=auth)).json()
    assert len(library) > len(path) and max(k["band"] for k in library) > max(k["band"] for k in path)

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


async def test_a_word_lesson_lists_its_words_and_speaks_each_line(api) -> None:  # type: ignore[no-untyped-def]
    from lingard_live.tts import ScriptedTts

    await seed_graph(api.state.curriculum, load_seed(api.settings.content_root, "en"))
    token, _ = await learner(api)
    auth = api.bearer(token)
    opened = await api.client.post("/v1/key-points/en.lex.banking", headers=auth)
    lesson_id = opened.json()["id"]
    content = (await api.client.get(f"/v1/lessons/{lesson_id}", headers=auth)).json()["content"]
    assert "current account" in content["words"]
    api.state.tts = tts = ScriptedTts()
    say = f"/v1/lessons/{lesson_id}/say"
    sort_code = content["words"].index("sort code")
    word = await api.client.get(say, params={"part": "word", "index": sort_code}, headers=auth)
    assert word.status_code == 200 and word.content[:4] == b"RIFF" and tts.spoken[-1] == "sort code"
    model = await api.client.get(say, params={"part": "model", "index": 0}, headers=auth)
    assert model.status_code == 200 and tts.spoken[-1] == content["models"][0]
    assert (await api.client.get(say, params={"part": "word", "index": 99}, headers=auth)).status_code == 404
    assert (await api.client.get(say, params={"part": "rule", "index": 0}, headers=auth)).status_code == 422


async def test_a_lesson_left_half_way_keeps_its_answers(api) -> None:  # type: ignore[no-untyped-def]
    """Progress lived only on screen: leaving a lesson before Finish lost every game played (founder, 2026-10-21)."""
    await seed_graph(api.state.curriculum, load_seed(api.settings.content_root, "fr"))
    token, _ = await learner(api, "Nora")
    auth = api.bearer(token)
    opened = await api.client.post("/v1/key-points/fr.grammar.present_regular", headers=auth)
    lesson_id = opened.json()["id"]
    progress = {
        "games": {
            "0": {"answers": ["parle", "", "finis"], "result": None},
            "1": {"answers": ["a"], "result": {"kind": "dictation", "correct": 1, "total": 1, "missed": []}},
        }
    }
    saved = await api.client.put(f"/v1/lessons/{lesson_id}/progress", json=progress, headers=auth)
    assert saved.status_code == 204
    back = (await api.client.get(f"/v1/lessons/{lesson_id}", headers=auth)).json()
    assert back["progress"] == progress and back["status"] == "open"
    other, _ = await learner(api, "Omar")
    stranger = await api.client.put(f"/v1/lessons/{lesson_id}/progress", json=progress, headers=api.bearer(other))
    assert stranger.status_code == 404
