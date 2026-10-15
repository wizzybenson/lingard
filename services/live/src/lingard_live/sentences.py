"""Incremental sentence splitting for streamed NPC tokens (each sentence is guarded, then synthesised)."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

_BOUNDARY = re.compile(r'([.!?…]+["»”)]?)(\s+)')
_COMPLETE = re.compile(r'[.!?…]+["»”)]?\s*$')


def is_complete(sentence: str) -> bool:
    """Ends the way a sentence ends (used to reject a truncated Guard repair)."""
    return bool(_COMPLETE.search(sentence))


class SentenceSplitter:
    def __init__(self, abbreviations: list[str], min_chars: int = 2) -> None:
        self._abbreviations = tuple(a.casefold() for a in abbreviations)
        self._min = min_chars
        self._buffer = ""

    def _is_abbreviation(self, text_before: str) -> bool:
        tail = text_before.rstrip().split(" ")[-1].casefold() if text_before.strip() else ""
        return tail in self._abbreviations

    def feed(self, chunk: str) -> list[str]:
        self._buffer += chunk
        out: list[str] = []
        start = 0
        for match in _BOUNDARY.finditer(self._buffer):
            end = match.end(1)
            candidate = self._buffer[start:end]
            if self._is_abbreviation(candidate):
                continue
            if len(candidate.strip()) >= self._min:
                out.append(candidate.strip())
                start = match.end()
        self._buffer = self._buffer[start:]
        return out

    def flush(self) -> list[str]:
        rest, self._buffer = self._buffer.strip(), ""
        return [rest] if rest else []


async def split_stream(tokens: AsyncIterator[str], splitter: SentenceSplitter) -> AsyncIterator[str]:
    async for token in tokens:
        for sentence in splitter.feed(token):
            yield sentence
    for sentence in splitter.flush():
        yield sentence
