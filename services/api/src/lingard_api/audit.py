"""Append-only audit log (SPEC §23.2). Pattern lifted from simupatient@69e1bd5:backend/app/services/audit_service.py."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lingard_db.models import AuditLog


def record(
    db: AsyncSession,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    target: str | None = None,
    ip: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    """Stage an audit row in the caller's transaction. ``detail`` must never contain PINs or tokens."""
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        tenant_id=tenant_id,
        target=target,
        ip=ip,
        detail=detail or {},
        at=datetime.now(UTC),
    )
    db.add(entry)
    return entry
