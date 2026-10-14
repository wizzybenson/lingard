"""``/v1/speech`` and item audio: server-side STT for spoken answers, TTS for listening items (scripts stay private)."""

from __future__ import annotations

import io
import wave
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from lingard_api.deps import Principal, State
from lingard_api.state import AppState
from lingard_contracts.common import Language
from lingard_exam_packs.items import ItemBank
from lingard_live.audio import pcm_to_wav, wav_to_pcm
from lingard_live.languages import load_language
from lingard_live.settings import LiveSettings, build_stt, build_tts
from lingard_live.tts import VoiceSpec

router = APIRouter(prefix="/v1", tags=["speech"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def decode_audio(data: bytes) -> bytes:
    """Any common recording (WAV, M4A/AAC from iOS and Android, WebM/Opus from browsers) → 16 kHz mono PCM."""
    try:
        return wav_to_pcm(data)
    except (wave.Error, EOFError, ValueError):
        pass
    import av

    try:
        container = av.open(io.BytesIO(data), mode="r")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16_000)
        # to_ndarray() trims the planes' alignment padding, which bytes(plane) would include.
        chunks = [r.to_ndarray().tobytes() for frame in container.decode(audio=0) for r in resampler.resample(frame)]
        chunks += [r.to_ndarray().tobytes() for r in resampler.resample(None)]
    except (av.error.FFmpegError, IndexError) as exc:
        raise ValueError("unsupported or corrupt audio") from exc
    return b"".join(chunks)


def _live_settings(state: State) -> LiveSettings:
    settings = state.settings
    return LiveSettings(
        voicebox_url=settings.voicebox_url,
        elevenlabs_api_key=settings.elevenlabs_api_key,
        content_root=settings.content_root,
    )


@router.post("/speech/transcribe")
async def transcribe(
    principal: Principal,
    state: State,
    audio: Annotated[UploadFile, File()],
    language: Annotated[Language, Form()] = "fr",
) -> dict[str, object]:
    data = await audio.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "recording too long")
    try:
        stt = build_stt(_live_settings(state))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    try:
        pcm = decode_audio(data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    result = await stt.transcribe(pcm, load_language(state.settings.content_root, language).stt_locale)
    return {"text": result.text, "confidence": result.confidence}


@router.get("/items/{item_id}/audio")
async def item_audio(item_id: str, principal: Principal, state: State) -> Response:
    """Listening items are rendered here; the client never receives the script."""
    try:
        item = ItemBank.load(state.settings.content_root).get(item_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item") from exc
    if item.skill.value != "listening":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a listening item")
    try:
        pcm = await narrate(state, item.stimulus, item.language)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return wav_response(pcm)


async def narrate(state: AppState, text: str, language: Language) -> bytes:
    """16 kHz PCM of ``text`` in the language's narrator voice. Raises ``RuntimeError`` when no TTS is configured."""
    if state.tts is None:
        state.tts = build_tts(_live_settings(state))
    voice = VoiceSpec(voice_id=load_language(state.settings.content_root, language).narrator_voice, language=language)
    return b"".join([chunk.pcm async for chunk in state.tts.stream(text, voice)])


def wav_response(pcm: bytes) -> Response:
    return Response(pcm_to_wav(pcm), media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"})
