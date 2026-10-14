import json
from collections.abc import Iterator
from pathlib import Path

from lingard_llm import LLMConfig, LLMRouter, PromptRegistry
from lingard_llm.testing import ScriptedChatModel
from tools.content_cli.review_golden import ROOT, load, machine_review, review

ROWS = [
    {"text": "Je ne pas comprends.", "has_error": True, "node_key": "fr.grammar.negation",
     "correction": "Je ne comprends pas.", "origin": "drafted", "reviewed": False},
    {"text": "C'est pas grave.", "has_error": False, "origin": "drafted", "reviewed": False},
    {"text": "Il a demandé une question.", "has_error": True, "node_key": "fr.lex.education",
     "accept_node_keys": ["fr.grammar.questions"], "correction": "Il a posé une question.",
     "origin": "drafted", "reviewed": False},
    {"text": "Quoi tu veux ?", "has_error": True, "node_key": "fr.grammar.questions",
     "correction": "Qu'est-ce que tu veux ?", "origin": "drafted", "reviewed": False},
    {"text": "Bonjour.", "has_error": False, "origin": "curriculum"},
]  # fmt: skip


def _file(tmp_path: Path) -> Path:
    path = tmp_path / "fr.drafted.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ROWS))
    return path


def _answers(*values: str) -> Iterator[str]:
    return iter(values)


def test_decisions_are_saved_as_they_are_made(tmp_path: Path) -> None:
    path = _file(tmp_path)
    answers = _answers("a", "x", "c", "s", "d", "q")
    decided = review(path, "Ana", ask=lambda _: next(answers), out=lambda _: None)
    rows = load(path)
    assert decided == 2
    assert rows[0] == {**ROWS[0], "reviewed": True, "reviewer": "Ana"}
    # "x" is rejected and "c" is refused on a row marked correct; the reviewer then skips it.
    assert rows[1]["reviewed"] is False
    assert "Il a demandé une question." not in {r["text"] for r in rows}  # deleted
    assert rows[-1] == ROWS[-1], "curriculum rows are never touched"


def test_flip_and_correct_and_resume(tmp_path: Path) -> None:
    path = _file(tmp_path)
    answers = _answers("s", "f", "fr.grammar.negation", "Ce n'est pas grave.", "f", "c", "Que veux-tu ?")
    review(path, "Ana", ask=lambda _: next(answers), out=lambda _: None)
    rows = {r["text"]: r for r in load(path)}
    assert rows["Je ne pas comprends."]["reviewed"] is False  # skipped
    flipped_to_wrong = rows["C'est pas grave."]
    assert flipped_to_wrong["has_error"] and flipped_to_wrong["correction"] == "Ce n'est pas grave."
    flipped_to_right = rows["Il a demandé une question."]
    assert not flipped_to_right["has_error"]
    assert not {"node_key", "accept_node_keys", "correction"} & flipped_to_right.keys()
    assert rows["Quoi tu veux ?"]["correction"] == "Que veux-tu ?"

    answers = _answers("a", "q")
    review(path, "Ben", ask=lambda _: next(answers), out=lambda _: None)
    assert {r["text"]: r for r in load(path)}["Je ne pas comprends."]["reviewer"] == "Ben"


def test_unknown_node_key_is_refused(tmp_path: Path) -> None:
    path = _file(tmp_path)
    answers = _answers("s", "f", "fr.grammar.negaton", "Ce n'est pas grave.", "q")
    review(path, "Ana", frozenset({"fr.grammar.negation"}), ask=lambda _: next(answers), out=lambda _: None)
    assert {r["text"]: r for r in load(path)}["C'est pas grave."]["has_error"] is False


async def test_machine_review_records_verdicts_without_marking_rows_reviewed(tmp_path: Path) -> None:
    replies = iter(
        [
            {"verdict": "accept", "reason": "classic negation error"},
            {"verdict": "delete", "reason": "spoken register, unfair either way"},
            {"verdict": "fix", "correction": "Il a posé une question.", "node_key": "fr.grammar.nope", "reason": "x"},
            {"verdict": "fix", "correction": "Que veux-tu ?", "node_key": "fr.grammar.questions", "reason": "better"},
        ]
    )
    model = ScriptedChatModel(responder=lambda _: json.dumps(next(replies)))
    config = LLMConfig.model_validate({"tiers": {"frontier": {"models": [{"provider": "scripted", "model": "judge"}]}}})
    router = LLMRouter(config, factory=lambda _spec: model)
    path = _file(tmp_path)
    nodes = frozenset({"fr.grammar.negation", "fr.grammar.questions", "fr.lex.education"})
    counts = await machine_review(path, "fr", router, PromptRegistry(ROOT / "prompts"), nodes, "Canada")
    rows = {r["text"]: r for r in load(path)}
    assert counts == {"accept": 2, "delete": 1, "fix": 1}
    assert all(r.get("reviewed") is not True for r in rows.values())
    assert rows["C'est pas grave."]["excluded"] is True
    unknown_node = rows["Il a demandé une question."]
    assert unknown_node["correction"] == "Il a posé une question." and "unapplied" in unknown_node["machine_review"]
    assert rows["Quoi tu veux ?"]["correction"] == "Que veux-tu ?"
    assert rows["Quoi tu veux ?"]["machine_review"]["original"]["correction"] == "Qu'est-ce que tu veux ?"
    assert "machine_review" not in rows["Bonjour."], "only drafted rows are machine-reviewed"
    assert await machine_review(path, "fr", router, PromptRegistry(ROOT / "prompts"), nodes, "Canada") == {}
