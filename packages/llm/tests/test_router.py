from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from lingard_llm.config import LLMConfig, ModelSpec
from lingard_llm.prompts import Prompt, PromptRegistry
from lingard_llm.router import LLMRouter, StructuredOutputError
from lingard_llm.testing import MissingFixtureError, RecordedChatModel, ScriptedChatModel, fixture_key
from lingard_llm.usage import MemoryUsageSink

ROOT = Path(__file__).resolve().parents[3]
PROMPT = Prompt(name="test", version=1, template="hi $name")


def config(*models: str, retries: int = 0) -> LLMConfig:
    price = {"input": 1.0, "output": 2.0, "cache_read": 0.1, "source_url": "x", "as_of": "2026-10-14"}
    return LLMConfig.model_validate(
        {
            "tiers": {
                "fast": {
                    "retries": retries,
                    "models": [{"provider": "scripted", "model": m, "price": price} for m in models],
                }
            }
        }
    )


def router_with(models: dict[str, ScriptedChatModel], cfg: LLMConfig) -> tuple[LLMRouter, MemoryUsageSink]:
    sink = MemoryUsageSink()

    def factory(spec: ModelSpec) -> BaseChatModel:
        return models[spec.model]

    return LLMRouter(cfg, factory=factory, sink=sink), sink


async def test_shipped_config_maps_tiers_to_current_claude_models() -> None:
    cfg = LLMConfig.load(ROOT / "config/llm.yaml")
    assert cfg.tier("fast").models[0].model == "claude-haiku-5-5"
    assert cfg.tier("mid").models[0].model == "claude-sonnet-5-5"
    assert cfg.tier("frontier").models[0].model == "claude-opus-5-5"
    assert all(s.price and s.price.source_url and s.price.as_of for t in cfg.tiers.values() for s in t.models)


async def test_text_records_usage_with_prompt_version_and_cost() -> None:
    model = ScriptedChatModel(queue=["bonjour"], model_name="a")
    router, sink = router_with({"a": model}, config("a"))
    out = await router.text("fast", PROMPT, [HumanMessage(content="salut")], trace_id="t1")
    assert out == "bonjour"
    [record] = sink.records
    assert (record.prompt, record.tier, record.model, record.trace_id) == ("test@v1", "fast", "a", "t1")
    assert record.cost_usd > 0


async def test_fallback_engages_when_primary_fails() -> None:
    primary = ScriptedChatModel(queue=["never"], fail_times=1, model_name="a")
    backup = ScriptedChatModel(queue=["from backup"], model_name="b")
    router, _ = router_with({"a": primary, "b": backup}, config("a", "b"))
    assert await router.text("fast", PROMPT, [HumanMessage(content="x")]) == "from backup"


async def test_retry_before_fallback() -> None:
    primary = ScriptedChatModel(queue=["second try"], fail_times=1, model_name="a")
    router, _ = router_with({"a": primary}, config("a", retries=1))
    assert await router.text("fast", PROMPT, [HumanMessage(content="x")]) == "second try"


async def test_stream_yields_pieces() -> None:
    model = ScriptedChatModel(queue=["Bonjour. Vous allez bien ?"], model_name="a")
    router, sink = router_with({"a": model}, config("a"))
    pieces = [p async for p in router.stream("fast", PROMPT, [HumanMessage(content="x")])]
    assert "".join(pieces) == "Bonjour. Vous allez bien ?"
    assert len(pieces) > 1
    assert sink.records and sink.records[0].output_tokens > 0


class Verdict(BaseModel):
    ok: bool
    reason: str


async def test_structured_parses_and_repairs_once() -> None:
    model = ScriptedChatModel(queue=["not json", 'Sure: {"ok": true, "reason": "fine"}'], model_name="a")
    router, _ = router_with({"a": model}, config("a"))
    verdict = await router.structured("fast", PROMPT, Verdict, [HumanMessage(content="judge")])
    assert verdict == Verdict(ok=True, reason="fine")
    assert "invalid" in str(model.calls[1][-1].content)


async def test_structured_gives_up() -> None:
    model = ScriptedChatModel(queue=["nope", "still nope"], model_name="a")
    router, _ = router_with({"a": model}, config("a"))
    with pytest.raises(StructuredOutputError):
        await router.structured("fast", PROMPT, Verdict, [HumanMessage(content="judge")])


def test_anthropic_system_prefix_gets_cache_breakpoint() -> None:
    router, _ = router_with({}, config("a"))
    assert router.messages("fast", "persona", "hi")[0].content == "persona"
    cfg = LLMConfig.load(ROOT / "config/llm.yaml")
    anthropic_router = LLMRouter(cfg, available=lambda provider: provider == "anthropic")
    system = anthropic_router.messages("fast", "persona", "hi")[0]
    assert isinstance(system.content, list)
    assert system.content[0]["cache_control"] == {"type": "ephemeral"}  # type: ignore[index]


def test_prompt_registry_latest_and_pins(tmp_path: Path) -> None:
    (tmp_path / "actor").mkdir()
    (tmp_path / "actor" / "v1.md").write_text("one $x")
    (tmp_path / "actor" / "v2.md").write_text("two $x")
    assert PromptRegistry(tmp_path).get("actor").render(x="!") == "two !"
    assert PromptRegistry(tmp_path, pins={"actor": 1}).get("actor").ref == "actor@v1"
    with pytest.raises(KeyError):
        PromptRegistry(tmp_path).get("actor").render()


async def test_recorded_model_replays_and_records(tmp_path: Path) -> None:
    messages = [HumanMessage(content="Bonjour")]
    replay = RecordedChatModel(fixtures_dir=tmp_path)
    with pytest.raises(MissingFixtureError):
        await replay.ainvoke(messages)
    recorder = RecordedChatModel(fixtures_dir=tmp_path, inner=ScriptedChatModel(queue=["Salut"]), record=True)
    assert (await recorder.ainvoke(messages)).content == "Salut"
    assert (tmp_path / f"{fixture_key(messages)}.json").is_file()
    assert (await replay.ainvoke(messages)).content == "Salut"


def test_only_providers_with_keys_are_used(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = LLMConfig.load(ROOT / "config/llm.yaml")
    for variable in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    router = LLMRouter(cfg)
    with pytest.raises(RuntimeError, match="set one of ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY"):
        router.specs("fast")

    monkeypatch.setenv("GOOGLE_API_KEY", "g-test")
    assert [s.provider for s in router.specs("mid")] == ["google"]
    assert router.primary_provider("fast") == "google"

    monkeypatch.setenv("OPENAI_API_KEY", "o-test")
    assert [s.model for s in router.specs("frontier")] == ["gpt-6-astra", "gemini-3.1-pro-preview"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", " ")  # blank counts as unset
    assert router.primary_provider("fast") == "openai"


def test_custom_factories_see_every_provider() -> None:
    router, _ = router_with({}, config("a"))
    assert [s.model for s in router.specs("fast")] == ["a"]


def test_render_split_separates_the_cacheable_prefix() -> None:
    prompt = Prompt(name="t", version=1, template="Rules for $lang.\n=== per call ===\nTurn: $turn\n")
    assert prompt.render_split(lang="fr", turn="Bonjour") == ("Rules for fr.", "Turn: Bonjour")
    assert PROMPT.render_split(name="x") == ("hi x", "")


def test_assessor_prompt_keeps_the_turn_out_of_the_cached_prefix() -> None:
    prompt = PromptRegistry(ROOT / "prompts").get("utterance_assessor")
    prefix, per_call = prompt.render_split(
        exam="E", language_name="L", learner_band=6, scale_name="S", npc_name="N", last_npc_line="NPC-LINE",
        transcript="TRANSCRIPT", targets="T", dimensions="D", scale_desc="SD", candidate_nodes="NODES",
    )  # fmt: skip
    assert "NODES" in prefix and "TRANSCRIPT" not in prefix and "NPC-LINE" not in prefix
    assert "TRANSCRIPT" in per_call
