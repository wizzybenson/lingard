"""LangChain LLM router with fast/mid/frontier tiers, retries, fallbacks, prompt caching and usage capture.

Core adapted from simupatient@69e1bd5:backend/app/agents/providers.py (``LangChainChatProvider``: ``init_chat_model``
construction, structured output, usage capture). Tiers, fallback chains, prompt caching and versioned prompts are new.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ValidationError

from lingard_llm.config import LLMConfig, ModelSpec, Tier
from lingard_llm.prompts import Prompt
from lingard_llm.testing import message_text
from lingard_llm.usage import MemoryUsageSink, UsageCallback, UsageSink

T = TypeVar("T", bound=BaseModel)
ModelFactory = Callable[[ModelSpec], BaseChatModel]

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class StructuredOutputError(ValueError):
    pass


def default_factory(spec: ModelSpec) -> BaseChatModel:
    if spec.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs: dict[str, Any] = {
            "model": spec.model,
            "max_tokens": spec.max_tokens,
            "default_request_timeout": spec.timeout_s,
            "max_retries": 0,  # the router owns retries so fallbacks engage promptly
        }
        if spec.effort:
            kwargs["effort"] = spec.effort
        return ChatAnthropic(**kwargs)
    if spec.provider == "openai":
        try:
            from langchain_openai import ChatOpenAI  # type: ignore[import-not-found,unused-ignore]
        except ImportError as exc:  # optional provider
            raise RuntimeError("install langchain-openai to use provider=openai") from exc
        model: BaseChatModel = ChatOpenAI(model=spec.model, max_tokens=spec.max_tokens, timeout=spec.timeout_s)
        return model
    raise ValueError(f"provider {spec.provider!r} needs an explicit model factory (tests)")


def cached_system(text: str, provider: str, suffix: str | None = None) -> SystemMessage:
    """System prefix with an Anthropic cache breakpoint; ``suffix`` (volatile notes) sits after the breakpoint."""
    if provider == "anthropic":
        blocks: list[str | dict[str, object]] = [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
        if suffix:
            blocks.append({"type": "text", "text": suffix})
        return SystemMessage(content=blocks)
    return SystemMessage(content=f"{text}\n\n{suffix}" if suffix else text)


class LLMRouter:
    def __init__(
        self,
        config: LLMConfig,
        *,
        factory: ModelFactory = default_factory,
        sink: UsageSink | None = None,
    ) -> None:
        self.config = config
        self.sink: UsageSink = sink or MemoryUsageSink()
        self._factory = factory
        self._models: dict[Tier, Runnable[Any, BaseMessage]] = {}
        prices = {spec.model: spec.price for tier in config.tiers.values() for spec in tier.models}
        self._callback = UsageCallback(self.sink, prices)

    def primary_provider(self, tier: Tier) -> str:
        return self.config.tier(tier).models[0].provider

    def runnable(self, tier: Tier) -> Runnable[Any, BaseMessage]:
        if tier not in self._models:
            tier_config = self.config.tier(tier)
            chain: list[Runnable[Any, BaseMessage]] = []
            for spec in tier_config.models:
                model: Runnable[Any, BaseMessage] = self._factory(spec)
                if tier_config.retries:
                    model = model.with_retry(stop_after_attempt=tier_config.retries + 1, wait_exponential_jitter=True)
                chain.append(model)
            primary, *fallbacks = chain
            self._models[tier] = primary.with_fallbacks(fallbacks) if fallbacks else primary
        return self._models[tier]

    def _config(self, tier: Tier, prompt: Prompt, trace_id: str | None) -> RunnableConfig:
        return RunnableConfig(
            callbacks=[self._callback],
            metadata={"tier": tier, "prompt": prompt.ref, "trace_id": trace_id},
            tags=[f"tier:{tier}", f"prompt:{prompt.ref}"],
        )

    def messages(
        self, tier: Tier, system: str, user: str, history: list[BaseMessage] | None = None
    ) -> list[BaseMessage]:
        return [cached_system(system, self.primary_provider(tier)), *(history or []), HumanMessage(content=user)]

    async def text(
        self, tier: Tier, prompt: Prompt, messages: list[BaseMessage], *, trace_id: str | None = None
    ) -> str:
        result = await self.runnable(tier).ainvoke(messages, config=self._config(tier, prompt, trace_id))
        return message_text(result)

    async def stream(
        self, tier: Tier, prompt: Prompt, messages: list[BaseMessage], *, trace_id: str | None = None
    ) -> AsyncIterator[str]:
        async for chunk in self.runnable(tier).astream(messages, config=self._config(tier, prompt, trace_id)):
            text = message_text(chunk)
            if text:
                yield text

    async def structured(
        self,
        tier: Tier,
        prompt: Prompt,
        schema: type[T],
        messages: list[BaseMessage],
        *,
        trace_id: str | None = None,
        attempts: int = 2,
    ) -> T:
        """JSON answer validated against ``schema``; on invalid JSON the error is fed back once.

        JSON-in-text works identically across providers and offline fixtures, which keeps recorded tests faithful.
        """
        instruction = "Reply with one JSON object only, no prose, matching this JSON Schema:\n" + json.dumps(
            schema.model_json_schema(), ensure_ascii=False
        )
        convo = [*messages, HumanMessage(content=instruction)]
        last_error = ""
        for _ in range(attempts):
            raw = await self.text(tier, prompt, convo, trace_id=trace_id)
            try:
                return schema.model_validate_json(_extract_json(raw))
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)[:800]
                convo = [*convo, HumanMessage(content=f"That was invalid: {last_error}\nReturn corrected JSON only.")]
        raise StructuredOutputError(f"{prompt.ref}: no valid {schema.__name__} after {attempts} attempts: {last_error}")


def _extract_json(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("{"):
        return stripped
    match = _JSON_BLOCK.search(stripped)
    if not match:
        raise ValueError("no JSON object in model output")
    return match.group(0)
