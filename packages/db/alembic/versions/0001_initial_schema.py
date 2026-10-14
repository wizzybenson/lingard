"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-14 02:55:07.724390
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "curriculum_edges",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("from_key", sa.String(length=160), nullable=False),
        sa.Column("to_key", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum_edges")),
        sa.UniqueConstraint("from_key", "to_key", "kind", name="uq_curriculum_edge"),
    )
    op.create_index(op.f("ix_curriculum_edges_from_key"), "curriculum_edges", ["from_key"], unique=False)
    op.create_index(op.f("ix_curriculum_edges_to_key"), "curriculum_edges", ["to_key"], unique=False)
    op.create_table(
        "curriculum_nodes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("band", sa.Integer(), nullable=False),
        sa.Column("skill", sa.String(length=16), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("as_of", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum_nodes")),
        sa.UniqueConstraint("key", name=op.f("uq_curriculum_nodes_key")),
    )
    op.create_index(op.f("ix_curriculum_nodes_band"), "curriculum_nodes", ["band"], unique=False)
    op.create_index(op.f("ix_curriculum_nodes_kind"), "curriculum_nodes", ["kind"], unique=False)
    op.create_index(op.f("ix_curriculum_nodes_language"), "curriculum_nodes", ["language"], unique=False)
    op.create_table(
        "draws",
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cutoff", sa.Integer(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draws")),
    )
    op.create_table(
        "memory_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("namespace", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("namespace_path", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_items")),
    )
    op.create_index(op.f("ix_memory_items_kind"), "memory_items", ["kind"], unique=False)
    op.create_index(op.f("ix_memory_items_namespace_path"), "memory_items", ["namespace_path"], unique=False)
    op.create_table(
        "npcs",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("city", sa.String(length=16), nullable=False),
        sa.Column("persona", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("voice_id", sa.String(length=64), nullable=False),
        sa.Column("schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_npcs")),
        sa.UniqueConstraint("key", name=op.f("uq_npcs_key")),
    )
    op.create_index(op.f("ix_npcs_city"), "npcs", ["city"], unique=False)
    op.create_table(
        "tenants",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("name", name=op.f("uq_tenants_name")),
    )
    op.create_table(
        "users",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("name_key", sa.String(length=64), nullable=False),
        sa.Column("pin_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("ui_locale", sa.String(length=8), nullable=False),
        sa.Column("failed_pin_attempts", sa.Integer(), nullable=False),
        sa.Column("lockout_level", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requires_admin_reset", sa.Boolean(), nullable=False),
        sa.Column("must_change_pin", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_users_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("tenant_id", "name_key", name="uq_users_tenant_name_key"),
    )
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)
    op.create_table(
        "audit_log",
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=200), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_log_actor_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_audit_log_tenant_id_tenants"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_table(
        "band_posteriors",
        sa.Column("pack", sa.String(length=16), nullable=False),
        sa.Column("skill", sa.String(length=16), nullable=False),
        sa.Column("mean", sa.Float(), nullable=False),
        sa.Column("variance", sa.Float(), nullable=False),
        sa.Column("observations", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_band_posteriors_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_band_posteriors_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_band_posteriors")),
        sa.UniqueConstraint("user_id", "pack", "skill", name="uq_band_posterior"),
    )
    op.create_index(op.f("ix_band_posteriors_tenant_id"), "band_posteriors", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_band_posteriors_user_id"), "band_posteriors", ["user_id"], unique=False)
    op.create_table(
        "device_sessions",
        sa.Column("device_label", sa.String(length=120), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=128), nullable=False),
        sa.Column("previous_refresh_hash", sa.String(length=128), nullable=True),
        sa.Column("pin_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_device_sessions_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_device_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_sessions")),
        sa.UniqueConstraint("refresh_token_hash", name=op.f("uq_device_sessions_refresh_token_hash")),
    )
    op.create_index(
        op.f("ix_device_sessions_previous_refresh_hash"), "device_sessions", ["previous_refresh_hash"], unique=False
    )
    op.create_index(op.f("ix_device_sessions_tenant_id"), "device_sessions", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_device_sessions_user_id"), "device_sessions", ["user_id"], unique=False)
    op.create_table(
        "fsrs_items",
        sa.Column("item_key", sa.String(length=200), nullable=False),
        sa.Column("card", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_fsrs_items_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_fsrs_items_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fsrs_items")),
        sa.UniqueConstraint("user_id", "item_key", name="uq_fsrs_user_item"),
    )
    op.create_index(op.f("ix_fsrs_items_due_at"), "fsrs_items", ["due_at"], unique=False)
    op.create_index(op.f("ix_fsrs_items_tenant_id"), "fsrs_items", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_fsrs_items_user_id"), "fsrs_items", ["user_id"], unique=False)
    op.create_table(
        "invites",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_by", sa.Uuid(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_invites_created_by_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_invites_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["used_by"], ["users.id"], name=op.f("fk_invites_used_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invites")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_invites_code_hash")),
    )
    op.create_index(op.f("ix_invites_tenant_id"), "invites", ["tenant_id"], unique=False)
    op.create_table(
        "learner_profiles",
        sa.Column("target_bands", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("crs_inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_accent", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("consents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("intensity_cap", sa.String(length=8), nullable=False),
        sa.Column("l1", sa.String(length=8), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_learner_profiles_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_learner_profiles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learner_profiles")),
        sa.UniqueConstraint("user_id", name="uq_learner_profiles_user"),
    )
    op.create_index(op.f("ix_learner_profiles_tenant_id"), "learner_profiles", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_learner_profiles_user_id"), "learner_profiles", ["user_id"], unique=False)
    op.create_table(
        "ledger",
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("ref_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_ledger_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_ledger_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_ledger_idempotency_key")),
    )
    op.create_index(op.f("ix_ledger_tenant_id"), "ledger", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ledger_user_id"), "ledger", ["user_id"], unique=False)
    op.create_table(
        "mastery",
        sa.Column("node_key", sa.String(length=160), nullable=False),
        sa.Column("p_mastery", sa.Float(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("contexts_count", sa.Integer(), nullable=False),
        sa.Column("contexts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_mastery_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_mastery_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mastery")),
        sa.UniqueConstraint("user_id", "node_key", name="uq_mastery_user_node"),
    )
    op.create_index(op.f("ix_mastery_node_key"), "mastery", ["node_key"], unique=False)
    op.create_index(op.f("ix_mastery_tenant_id"), "mastery", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_mastery_user_id"), "mastery", ["user_id"], unique=False)
    op.create_table(
        "mock_exams",
        sa.Column("pack", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("band_or_score", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("clb_nclc", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_mock_exams_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_mock_exams_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mock_exams")),
    )
    op.create_index(op.f("ix_mock_exams_tenant_id"), "mock_exams", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_mock_exams_user_id"), "mock_exams", ["user_id"], unique=False)
    op.create_table(
        "npc_relationships",
        sa.Column("npc_key", sa.String(length=64), nullable=False),
        sa.Column("affinity", sa.Float(), nullable=False),
        sa.Column("shared_history_summary", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_npc_relationships_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_npc_relationships_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_npc_relationships")),
        sa.UniqueConstraint("user_id", "npc_key", name="uq_npc_rel_user_npc"),
    )
    op.create_index(op.f("ix_npc_relationships_tenant_id"), "npc_relationships", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_npc_relationships_user_id"), "npc_relationships", ["user_id"], unique=False)
    op.create_table(
        "placements",
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("path", sa.String(length=8), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_placements_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_placements_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_placements")),
    )
    op.create_index(op.f("ix_placements_tenant_id"), "placements", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_placements_user_id"), "placements", ["user_id"], unique=False)
    op.create_table(
        "sessions",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("city", sa.String(length=16), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_sessions_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index(op.f("ix_sessions_tenant_id"), "sessions", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "sim_crs_snapshots",
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_sim_crs_snapshots_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sim_crs_snapshots_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sim_crs_snapshots")),
    )
    op.create_index(op.f("ix_sim_crs_snapshots_tenant_id"), "sim_crs_snapshots", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_sim_crs_snapshots_user_id"), "sim_crs_snapshots", ["user_id"], unique=False)
    op.create_table(
        "synthesis_cache",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("audio_ref", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_synthesis_cache_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_synthesis_cache")),
        sa.UniqueConstraint("key", name=op.f("uq_synthesis_cache_key")),
    )
    op.create_index(op.f("ix_synthesis_cache_user_id"), "synthesis_cache", ["user_id"], unique=False)
    op.create_table(
        "voice_profiles",
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("provider_profile_id", sa.String(length=255), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_voice_profiles_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_voice_profiles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_voice_profiles")),
    )
    op.create_index(op.f("ix_voice_profiles_tenant_id"), "voice_profiles", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_voice_profiles_user_id"), "voice_profiles", ["user_id"], unique=False)
    op.create_table(
        "wallet",
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.Column("stars_total", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_wallet_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_wallet_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wallet")),
        sa.UniqueConstraint("user_id", name="uq_wallet_user"),
    )
    op.create_index(op.f("ix_wallet_tenant_id"), "wallet", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_wallet_user_id"), "wallet", ["user_id"], unique=False)
    op.create_table(
        "weakness_tickets",
        sa.Column("node_key", sa.String(length=160), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reopen_count", sa.Integer(), nullable=False),
        sa.Column("examples", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("interventions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("success_contexts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_weakness_tickets_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_weakness_tickets_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weakness_tickets")),
    )
    op.create_index(op.f("ix_weakness_tickets_node_key"), "weakness_tickets", ["node_key"], unique=False)
    op.create_index(op.f("ix_weakness_tickets_status"), "weakness_tickets", ["status"], unique=False)
    op.create_index(op.f("ix_weakness_tickets_tenant_id"), "weakness_tickets", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_weakness_tickets_user_id"), "weakness_tickets", ["user_id"], unique=False)
    op.create_table(
        "world_state",
        sa.Column("city", sa.String(length=16), nullable=False),
        sa.Column("district_unlocks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("flat", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("job", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inventory", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("story_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_world_state_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_world_state_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_world_state")),
        sa.UniqueConstraint("user_id", "city", name="uq_world_state_user_city"),
    )
    op.create_index(op.f("ix_world_state_tenant_id"), "world_state", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_world_state_user_id"), "world_state", ["user_id"], unique=False)
    op.create_table(
        "scenes",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("contract", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("outcome", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f("fk_scenes_session_id_sessions"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_scenes_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_scenes_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenes")),
    )
    op.create_index(op.f("ix_scenes_session_id"), "scenes", ["session_id"], unique=False)
    op.create_index(op.f("ix_scenes_tenant_id"), "scenes", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_scenes_user_id"), "scenes", ["user_id"], unique=False)
    op.create_table(
        "writing_submissions",
        sa.Column("pack", sa.String(length=16), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rewrite", sa.Text(), nullable=True),
        sa.Column("mock_exam_id", sa.Uuid(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["mock_exam_id"],
            ["mock_exams.id"],
            name=op.f("fk_writing_submissions_mock_exam_id_mock_exams"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_writing_submissions_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_writing_submissions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_writing_submissions")),
    )
    op.create_index(op.f("ix_writing_submissions_tenant_id"), "writing_submissions", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_writing_submissions_user_id"), "writing_submissions", ["user_id"], unique=False)
    op.create_table(
        "lessons",
        sa.Column("node_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("homework_scene_id", sa.Uuid(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["homework_scene_id"], ["scenes.id"], name=op.f("fk_lessons_homework_scene_id_scenes"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_lessons_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_lessons_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lessons")),
    )
    op.create_index(op.f("ix_lessons_tenant_id"), "lessons", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_lessons_user_id"), "lessons", ["user_id"], unique=False)
    op.create_table(
        "turns",
        sa.Column("scene_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=16), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("audio_ref", sa.Text(), nullable=True),
        sa.Column("timings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], name=op.f("fk_turns_scene_id_scenes"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_turns_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_turns_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_turns")),
        sa.UniqueConstraint("event_id", name=op.f("uq_turns_event_id")),
        sa.UniqueConstraint("scene_id", "index", "speaker", name="uq_turns_scene_index_speaker"),
    )
    op.create_index(op.f("ix_turns_scene_id"), "turns", ["scene_id"], unique=False)
    op.create_index(op.f("ix_turns_tenant_id"), "turns", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_turns_user_id"), "turns", ["user_id"], unique=False)
    op.create_table(
        "assessments",
        sa.Column("turn_id", sa.Uuid(), nullable=True),
        sa.Column("submission_id", sa.Uuid(), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("pack", sa.String(length=16), nullable=False),
        sa.Column("dimension_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("band_estimate", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("error_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["writing_submissions.id"],
            name=op.f("fk_assessments_submission_id_writing_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_assessments_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"], ["turns.id"], name=op.f("fk_assessments_turn_id_turns"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_assessments_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
        sa.UniqueConstraint("event_id", name=op.f("uq_assessments_event_id")),
    )
    op.create_index(op.f("ix_assessments_submission_id"), "assessments", ["submission_id"], unique=False)
    op.create_index(op.f("ix_assessments_tenant_id"), "assessments", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_assessments_turn_id"), "assessments", ["turn_id"], unique=False)
    op.create_index(op.f("ix_assessments_user_id"), "assessments", ["user_id"], unique=False)
    op.create_table(
        "pron_scores",
        sa.Column("turn_id", sa.Uuid(), nullable=True),
        sa.Column("phoneme_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prosody", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("intelligibility", sa.Float(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_pron_scores_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"], ["turns.id"], name=op.f("fk_pron_scores_turn_id_turns"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_pron_scores_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pron_scores")),
    )
    op.create_index(op.f("ix_pron_scores_tenant_id"), "pron_scores", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_pron_scores_turn_id"), "pron_scores", ["turn_id"], unique=False)
    op.create_index(op.f("ix_pron_scores_user_id"), "pron_scores", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pron_scores_user_id"), table_name="pron_scores")
    op.drop_index(op.f("ix_pron_scores_turn_id"), table_name="pron_scores")
    op.drop_index(op.f("ix_pron_scores_tenant_id"), table_name="pron_scores")
    op.drop_table("pron_scores")
    op.drop_index(op.f("ix_assessments_user_id"), table_name="assessments")
    op.drop_index(op.f("ix_assessments_turn_id"), table_name="assessments")
    op.drop_index(op.f("ix_assessments_tenant_id"), table_name="assessments")
    op.drop_index(op.f("ix_assessments_submission_id"), table_name="assessments")
    op.drop_table("assessments")
    op.drop_index(op.f("ix_turns_user_id"), table_name="turns")
    op.drop_index(op.f("ix_turns_tenant_id"), table_name="turns")
    op.drop_index(op.f("ix_turns_scene_id"), table_name="turns")
    op.drop_table("turns")
    op.drop_index(op.f("ix_lessons_user_id"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_tenant_id"), table_name="lessons")
    op.drop_table("lessons")
    op.drop_index(op.f("ix_writing_submissions_user_id"), table_name="writing_submissions")
    op.drop_index(op.f("ix_writing_submissions_tenant_id"), table_name="writing_submissions")
    op.drop_table("writing_submissions")
    op.drop_index(op.f("ix_scenes_user_id"), table_name="scenes")
    op.drop_index(op.f("ix_scenes_tenant_id"), table_name="scenes")
    op.drop_index(op.f("ix_scenes_session_id"), table_name="scenes")
    op.drop_table("scenes")
    op.drop_index(op.f("ix_world_state_user_id"), table_name="world_state")
    op.drop_index(op.f("ix_world_state_tenant_id"), table_name="world_state")
    op.drop_table("world_state")
    op.drop_index(op.f("ix_weakness_tickets_user_id"), table_name="weakness_tickets")
    op.drop_index(op.f("ix_weakness_tickets_tenant_id"), table_name="weakness_tickets")
    op.drop_index(op.f("ix_weakness_tickets_status"), table_name="weakness_tickets")
    op.drop_index(op.f("ix_weakness_tickets_node_key"), table_name="weakness_tickets")
    op.drop_table("weakness_tickets")
    op.drop_index(op.f("ix_wallet_user_id"), table_name="wallet")
    op.drop_index(op.f("ix_wallet_tenant_id"), table_name="wallet")
    op.drop_table("wallet")
    op.drop_index(op.f("ix_voice_profiles_user_id"), table_name="voice_profiles")
    op.drop_index(op.f("ix_voice_profiles_tenant_id"), table_name="voice_profiles")
    op.drop_table("voice_profiles")
    op.drop_index(op.f("ix_synthesis_cache_user_id"), table_name="synthesis_cache")
    op.drop_table("synthesis_cache")
    op.drop_index(op.f("ix_sim_crs_snapshots_user_id"), table_name="sim_crs_snapshots")
    op.drop_index(op.f("ix_sim_crs_snapshots_tenant_id"), table_name="sim_crs_snapshots")
    op.drop_table("sim_crs_snapshots")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_tenant_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_placements_user_id"), table_name="placements")
    op.drop_index(op.f("ix_placements_tenant_id"), table_name="placements")
    op.drop_table("placements")
    op.drop_index(op.f("ix_npc_relationships_user_id"), table_name="npc_relationships")
    op.drop_index(op.f("ix_npc_relationships_tenant_id"), table_name="npc_relationships")
    op.drop_table("npc_relationships")
    op.drop_index(op.f("ix_mock_exams_user_id"), table_name="mock_exams")
    op.drop_index(op.f("ix_mock_exams_tenant_id"), table_name="mock_exams")
    op.drop_table("mock_exams")
    op.drop_index(op.f("ix_mastery_user_id"), table_name="mastery")
    op.drop_index(op.f("ix_mastery_tenant_id"), table_name="mastery")
    op.drop_index(op.f("ix_mastery_node_key"), table_name="mastery")
    op.drop_table("mastery")
    op.drop_index(op.f("ix_ledger_user_id"), table_name="ledger")
    op.drop_index(op.f("ix_ledger_tenant_id"), table_name="ledger")
    op.drop_table("ledger")
    op.drop_index(op.f("ix_learner_profiles_user_id"), table_name="learner_profiles")
    op.drop_index(op.f("ix_learner_profiles_tenant_id"), table_name="learner_profiles")
    op.drop_table("learner_profiles")
    op.drop_index(op.f("ix_invites_tenant_id"), table_name="invites")
    op.drop_table("invites")
    op.drop_index(op.f("ix_fsrs_items_user_id"), table_name="fsrs_items")
    op.drop_index(op.f("ix_fsrs_items_tenant_id"), table_name="fsrs_items")
    op.drop_index(op.f("ix_fsrs_items_due_at"), table_name="fsrs_items")
    op.drop_table("fsrs_items")
    op.drop_index(op.f("ix_device_sessions_user_id"), table_name="device_sessions")
    op.drop_index(op.f("ix_device_sessions_tenant_id"), table_name="device_sessions")
    op.drop_index(op.f("ix_device_sessions_previous_refresh_hash"), table_name="device_sessions")
    op.drop_table("device_sessions")
    op.drop_index(op.f("ix_band_posteriors_user_id"), table_name="band_posteriors")
    op.drop_index(op.f("ix_band_posteriors_tenant_id"), table_name="band_posteriors")
    op.drop_table("band_posteriors")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("tenants")
    op.drop_index(op.f("ix_npcs_city"), table_name="npcs")
    op.drop_table("npcs")
    op.drop_index(op.f("ix_memory_items_namespace_path"), table_name="memory_items")
    op.drop_index(op.f("ix_memory_items_kind"), table_name="memory_items")
    op.drop_table("memory_items")
    op.drop_table("draws")
    op.drop_index(op.f("ix_curriculum_nodes_language"), table_name="curriculum_nodes")
    op.drop_index(op.f("ix_curriculum_nodes_kind"), table_name="curriculum_nodes")
    op.drop_index(op.f("ix_curriculum_nodes_band"), table_name="curriculum_nodes")
    op.drop_table("curriculum_nodes")
    op.drop_index(op.f("ix_curriculum_edges_to_key"), table_name="curriculum_edges")
    op.drop_index(op.f("ix_curriculum_edges_from_key"), table_name="curriculum_edges")
    op.drop_table("curriculum_edges")
