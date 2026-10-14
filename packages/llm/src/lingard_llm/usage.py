"""Usage and cost capture for every LLM call (SPEC §21, §22).

Pattern adapted from simupatient@69e1bd5:backend/app/services/usage_service.py (rate card, off-path projection).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from lingard_llm.config import Price


@dataclass(frozen=True)
class UsageRecord:
    prompt: str
    tier: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float
    latency_ms: int
    trace_id: str | None = None


class UsageSink(Protocol):
    def record(self, usage: UsageRecord) -> None: ...


@dataclass
class MemoryUsageSink:
    records: list[UsageRecord] = field(default_factory=list)

    def record(self, usage: UsageRecord) -> None:
        self.records.append(usage)

    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self.records)


def cost_usd(price: Price | None, input_tokens: int, output_tokens: int, cache_read_tokens: int) -> float:
    if price is None:
        return 0.0
    uncached = max(input_tokens - cache_read_tokens, 0)
    return (uncached * price.input + cache_read_tokens * price.cache_read + output_tokens * price.output) / 1_000_000


@dataclass
class _Pending:
    started: float
    metadata: dict[str, Any]


class UsageCallback(AsyncCallbackHandler):
    """Collects token usage per chat-model run and forwards priced records to a sink."""

    def __init__(self, sink: UsageSink, prices: dict[str, Price | None]) -> None:
        self._sink = sink
        self._prices = prices
        self._pending: dict[UUID, _Pending] = {}

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._pending[run_id] = _Pending(started=time.perf_counter(), metadata=dict(metadata or {}))

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        pending = self._pending.pop(run_id, None)
        if pending is None:
            return
        model, usage = _usage_from(response.generations)
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        details = usage.get("input_token_details") or {}
        cache_read = int(details.get("cache_read", 0)) if isinstance(details, dict) else 0
        model = model or str(pending.metadata.get("ls_model_name", "unknown"))
        self._sink.record(
            UsageRecord(
                prompt=str(pending.metadata.get("prompt", "unversioned")),
                tier=str(pending.metadata.get("tier", "unknown")),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read,
                cost_usd=cost_usd(self._prices.get(model), input_tokens, output_tokens, cache_read),
                latency_ms=int((time.perf_counter() - pending.started) * 1000),
                trace_id=pending.metadata.get("trace_id"),
            )
        )

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._pending.pop(run_id, None)


def _usage_from(generations: Sequence[Sequence[Any]]) -> tuple[str | None, dict[str, Any]]:
    for batch in generations:
        for generation in batch:
            if isinstance(generation, ChatGeneration):
                message = generation.message
                usage = getattr(message, "usage_metadata", None) or {}
                model = message.response_metadata.get("model_name") or message.response_metadata.get("model")
                return (str(model) if model else None), dict(usage)
    return None, {}
