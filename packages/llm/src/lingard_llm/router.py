"""LangChain LLM router with fast/mid/frontier tiers, retries, fallbacks, prompt caching and usage capture.

Core adapted from simupatient@69e1bd5:backend/app/agents/providers.py (``LangChainChatProvider``: ``init_chat_model``
construction, structured output, usage capture). Tiers, fallback chains, prompt caching and versioned prompts are new.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ValidationError

from lingard_llm.config import PROVIDER_ENV, LLMConfig, ModelSpec, Tier, provider_configured
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
        if not spec.thinking:
            kwargs["thinking"] = {"type": "disabled"}  # Haiku 5.5 accepts this at effort high or below
        return ChatAnthropic(**kwargs)
    if spec.provider == "openai":
        from langchain_openai import ChatOpenAI

        effort = {"xhigh": "high", "max": "high"}.get(spec.effort or "", spec.effort)
        return ChatOpenAI(
            model=spec.model,
            max_completion_tokens=spec.max_tokens,
            timeout=spec.timeout_s,
            max_retries=0,
            reasoning_effort=effort,
        )
    if spec.provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=spec.model, max_output_tokens=spec.max_tokens, timeout=spec.timeout_s, max_retries=0
        )
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
        available: Callable[[str], bool] | None = None,
    ) -> None:
        """``available`` decides which providers may be used; by default a hosted provider is used only when its API
        key is set (``PROVIDER_ENV``), so each tier falls through to whichever configured provider comes first.
        Custom factories (tests, recorded fixtures) default to every provider being available."""
        self.config = config
        self._available = available or (provider_configured if factory is default_factory else lambda _: True)
        self.sink: UsageSink = sink or MemoryUsageSink()
        self._factory = factory
        self._models: dict[Tier, Runnable[Any, BaseMessage]] = {}
        self._chains: dict[Tier, list[Runnable[Any, BaseMessage]]] = {}
        prices = {spec.model: spec.price for tier in config.tiers.values() for spec in tier.models}
        self._callback = UsageCallback(self.sink, prices)

    def specs(self, tier: Tier) -> list[ModelSpec]:
        """The tier's models whose provider is available, in fallback order."""
        specs = [spec for spec in self.config.tier(tier).models if self._available(spec.provider)]
        if not specs:
            keys = sorted({PROVIDER_ENV.get(s.provider, s.provider) for s in self.config.tier(tier).models})
            raise RuntimeError(f"no {tier} model available: set one of {', '.join(keys)}")
        return specs

    def primary_provider(self, tier: Tier) -> str:
        return self.specs(tier)[0].provider

    def _attempts(self, tier: Tier) -> list[Runnable[Any, BaseMessage]]:
        """One runnable per available model, each with the tier's retries."""
        if tier not in self._chains:
            retries = self.config.tier(tier).retries
            chain: list[Runnable[Any, BaseMessage]] = []
            for spec in self.specs(tier):
                model: Runnable[Any, BaseMessage] = self._factory(spec)
                if retries:
                    model = model.with_retry(stop_after_attempt=retries + 1, wait_exponential_jitter=True)
                chain.append(model)
            self._chains[tier] = chain
        return self._chains[tier]

    def runnable(self, tier: Tier) -> Runnable[Any, BaseMessage]:
        if tier not in self._models:
            primary, *fallbacks = self._attempts(tier)
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
        config = self._config(tier, prompt, trace_id)
        if self.config.tier(tier).hedge_s is None:
            return message_text(await self.runnable(tier).ainvoke(messages, config=config))

        def asker(model: Runnable[Any, BaseMessage]) -> Callable[[], Awaitable[str]]:
            async def ask() -> str:
                return message_text(await model.ainvoke(messages, config=config))

            return ask

        text, _ = await self._race(tier, [asker(m) for m in self._attempts(tier)])
        return text

    async def stream(
        self, tier: Tier, prompt: Prompt, messages: list[BaseMessage], *, trace_id: str | None = None
    ) -> AsyncIterator[str]:
        config = self._config(tier, prompt, trace_id)
        if self.config.tier(tier).hedge_s is None:
            async for chunk in self.runnable(tier).astream(messages, config=config):
                if text := message_text(chunk):
                    yield text
            return
        streams: list[AsyncIterator[BaseMessage]] = []

        def opener(model: Runnable[Any, BaseMessage]) -> Callable[[], Awaitable[str]]:
            def start() -> Awaitable[str]:
                stream = aiter(model.astream(messages, config=config))
                streams.append(stream)
                return _first_text(stream)

            return start

        first, index = await self._race(tier, [opener(m) for m in self._attempts(tier)])
        winner = streams[index]
        for stream in streams:
            if stream is not winner:
                with contextlib.suppress(Exception):
                    await stream.aclose()  # type: ignore[attr-defined]
        yield first
        async for chunk in winner:
            if text := message_text(chunk):
                yield text

    async def _race(self, tier: Tier, attempts: list[Callable[[], Awaitable[str]]]) -> tuple[str, int]:
        """Starts the first attempt, and the next whenever every running one has gone ``hedge_s`` without answering
        or has failed. Returns the first answer and its attempt's index; raises the last error if all fail."""
        hedge_s = self.config.tier(tier).hedge_s
        running: dict[asyncio.Task[str], int] = {}
        launched = 0
        error: BaseException | None = None

        def launch() -> None:
            nonlocal launched
            running[asyncio.ensure_future(attempts[launched]())] = launched
            launched += 1

        launch()
        try:
            while running:
                more = launched < len(attempts)
                done, _ = await asyncio.wait(
                    running, timeout=hedge_s if more else None, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    index = running.pop(task)
                    if task.exception() is None:
                        return task.result(), index
                    error = task.exception()
                if more:  # every finished attempt failed, or none answered in time
                    launch()
            raise error if error else RuntimeError(f"no {tier} model answered")
        finally:
            for task in running:
                task.cancel()
            await asyncio.gather(*running, return_exceptions=True)

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


async def _first_text(stream: AsyncIterator[BaseMessage]) -> str:
    """The stream's first non-empty text; an answer with no text at all counts as a failure."""
    async for chunk in stream:
        if text := message_text(chunk):
            return text
    raise RuntimeError("the model answered with no text")


def _extract_json(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("{"):
        return stripped
    match = _JSON_BLOCK.search(stripped)
    if not match:
        raise ValueError("no JSON object in model output")
    return match.group(0)
