"""Turn event published on the Redis Stream ``turns`` (SPEC §5.3)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from lingard_contracts.common import Locale, NodeKey, Strict

TURNS_STREAM = "turns"


class TurnTimings(Strict):
    speech_start: int = Field(ge=0)
    speech_end: int = Field(ge=0)
    eot_decided: int = Field(ge=0)


class NpcContext(Strict):
    npc_id: str
    last_npc_line: str = ""


class TurnEvent(Strict):
    """One learner (or NPC) turn. Consumers must be idempotent on ``event_id``."""

    event_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    user_id: UUID
    session_id: UUID
    scene_id: UUID
    turn_index: int = Field(ge=0)
    speaker: Literal["learner", "npc"]
    language: Locale
    transcript: str
    stt_confidence: float | None = Field(default=None, ge=0, le=1)
    audio_ref: str | None = None
    timings_ms: TurnTimings | None = None
    pauses_ms: list[int] = Field(default_factory=list)
    npc_context: NpcContext | None = None
    targets_active: list[NodeKey] = Field(default_factory=list)
    interrupted_npc: bool = False

    def stream_fields(self) -> dict[str, str]:
        """Flat mapping for ``XADD``; the full event travels as one JSON field."""
        return {"event_id": str(self.event_id), "json": self.model_dump_json()}

    @classmethod
    def from_stream_fields(cls, fields: dict[str, str]) -> TurnEvent:
        """Parse an entry read with ``decode_responses=True``."""
        raw = fields.get("json")
        if raw is None:
            raise ValueError("stream entry has no 'json' field")
        return cls.model_validate_json(raw)
