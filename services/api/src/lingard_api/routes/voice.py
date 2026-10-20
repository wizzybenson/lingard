"""``/v1/voice``: explicit-consent voice clone enrolment and verified deletion; ``/v1/me`` export and deletion."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from lingard_api import audit
from lingard_api.deps import Db, Principal, State
from lingard_api.privacy import CascadeError, delete_account, delete_voice_clone, export_zip
from lingard_db.models import LearnerProfile, VoiceProfile
from lingard_pronunciation.audio import wav_to_pcm
from lingard_pronunciation.clone import CloneError, create_with_fallback
from lingard_storage import AUDIO_BUCKET, user_prefix

router = APIRouter(prefix="/v1", tags=["voice", "privacy"])
MIN_SAMPLE_S, MAX_SAMPLE_S = 20, 120


class VoiceView(BaseModel):
    status: str
    provider: str | None = None
    consent_at: str | None = None


class DeleteAccountBody(BaseModel):
    pin: str


@router.get("/voice", response_model=VoiceView)
async def voice_status(principal: Principal, db: Db) -> VoiceView:
    row = (
        await db.execute(
            select(VoiceProfile).where(VoiceProfile.user_id == principal.user_id, VoiceProfile.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if row is None:
        return VoiceView(status="none")
    return VoiceView(status=row.status, provider=row.provider, consent_at=row.consent_at.isoformat())


@router.post("/voice/clone", response_model=VoiceView, status_code=201)
async def create_clone(
    principal: Principal,
    state: State,
    db: Db,
    sample: Annotated[UploadFile, File()],
    consent: Annotated[bool, Form()] = False,
) -> VoiceView:
    """Clone from a 20–120 s 16-bit WAV. Requires explicit consent in this request and in the profile settings."""
    profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == principal.user_id))).scalar_one()
    if not consent or not (profile.consents or {}).get("voice_clone"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Voice cloning needs your explicit consent")
    existing = (
        await db.execute(
            select(VoiceProfile).where(VoiceProfile.user_id == principal.user_id, VoiceProfile.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if existing is not None:
        return VoiceView(status=existing.status, provider=existing.provider, consent_at=existing.consent_at.isoformat())
    pcm, rate = wav_to_pcm(await sample.read())
    seconds = len(pcm) / 2 / rate
    if not MIN_SAMPLE_S <= seconds <= MAX_SAMPLE_S:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"sample must be {MIN_SAMPLE_S}–{MAX_SAMPLE_S} s")
    order = [state.clone_providers[n] for n in ("voicebox", "elevenlabs") if n in state.clone_providers]
    if not order:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No voice clone provider is configured")
    user_ref = uuid.uuid5(uuid.NAMESPACE_URL, str(principal.user_id)).hex[:12]
    try:
        provider_name, profile_id = await create_with_fallback(
            order[0], order[1] if len(order) > 1 else None, user_ref, pcm
        )
    except CloneError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Voice clone provider failed: {exc}") from exc
    sample_ref = await state.objects.put(AUDIO_BUCKET, f"{user_prefix(str(principal.user_id))}voice/sample.pcm", pcm)
    row = VoiceProfile(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        provider=provider_name,
        provider_profile_id=profile_id,
        consent_at=datetime.now(UTC),
        sample_ref=sample_ref,
    )
    db.add(row)
    audit.record(db, "voice_clone_created", actor_id=principal.user_id, detail={"provider": provider_name})
    await db.commit()
    return VoiceView(status=row.status, provider=provider_name, consent_at=row.consent_at.isoformat())


@router.delete("/voice/clone", status_code=204)
async def remove_clone(principal: Principal, state: State, db: Db) -> None:
    try:
        await delete_voice_clone(db, principal.user_id, state.clone_providers, state.objects)
    except CascadeError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Deletion not verified: {exc}") from exc
    await db.commit()


@router.get("/me/export")
async def export(principal: Principal, state: State, db: Db) -> Response:
    data = await export_zip(db, principal.user_id, state.objects)
    audit.record(db, "data_exported", actor_id=principal.user_id)
    await db.commit()
    return Response(
        data, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="lingard-export.zip"'}
    )


@router.post("/me/delete", status_code=204)
async def remove_account(body: DeleteAccountBody, principal: Principal, state: State, db: Db) -> None:
    if not await state.auth.verify_pin(principal.user_id, body.pin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "PIN is wrong")
    try:
        await delete_account(db, principal.user_id, state.clone_providers, state.objects, state.graph_deps.memory)
    except CascadeError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Deletion not verified: {exc}") from exc
    await db.commit()
