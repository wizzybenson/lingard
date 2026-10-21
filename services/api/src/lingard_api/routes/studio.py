"""Accent Studio (SPEC §13.4): shadowing lines, scoring through the pronunciation service, FSRS on the final attempt."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Annotated, Any

import httpx
import yaml
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lingard_api.deps import Db, Principal, State
from lingard_api.routes.speech import MAX_UPLOAD_BYTES, decode_audio, narrate, wav_response
from lingard_api.state import AppState
from lingard_contracts.common import CITY_LOCALE, LANGUAGE_CITY, Language
from lingard_db.models import VoiceProfile
from lingard_graphs.pedagogy.review import new_card, review
from lingard_pronunciation.studio import MAX_ATTEMPTS, PASS_SCORE

router = APIRouter(prefix="/v1/studio", tags=["studio"])
GOLDEN_PROVIDER = "elevenlabs"
"""Clone provider whose voice ids the pronunciation service's speech-to-speech converter accepts."""


class StudioLine(BaseModel):
    node_key: str
    line: str
    title: str


@cache
def _lines(content_root: Path, language: str) -> tuple[tuple[str, str], ...]:
    data = yaml.safe_load((content_root / "pronunciation" / f"studio_{language}.yaml").read_text())
    return tuple((str(item["node_key"]), str(item["line"])) for item in data["lines"])


@router.get("/items", response_model=list[StudioLine])
async def items(principal: Principal, state: State, language: Language) -> list[StudioLine]:
    out = []
    for node_key, line in _lines(state.settings.content_root, language):
        node = await state.curriculum.get(node_key)
        out.append(StudioLine(node_key=node_key, line=line, title=node.title if node else node_key))
    return out


def _line_nodes(state: AppState, language: Language) -> dict[str, str]:
    return {text: key for key, text in _lines(state.settings.content_root, language)}


async def _golden_profile(db: AsyncSession, user_id: uuid.UUID) -> str | None:
    """The learner's speech-to-speech voice id, if they have consented to and created an ElevenLabs clone."""
    profile = (
        await db.execute(
            select(VoiceProfile).where(
                VoiceProfile.user_id == user_id,
                VoiceProfile.deleted_at.is_(None),
                VoiceProfile.provider == GOLDEN_PROVIDER,
            )
        )
    ).scalar_one_or_none()
    return profile.provider_profile_id if profile else None


async def _reference(
    state: AppState, db: AsyncSession, user_id: uuid.UUID, line: str, language: Language
) -> bytes | None:
    """The line to shadow, and the pitch reference for intonation scoring (SPEC §13.3).

    The golden self (the native render converted into the learner's cloned timbre) when they have a clone; otherwise
    the native narrator render. ``None`` when no TTS is available.
    """
    try:
        native = await narrate(state, line, language)
    except (RuntimeError, httpx.HTTPError):
        return None
    profile_id = await _golden_profile(db, user_id)
    if profile_id is None or state.pronunciation is None:
        return native
    payload = {
        "text": line,
        "accent": CITY_LOCALE[LANGUAGE_CITY[language]],
        "profile_id": profile_id,
        "user_id": str(user_id),
        "native_pcm_b64": base64.b64encode(native).decode(),
    }
    try:
        response = await state.pronunciation.post("/golden", json=payload)
    except httpx.HTTPError:
        return native
    return base64.b64decode(response.json()["pcm_b64"]) if response.status_code == 200 else native


@router.get("/reference")
async def reference(
    request: Request, principal: Principal, state: State, db: Db, line: str, language: Language
) -> Response:
    if line not in _line_nodes(state, language):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a studio line")
    pcm = await _reference(state, db, principal.user_id, line, language)
    if pcm is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no TTS provider available")
    return wav_response(pcm, request)


@router.post("/shadow")
async def shadow(
    principal: Principal,
    state: State,
    db: Db,
    audio: Annotated[UploadFile, File()],
    line: Annotated[str, Form()],
    language: Annotated[Language, Form()],
    attempt: Annotated[int, Form(ge=1, le=MAX_ATTEMPTS)] = 1,
) -> dict[str, Any]:
    known = _line_nodes(state, language)
    if line not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a studio line")
    if state.pronunciation is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "pronunciation scoring is not configured")
    data = await audio.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "recording too long")
    try:
        pcm = decode_audio(data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    payload = {"text": line, "language": language, "learner_pcm_b64": base64.b64encode(pcm).decode()}
    if (reference_pcm := await _reference(state, db, principal.user_id, line, language)) is not None:
        payload["reference_pcm_b64"] = base64.b64encode(reference_pcm).decode()
    try:
        response = await state.pronunciation.post("/shadow", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "pronunciation service unreachable") from exc
    if response.status_code != 200:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, response.json().get("detail", "scoring failed"))
    result: dict[str, Any] = response.json()

    await state.graph_deps.store.mark_active(principal.user_id, datetime.now(UTC).date())
    passed = result["intelligibility"] >= PASS_SCORE
    final = passed or attempt >= MAX_ATTEMPTS
    if final:  # one FSRS review per line per session: pass first time = Good, on a retry = Hard, never = Again
        store, node_key = state.graph_deps.store, known[line]
        card = (await store.fsrs(principal.user_id)).get(node_key) or new_card()
        await store.save_fsrs(principal.user_id, node_key, review(card, passed, hesitant=passed and attempt > 1))
    return {**result, "passed": passed, "final": final, "attempts_left": 0 if final else MAX_ATTEMPTS - attempt}
