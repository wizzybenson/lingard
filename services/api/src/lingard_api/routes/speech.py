"""``/v1/speech`` and item audio: server-side STT for spoken answers, TTS for listening items (scripts stay private)."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import wave
from functools import cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from lingard_api.deps import Principal, State
from lingard_api.state import AppState
from lingard_contracts.common import Language
from lingard_exam_packs.items import ItemBank
from lingard_live.audio import pcm_to_wav, wav_to_pcm
from lingard_live.languages import load_language
from lingard_live.settings import LiveSettings, build_stt, build_tts, tts_providers
from lingard_live.tts import TtsProvider, VoiceSpec
from lingard_llm.config import any_llm_configured
from lingard_storage import AUDIO_BUCKET

router = APIRouter(prefix="/v1", tags=["speech"])
log = logging.getLogger(__name__)
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
        _env_file=None,  # the API settings are the single source of provider keys
        voicebox_url=settings.voicebox_url,
        elevenlabs_api_key=settings.elevenlabs_api_key,
        openai_api_key=settings.openai_api_key,
        deepgram_api_key=settings.deepgram_api_key,
        content_root=settings.content_root,
        elevenlabs_tts_model=settings.narration_tts_model,
        tts_timeout_s=30.0,
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
async def item_audio(item_id: str, request: Request, principal: Principal, state: State) -> Response:
    """Listening items are rendered here; the client never receives the script."""
    try:
        item = item_bank(state.settings.content_root).get(item_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item") from exc
    if item.skill.value != "listening":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a listening item")
    try:
        pcm = await narrate(state, item.stimulus, item.language)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return wav_response(pcm, request)


def require_providers(state: AppState, *, llm: bool = False, tts: bool = False) -> None:
    """503 with what to set, before starting something that would otherwise fail halfway through."""
    missing = []
    if llm and not any_llm_configured():
        missing.append("a language model (ANTHROPIC_API_KEY, OPENAI_API_KEY or GOOGLE_API_KEY)")
    if tts and state.tts is None and not tts_providers(_live_settings(state)):
        missing.append("text-to-speech for listening (VOICEBOX_URL, ELEVENLABS_API_KEY or OPENAI_API_KEY)")
    if missing:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Not configured: " + " and ".join(missing))


SPEAKER = re.compile(r"^([MF]\d?)\s*:\s*(.+)$")  # "F1:" or, in French typography, "F1 :"
TURN_GAP = b"\x00\x00" * int(16_000 * 0.35)
"""A breath between speakers, 16 kHz mono PCM."""


def script_turns(text: str) -> list[tuple[str | None, str]]:
    """A listening script as turns. Lines tagged ``M1:``/``F2:`` are speakers (gender, number); untagged text is the
    narrator. A line without a tag continues the turn above it."""
    turns: list[tuple[str | None, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        tagged = SPEAKER.match(line)
        if tagged:
            turns.append((tagged.group(1), tagged.group(2)))
        elif turns:
            turns[-1] = (turns[-1][0], f"{turns[-1][1]} {line}")
        else:
            turns.append((None, line))
    return turns or [(None, text)]


def speaker_voice(language: Language, tag: str | None, narrator: str) -> str:
    """A logical voice per speaker: the provider maps it to a stable voice of that gender (config/voices.yaml)."""
    if tag is None:
        return narrator
    return f"{language}_{'f' if tag[0] == 'F' else 'm'}_speaker{tag[1:] or '1'}"


@cache
def item_bank(content_root: Path) -> ItemBank:
    """The authored bank, parsed once per process (read-only here; the graphs keep their own copy)."""
    return ItemBank.load(content_root)


NARRATION_SLOTS = asyncio.Semaphore(2)
"""Lesson and exam recordings rendered at once, per API process; the live plane has its own budget."""
RENDERING: dict[str, asyncio.Future[bytes]] = {}
"""Renders in flight, by cache key."""


async def _cached(state: AppState, key: str) -> bytes | None:
    try:
        return await state.objects.get(AUDIO_BUCKET, key)
    except Exception as exc:  # a miss (or an unreachable cache) just means rendering it
        log.debug("tts cache miss %s: %s", key, exc)
        return None


async def _render(tts: TtsProvider, text: str, language: Language, narrator: str) -> bytes:
    pieces = []
    for tag, line in script_turns(text):
        voice = VoiceSpec(voice_id=speaker_voice(language, tag, narrator), language=language, rate="slow")
        pieces.append(b"".join([chunk.pcm async for chunk in tts.stream(line, voice)]))
    return TURN_GAP.join(pieces)


async def narrate(state: AppState, text: str, language: Language, take: int = 0) -> bytes:
    """16 kHz PCM of ``text``, one voice per speaker. Rendered once per provider and text, then served from the
    object store: replays cost nothing and start at once. Raises ``RuntimeError`` when no TTS is configured.
    ``take``: another rendering of the same text (a fresh take when one came out with stray sounds)."""
    if state.tts is None:
        state.tts = build_tts(_live_settings(state))
    narrator = load_language(state.settings.content_root, language).narrator_voice
    # The edition changes whenever the voices or pace change, so learners never get the old recording again.
    recipe = f"{NARRATION_EDITION}|{type(state.tts).__name__}|{language}|{narrator}|{text}"
    if take:
        recipe += f"|take {take}"
    digest = hashlib.sha256(recipe.encode()).hexdigest()
    key = f"cache/tts/{digest}.pcm"
    if (cached := await _cached(state, key)) is not None:
        return cached
    # The same line asked for again while it renders (iOS fetches a recording in several byte ranges) waits for that
    # render instead of starting another.
    if (running := RENDERING.get(key)) is not None:
        return await asyncio.shield(running)
    done: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
    done.add_done_callback(lambda f: f.cancelled() or f.exception())  # an error nobody awaited is not "unretrieved"
    RENDERING[key] = done
    try:
        pcm = await _narrate_once(state, state.tts, key, text, language, narrator)
    except BaseException as exc:
        done.set_exception(exc)
        raise
    else:
        done.set_result(pcm)
    finally:
        RENDERING.pop(key, None)
    return pcm


async def _narrate_once(
    state: AppState, tts: TtsProvider, key: str, text: str, language: Language, narrator: str
) -> bytes:
    # A few renders at a time: a lesson opening asked for every recording at once and the provider answered 429
    # (Starter allows only a few concurrent requests). The rest wait, then usually find their text already cached.
    async with NARRATION_SLOTS:
        if (cached := await _cached(state, key)) is not None:
            return cached
        try:
            pcm = await _render(tts, text, language, narrator)
        except Exception:
            log.warning("narration failed once; retrying", exc_info=True)
            await asyncio.sleep(1.5)
            pcm = await _render(tts, text, language, narrator)
        try:  # cached before the slot is freed, so a request waiting for the same line finds it
            await state.objects.put(AUDIO_BUCKET, key, pcm, "audio/L16")
        except Exception as exc:  # the audio is still served; it is only re-rendered next time
            log.warning("tts cache write failed for %s: %s", key, exc)
    return pcm


RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


NARRATION_EDITION = 2
"""2: native voices per language and accent (config/voices.yaml), a slower pace, the fuller model (2026-10-21)."""


def wav_response(pcm: bytes, request: Request, *, revalidate: bool = False) -> Response:
    """The audio as WAV, honouring a byte range: iOS's player asks for ranges before it plays, and stalled forever
    ("buffering") when the whole file came back instead. ``revalidate``: for audio that can be replaced (a studio
    model re-recorded because it had a stray sound), the device asks each time and gets "not modified" while it is
    the same, instead of keeping the old one for a day."""
    wav = pcm_to_wav(pcm)
    tag = f'"{hashlib.sha256(wav).hexdigest()[:32]}"'
    cache = "private, no-cache" if revalidate else "private, max-age=86400"
    headers = {"Cache-Control": cache, "Accept-Ranges": "bytes", "ETag": tag}
    if revalidate and request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    asked = RANGE.match(request.headers.get("range", "").strip())
    if asked is None or asked.groups() == ("", ""):
        return Response(wav, media_type="audio/wav", headers=headers)
    first, last = asked.groups()
    size = len(wav)
    start, end = (size - int(last), size - 1) if first == "" else (int(first), min(int(last or size - 1), size - 1))
    if start < 0 or start >= size or start > end:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return Response(wav[start : end + 1], status_code=206, media_type="audio/wav", headers=headers)
