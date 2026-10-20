"""ORM models for every SPEC §7 table. Curriculum and memory tables come from their packages."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_memory.sql import memory_table
from lingard_curriculum.sql import curriculum_tables
from lingard_db.base import Base, Owned, Timestamped

MEMORY_EMBEDDING_DIMS = 384
curriculum_nodes_table, curriculum_edges_table = curriculum_tables(Base.metadata)
memory_items_table = memory_table(Base.metadata, MEMORY_EMBEDDING_DIMS)

Json = dict[str, Any]


class Tenant(Timestamped, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(String(120), unique=True)


class User(Timestamped, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "name_key", name="uq_users_tenant_name_key"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    name_key: Mapped[str] = mapped_column(String(64))
    """NFKC-normalised, case-folded display name; uniqueness is enforced on this."""
    pin_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="learner")
    ui_locale: Mapped[str | None] = mapped_column(String(8), default=None)
    """The interface language the learner chose; None until they choose (the app then uses the device language)."""
    failed_pin_attempts: Mapped[int] = mapped_column(Integer, default=0)
    lockout_level: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requires_admin_reset: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_pin: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invite(Timestamped, Base):
    __tablename__ = "invites"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(128), unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16), default="learner")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceSession(Owned, Base):
    __tablename__ = "device_sessions"
    device_label: Mapped[str] = mapped_column(String(120))
    refresh_token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    previous_refresh_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    pin_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(64))


class LearnerProfile(Owned, Base):
    __tablename__ = "learner_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_learner_profiles_user"),)
    target_bands: Mapped[Json] = mapped_column(JSONB, default=dict)
    crs_inputs: Mapped[Json] = mapped_column(JSONB, default=dict)
    model_accent: Mapped[Json] = mapped_column(JSONB, default=dict)
    consents: Mapped[Json] = mapped_column(JSONB, default=dict)
    intensity_cap: Mapped[str] = mapped_column(String(8), default="tense")
    l1: Mapped[str] = mapped_column(String(8), default="ar")
    settings: Mapped[Json] = mapped_column(JSONB, default=dict)


class VoiceProfile(Owned, Base):
    __tablename__ = "voice_profiles"
    provider: Mapped[str] = mapped_column(String(16))
    provider_profile_id: Mapped[str] = mapped_column(String(255))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sample_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SynthesisCache(Timestamped, Base):
    __tablename__ = "synthesis_cache"
    key: Mapped[str] = mapped_column(String(128), unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    audio_ref: Mapped[str] = mapped_column(Text)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Mastery(Owned, Base):
    __tablename__ = "mastery"
    __table_args__ = (UniqueConstraint("user_id", "node_key", name="uq_mastery_user_node"),)
    node_key: Mapped[str] = mapped_column(String(160), index=True)
    p_mastery: Mapped[float] = mapped_column(Float, default=0.1)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    contexts_count: Mapped[int] = mapped_column(Integer, default=0)
    contexts: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error_times: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    last_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FsrsItem(Owned, Base):
    __tablename__ = "fsrs_items"
    __table_args__ = (UniqueConstraint("user_id", "item_key", name="uq_fsrs_user_item"),)
    item_key: Mapped[str] = mapped_column(String(200))
    card: Mapped[Json] = mapped_column(JSONB)
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)


class WeaknessTicket(Owned, Base):
    __tablename__ = "weakness_tickets"
    node_key: Mapped[str] = mapped_column(String(160), index=True)
    severity: Mapped[float] = mapped_column(Float, default=0.5)
    priority: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    examples: Mapped[list[Json]] = mapped_column(JSONB, default=list)
    interventions: Mapped[list[Json]] = mapped_column(JSONB, default=list)
    success_contexts: Mapped[list[Json]] = mapped_column(JSONB, default=list)


class WorldState(Owned, Base):
    __tablename__ = "world_state"
    __table_args__ = (UniqueConstraint("user_id", "city", name="uq_world_state_user_city"),)
    city: Mapped[str] = mapped_column(String(16))
    district_unlocks: Mapped[list[str]] = mapped_column(JSONB, default=list)
    flat: Mapped[Json] = mapped_column(JSONB, default=dict)
    job: Mapped[Json] = mapped_column(JSONB, default=dict)
    inventory: Mapped[list[Json]] = mapped_column(JSONB, default=list)
    story_flags: Mapped[Json] = mapped_column(JSONB, default=dict)


class Npc(Timestamped, Base):
    __tablename__ = "npcs"
    key: Mapped[str] = mapped_column(String(64), unique=True)
    city: Mapped[str] = mapped_column(String(16), index=True)
    persona: Mapped[Json] = mapped_column(JSONB)
    voice_id: Mapped[str] = mapped_column(String(64))
    schedule: Mapped[list[Json]] = mapped_column(JSONB)


class NpcRelationship(Owned, Base):
    __tablename__ = "npc_relationships"
    __table_args__ = (UniqueConstraint("user_id", "npc_key", name="uq_npc_rel_user_npc"),)
    npc_key: Mapped[str] = mapped_column(String(64))
    affinity: Mapped[float] = mapped_column(Float, default=0.0)
    shared_history_summary: Mapped[str] = mapped_column(Text, default="")


class Session(Owned, Base):
    __tablename__ = "sessions"
    kind: Mapped[str] = mapped_column(String(16))
    city: Mapped[str | None] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)
    plan: Mapped[Json] = mapped_column(JSONB, default=dict)


class Scene(Owned, Base):
    __tablename__ = "scenes"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    contract: Mapped[Json] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="planned")
    outcome: Mapped[Json] = mapped_column(JSONB, default=dict)
    trace_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)


class Turn(Owned, Base):
    __tablename__ = "turns"
    __table_args__ = (UniqueConstraint("scene_id", "index", "speaker", name="uq_turns_scene_index_speaker"),)
    scene_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    index: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(16))
    transcript: Mapped[str] = mapped_column(Text)
    audio_ref: Mapped[str | None] = mapped_column(Text)
    timings: Mapped[Json] = mapped_column(JSONB, default=dict)


class Assessment(Owned, Base):
    __tablename__ = "assessments"
    turn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("turns.id", ondelete="CASCADE"), index=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("writing_submissions.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    pack: Mapped[str] = mapped_column(String(16))
    dimension_scores: Mapped[list[Json]] = mapped_column(JSONB)
    band_estimate: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    error_tags: Mapped[list[Json]] = mapped_column(JSONB, default=list)
    model_versions: Mapped[Json] = mapped_column(JSONB, default=dict)


class PronScore(Owned, Base):
    __tablename__ = "pron_scores"
    turn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("turns.id", ondelete="CASCADE"), index=True)
    phoneme_scores: Mapped[list[Json]] = mapped_column(JSONB)
    prosody: Mapped[Json] = mapped_column(JSONB)
    intelligibility: Mapped[float] = mapped_column(Float)


class WritingSubmission(Owned, Base):
    __tablename__ = "writing_submissions"
    pack: Mapped[str] = mapped_column(String(16))
    task_type: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    scores: Mapped[Json] = mapped_column(JSONB, default=dict)
    rewrite: Mapped[str | None] = mapped_column(Text)
    mock_exam_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mock_exams.id", ondelete="SET NULL"))


class MockExam(Owned, Base):
    __tablename__ = "mock_exams"
    pack: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    sections: Mapped[list[Json]] = mapped_column(JSONB, default=list)
    raw_scores: Mapped[Json] = mapped_column(JSONB, default=dict)
    band_or_score: Mapped[Json] = mapped_column(JSONB, default=dict)
    clb_nclc: Mapped[Json] = mapped_column(JSONB, default=dict)


class Placement(Owned, Base):
    __tablename__ = "placements"
    language: Mapped[str] = mapped_column(String(2))
    path: Mapped[str] = mapped_column(String(8))
    result: Mapped[Json] = mapped_column(JSONB, default=dict)


class Lesson(Owned, Base):
    __tablename__ = "lessons"
    node_key: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), default="planned")
    content: Mapped[Json] = mapped_column(JSONB, default=dict)
    homework_scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id", ondelete="SET NULL"))


class BandPosterior(Owned, Base):
    __tablename__ = "band_posteriors"
    __table_args__ = (UniqueConstraint("user_id", "pack", "skill", name="uq_band_posterior"),)
    pack: Mapped[str] = mapped_column(String(16))
    skill: Mapped[str] = mapped_column(String(16))
    mean: Mapped[float] = mapped_column(Float)
    variance: Mapped[float] = mapped_column(Float)
    observations: Mapped[int] = mapped_column(Integer, default=0)


class Wallet(Owned, Base):
    __tablename__ = "wallet"
    __table_args__ = (UniqueConstraint("user_id", name="uq_wallet_user"),)
    coins: Mapped[int] = mapped_column(Integer, default=0)
    stars_total: Mapped[int] = mapped_column(Integer, default=0)


class Ledger(Owned, Base):
    """Append-only: the repository exposes no update or delete for this table."""

    __tablename__ = "ledger"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_ledger_user_id_idempotency_key"),)
    currency: Mapped[str] = mapped_column(String(16))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(64))
    ref_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(160))


class SimCrsSnapshot(Owned, Base):
    __tablename__ = "sim_crs_snapshots"
    value: Mapped[int] = mapped_column(Integer)
    breakdown: Mapped[Json] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Draw(Timestamped, Base):
    __tablename__ = "draws"
    held_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cutoff: Mapped[int] = mapped_column(Integer)
    source_note: Mapped[str] = mapped_column(Text)


class AuditLog(Timestamped, Base):
    __tablename__ = "audit_log"
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[Json] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
