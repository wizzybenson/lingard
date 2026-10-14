"""Accent Studio (SPEC §13.4): shadowing lines, scoring through the pronunciation service, FSRS on the final attempt."""

from __future__ import annotations

import base64
from functools import cache
from pathlib import Path
from typing import Annotated, Any

import httpx
import yaml
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from lingard_api.deps import Principal, State
from lingard_api.routes.speech import MAX_UPLOAD_BYTES, decode_audio
from lingard_contracts.common import Language
from lingard_graphs.pedagogy.review import new_card, review
from lingard_pronunciation.studio import MAX_ATTEMPTS, PASS_SCORE

router = APIRouter(prefix="/v1/studio", tags=["studio"])


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


@router.post("/shadow")
async def shadow(
    principal: Principal,
    state: State,
    audio: Annotated[UploadFile, File()],
    line: Annotated[str, Form()],
    language: Annotated[Language, Form()],
    attempt: Annotated[int, Form(ge=1, le=MAX_ATTEMPTS)] = 1,
) -> dict[str, Any]:
    known = dict((text, key) for key, text in _lines(state.settings.content_root, language))
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
    try:
        response = await state.pronunciation.post("/shadow", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "pronunciation service unreachable") from exc
    if response.status_code != 200:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, response.json().get("detail", "scoring failed"))
    result: dict[str, Any] = response.json()

    passed = result["intelligibility"] >= PASS_SCORE
    final = passed or attempt >= MAX_ATTEMPTS
    if final:  # one FSRS review per line per session: pass first time = Good, on a retry = Hard, never = Again
        store, node_key = state.graph_deps.store, known[line]
        card = (await store.fsrs(principal.user_id)).get(node_key) or new_card()
        await store.save_fsrs(principal.user_id, node_key, review(card, passed, hesitant=passed and attempt > 1))
    return {**result, "passed": passed, "final": final, "attempts_left": 0 if final else MAX_ATTEMPTS - attempt}
