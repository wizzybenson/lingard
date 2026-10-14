"""Voice-clone deletion cascade, account deletion, data export and audio retention (SPEC §23.1)."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, inspect, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_memory import MemoryStore
from lingard_api import audit
from lingard_db.base import Base
from lingard_db.models import AuditLog, DeviceSession, LearnerProfile, SynthesisCache, User, VoiceProfile
from lingard_pronunciation.clone import VoiceCloneProvider
from lingard_storage import AUDIO_BUCKET, ObjectStore, user_prefix


class CascadeError(RuntimeError):
    """A step of a deletion cascade could not be verified; nothing is reported as deleted."""


async def delete_voice_clone(
    db: AsyncSession, user_id: uuid.UUID, providers: dict[str, VoiceCloneProvider], objects: ObjectStore
) -> int:
    """Delete every clone at its provider, the samples and renders in storage, and the cache rows; then verify."""
    profiles = (
        (
            await db.execute(
                select(VoiceProfile).where(VoiceProfile.user_id == user_id, VoiceProfile.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    for profile in profiles:
        provider = providers.get(profile.provider)
        if provider is None:
            raise CascadeError(f"provider {profile.provider} is not configured; cannot delete clone")
        await provider.delete(profile.provider_profile_id)
        if await provider.exists(profile.provider_profile_id):
            raise CascadeError(f"{profile.provider} still reports clone {profile.provider_profile_id}")
        profile.deleted_at, profile.status = datetime.now(UTC), "deleted"
    await objects.delete_prefix(AUDIO_BUCKET, f"{user_prefix(str(user_id))}voice/")
    await objects.delete_prefix(AUDIO_BUCKET, f"{user_prefix(str(user_id))}golden/")
    if await objects.list_keys(AUDIO_BUCKET, f"{user_prefix(str(user_id))}voice/"):
        raise CascadeError("voice samples still present in storage")
    await db.execute(delete(SynthesisCache).where(SynthesisCache.user_id == user_id))
    audit.record(db, "voice_clone_deleted", actor_id=user_id, detail={"profiles": len(profiles)})
    return len(profiles)


def _row(obj: Any) -> dict[str, Any]:
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


async def export_zip(db: AsyncSession, user_id: uuid.UUID, objects: ObjectStore) -> bytes:
    """Everything the learner owns: one JSON file per table plus their audio. Voice clone models are not exportable."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        user = await db.get_one(User, user_id)
        archive.writestr(
            "account.json",
            json.dumps(
                {k: v for k, v in _row(user).items() if k not in ("pin_hash", "name_key")}, default=str, indent=1
            ),
        )
        for mapper in Base.registry.mappers:
            model = mapper.class_
            if "user_id" not in mapper.columns or model in (DeviceSession,):
                continue
            rows = (await db.execute(select(model).where(mapper.columns["user_id"] == user_id))).scalars().all()
            if rows:
                payload = [{k: v for k, v in _row(r).items() if k != "provider_profile_id"} for r in rows]
                table = model.__tablename__
                archive.writestr(f"data/{table}.json", json.dumps(payload, default=str, indent=1))
        prefix = user_prefix(str(user_id))
        for key in await objects.list_keys(AUDIO_BUCKET, prefix):
            if "/voice/" in key:
                continue  # clone samples stay private to the clone pipeline; the learner's turns are exported
            archive.writestr(f"audio/{key.removeprefix(prefix)}", await objects.get(AUDIO_BUCKET, key))
    return buffer.getvalue()


async def delete_account(
    db: AsyncSession,
    user_id: uuid.UUID,
    providers: dict[str, VoiceCloneProvider],
    objects: ObjectStore,
    memory: MemoryStore,
) -> None:
    """Full deletion. Order matters: external copies first (verifiable), then the database rows (FK cascade)."""
    await delete_voice_clone(db, user_id, providers, objects)
    await objects.delete_prefix(AUDIO_BUCKET, user_prefix(str(user_id)))
    if await objects.list_keys(AUDIO_BUCKET, user_prefix(str(user_id))):
        raise CascadeError("learner audio still present in storage")
    await memory.delete_namespace(("user", str(user_id)))
    user = await db.get_one(User, user_id)
    tenant_id, pseudonym = user.tenant_id, hashlib.sha256(str(user_id).encode()).hexdigest()[:16]
    # Keep the security trail but pseudonymise it: no id, name or IP of the erased learner survives.
    await db.execute(
        update(AuditLog)
        .where(or_(AuditLog.target.in_([str(user_id), user.name_key]), AuditLog.actor_id == user_id))
        .values(target=pseudonym, ip=None)
    )
    await db.delete(user)
    audit.record(db, "account_deleted", tenant_id=tenant_id, target=pseudonym)


async def apply_retention(
    db: AsyncSession, objects: ObjectStore, retention_days: int, now: datetime | None = None
) -> int:
    """Delete raw turn audio older than the retention window unless the learner opted in to keep it."""
    moment = now or datetime.now(UTC)
    removed = 0
    profiles = (await db.execute(select(LearnerProfile))).scalars().all()
    for profile in profiles:
        if (profile.consents or {}).get("audio_retention_extended"):
            continue
        prefix = f"{user_prefix(str(profile.user_id))}turns/"
        for key in await objects.list_keys(AUDIO_BUCKET, prefix):
            day = key.removeprefix(prefix).split("/")[0]
            try:
                stamp = datetime.fromisoformat(day).replace(tzinfo=UTC)
            except ValueError:
                continue
            if moment - stamp > timedelta(days=retention_days):
                removed += await objects.delete_prefix(AUDIO_BUCKET, key)
    return removed
