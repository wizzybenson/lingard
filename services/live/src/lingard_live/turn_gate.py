# Lifted from simupatient@69e1bd5:backend/app/realtime/policy.py
"""Transcript quality gate: rejects empty, garbled, echoed or implausible turns before the actor sees them.

Adapted: thresholds are an explicit ``GatePolicy`` instead of global settings, and echo candidates are plain strings.
The low-entropy check counts distinct characters instead of their share of the text, which dropped long fluent turns.
Language-agnostic by design (no hard-coded phrases).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

TurnStatus = Literal["accepted", "needs_confirmation", "ignored"]


@dataclass(frozen=True)
class GatePolicy:
    min_transcript_chars: int = 3
    min_confidence: float = 0.65
    hard_reject_confidence: float = 0.45
    min_speech_ms: int = 300
    speech_ms_per_word: int = 180
    echo_similarity: float = 0.82


@dataclass(frozen=True)
class EchoCheck:
    checked: bool
    matched: bool
    similarity: float | None = None


@dataclass(frozen=True)
class TurnDecision:
    status: TurnStatus
    reason: str
    echo: EchoCheck
    normalized_text: str


def normalize_transcript(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def normalize_semantic_text(text: str) -> str:
    return re.sub(r"[^\w\s]", "", normalize_transcript(text), flags=re.UNICODE).strip()


def is_low_entropy(text: str) -> bool:
    tokens = re.findall(r"\b[\w']+\b", text, flags=re.UNICODE)
    if len(tokens) >= 3 and Counter(tokens).most_common(1)[0][1] / len(tokens) > 0.6:
        return True
    compact = re.sub(r"\s+", "", text)
    if len(compact) >= 8:
        # An absolute count, not a share of the length: any long sentence reuses a ~30-letter alphabet, so a ratio
        # threshold rejected every fluent turn over ~130 characters. "hahaha" has two distinct characters.
        if len(set(compact)) <= 3:
            return True
        counts = Counter(compact).values()
        entropy = -sum((c / len(compact)) * math.log2(c / len(compact)) for c in counts)
        if entropy < 1.0:
            return True
    return False


def echo_similarity(text: str, recent_npc_lines: list[str], threshold: float) -> EchoCheck:
    if not text:
        return EchoCheck(checked=False, matched=False)
    best = 0.0
    for line in recent_npc_lines:
        candidate = normalize_semantic_text(line)
        if candidate:
            best = max(best, SequenceMatcher(None, text, candidate).ratio())
    return EchoCheck(checked=True, matched=best >= threshold, similarity=round(best, 3))


def duration_reason(text: str, speech_ms: int | None, policy: GatePolicy) -> str | None:
    if speech_ms is None:
        return None
    word_count = len(re.findall(r"\b[\w']+\b", text, flags=re.UNICODE))
    required = max(policy.min_speech_ms, word_count * policy.speech_ms_per_word)
    if speech_ms < policy.min_speech_ms:
        return "too_short_audio"
    if speech_ms < required * 0.6:
        return "implausible_speech_duration"
    if speech_ms < required:
        return "speech_duration_mismatch"
    return None


def validate_turn(
    text: str,
    *,
    confidence: float | None,
    speech_ms: int | None,
    recent_npc_lines: list[str],
    policy: GatePolicy | None = None,
) -> TurnDecision:
    rules = policy or GatePolicy()
    normalized = normalize_transcript(text)
    semantic = normalize_semantic_text(text)
    echo = echo_similarity(semantic, recent_npc_lines, rules.echo_similarity)

    if not semantic:
        return TurnDecision("ignored", "empty", echo, normalized)
    if len(semantic) < rules.min_transcript_chars:
        return TurnDecision("ignored", "too_short", echo, normalized)
    if is_low_entropy(semantic):
        return TurnDecision("ignored", "low_entropy", echo, normalized)
    if echo.matched:
        return TurnDecision("ignored", "echo_similarity", echo, normalized)
    if confidence is not None and confidence < rules.hard_reject_confidence:
        return TurnDecision("ignored", "very_low_confidence", echo, normalized)
    reason = duration_reason(semantic, speech_ms, rules)
    if reason in {"too_short_audio", "implausible_speech_duration"}:
        return TurnDecision("ignored", reason or "", echo, normalized)
    if reason or (confidence is not None and confidence < rules.min_confidence):
        return TurnDecision("needs_confirmation", reason or "low_confidence", echo, normalized)
    return TurnDecision("accepted", "quality_passed", echo, normalized)
