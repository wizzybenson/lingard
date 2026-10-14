"""Offline chat models: scripted responders for unit tests, recorded fixtures (VCR-style) for graph tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import ConfigDict, Field

Responder = Callable[[list[BaseMessage]], str]


def message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _usage(messages: list[BaseMessage], text: str) -> UsageMetadata:
    prompt_tokens = sum(len(message_text(m)) for m in messages) // 4 + 1
    output_tokens = len(text) // 4 + 1
    return UsageMetadata(
        input_tokens=prompt_tokens, output_tokens=output_tokens, total_tokens=prompt_tokens + output_tokens
    )


class ScriptedChatModel(BaseChatModel):
    """Answers with ``responder(messages)``, or pops ``queue`` in order. Streams word by word."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    responder: Responder | None = None
    queue: list[str] = Field(default_factory=list)
    model_name: str = "scripted"
    fail_times: int = 0
    first_token_delay_s: float = 0.0
    token_delay_s: float = 0.0
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _answer(self, messages: list[BaseMessage]) -> str:
        self.calls.append(messages)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("scripted failure")
        if self.responder is not None:
            return self.responder(messages)
        if not self.queue:
            raise RuntimeError("ScriptedChatModel queue is empty")
        return self.queue.pop(0)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = self._answer(messages)
        message = AIMessage(
            content=text, usage_metadata=_usage(messages, text), response_metadata={"model_name": self.model_name}
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        text = self._answer(messages)
        words = text.split(" ")
        for i, word in enumerate(words):
            piece = word if i == len(words) - 1 else word + " "
            last = i == len(words) - 1
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=piece,
                    usage_metadata=_usage(messages, text) if last else None,
                    response_metadata={"model_name": self.model_name} if last else {},
                )
            )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        import asyncio

        if self.first_token_delay_s:
            await asyncio.sleep(self.first_token_delay_s)
        for i, chunk in enumerate(self._stream(messages, stop, None, **kwargs)):
            if i and self.token_delay_s:
                await asyncio.sleep(self.token_delay_s)
            yield chunk


class MissingFixtureError(LookupError):
    pass


def fixture_key(messages: list[BaseMessage]) -> str:
    payload = json.dumps([[m.type, message_text(m)] for m in messages], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


class RecordedChatModel(BaseChatModel):
    """Replays responses stored as ``<fixtures_dir>/<key>.json``.

    With ``inner`` set and ``record=True`` it calls the real model on a miss and stores the answer, so integration tests
    can be re-recorded against a live provider and then run offline in CI.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    fixtures_dir: Path
    inner: BaseChatModel | None = None
    record: bool = False
    model_name: str = "recorded"

    @property
    def _llm_type(self) -> str:
        return "recorded"

    def _path(self, messages: list[BaseMessage]) -> Path:
        return self.fixtures_dir / f"{fixture_key(messages)}.json"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        path = self._path(messages)
        if path.is_file():
            text = json.loads(path.read_text())["response"]
        elif self.record and self.inner is not None:
            text = message_text(self.inner.invoke(messages))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"messages": [message_text(m) for m in messages], "response": text}, indent=1))
        else:
            raise MissingFixtureError(f"no recorded LLM response {path}; re-record with LINGARD_LLM_RECORD=1")
        message = AIMessage(
            content=text, usage_metadata=_usage(messages, text), response_metadata={"model_name": self.model_name}
        )
        return ChatResult(generations=[ChatGeneration(message=message)])
