"""Accent Studio (SPEC §13.4): shadowing lines, scoring through the pronunciation service, FSRS on the final attempt."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
import yaml
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lingard_api.deps import Db, Principal, State
from lingard_api.routes.speech import (
    MAX_UPLOAD_BYTES,
    NARRATION_EDITION,
    _live_settings,
    decode_audio,
    narrate,
    wav_response,
)
from lingard_api.state import AppState
from lingard_contracts.common import CITY_LOCALE, LANGUAGE_CITY, Language
from lingard_db.models import LearnerProfile, User, VoiceProfile
from lingard_graphs.pedagogy.review import new_card, review
from lingard_live.languages import load_language
from lingard_live.tts import OpenAITts, VoiceSpec
from lingard_pronunciation.g2p import LexiconG2P
from lingard_pronunciation.gym import (
    HEAR_GOOD,
    Drill,
    Gym,
    Progress,
    Stage,
    ending,
    load_gym,
    partners,
    record_attempt,
    target_score,
)
from lingard_pronunciation.gym import NEEDED as GYM_NEEDED
from lingard_pronunciation.studio import MAX_ATTEMPTS, PASS_SCORE
from lingard_storage import AUDIO_BUCKET

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/studio", tags=["studio"])
NEEDED_STAGES = set(GYM_NEEDED)
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


def _gym(state: AppState, language: Language) -> Gym:
    return load_gym(state.settings.content_root, language)


def _speakable(state: AppState, language: Language, text: str) -> bool:
    """Only the studio's own texts are rendered and scored: its lines, every drill text, and pairs said together."""
    if text in _line_nodes(state, language) or text in _gym(state, language).texts():
        return True
    return any(text == f"{a} / {b}" for drill in _gym(state, language).drills for a, b in drill.pairs)


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
        model = await _melody_model(state, line, language) or await _checked_model(state, line, language)
        native = model if model is not None else await narrate(state, line, language)
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


MELODY_TRIES = 5


async def _melody_model(state: AppState, text: str, language: Language) -> bytes | None:
    """The model of a melody-drill text: rendered with instructions to rise (a question) or fall (a statement), and
    kept only once the pronunciation service measures that ending in it; ``None`` for other texts, or when no render
    carried the melody (the everyday narrator is used then)."""
    gym = _gym(state, language)
    want = ending(text)
    if text not in gym.melody_texts() or want is None or state.pronunciation is None:
        return None
    key = f"cache/melody/{hashlib.sha256(f'{language}|{text}'.encode()).hexdigest()}.pcm"
    with contextlib.suppress(Exception):  # not rendered yet
        return await state.objects.get(AUDIO_BUCKET, key)
    live = _live_settings(state)
    api_key = live.openai_api_key.get_secret_value() if live.openai_api_key else None
    if not api_key:
        return None
    narrator = load_language(state.settings.content_root, language).narrator_voice
    instructions = gym.melody_model.get("question" if want == "rise" else "statement", "")
    tts = OpenAITts(api_key, model=live.openai_tts_model)
    for _ in range(MELODY_TRIES):
        voice = VoiceSpec(voice_id=narrator, language=language, style=instructions)
        pcm = b"".join([chunk.pcm async for chunk in tts.stream(text, voice)])
        payload = {
            "text": text,
            "language": language,
            "learner_pcm_b64": base64.b64encode(pcm).decode(),
            "reference_pcm_b64": base64.b64encode(pcm).decode(),
        }
        measured = (await state.pronunciation.post("/shadow", json=payload)).json()
        found = ((measured.get("prosody") or {}).get("intonation") or {}).get("final", {}).get("yours")
        if found == want and await _clean(state, text, language, pcm):
            await state.objects.put(AUDIO_BUCKET, key, pcm, "audio/L16")
            return pcm
    return None


async def _with_melody(state: AppState, drill: Drill, texts: tuple[str, ...], language: Language) -> list[str]:
    """A melody drill's texts that have a verified model: one whose rise or fall could not be rendered is left out
    rather than taught with a flat model (``cli warm-studio`` renders them ahead of time)."""
    if drill.focus != "intonation" or state.pronunciation is None:
        return list(texts)
    kept = []
    for text in texts:
        if ending(text) is None or await _melody_model(state, text, language) is not None:
            kept.append(text)
    return kept or list(texts)


NARRATOR_TAKES = 3
OTHER_TAKES = 3
"""Renders tried for a drill text's model: the narrator's first, then another native voice. Every engine sometimes
adds stray sounds to a short word (a breath or an "euh" before "rue", an "e" after "roue": 1 word in 6 to 12 on
2026-10-22, at random), so each take is checked and the first clean one kept."""
CHECK_EDITION = 4
"""4: a model must also have no sounds beyond the text's own, a tie at either end counting as extra and a nasal
vowel's nasality heard as an "n" not (1 only checked the scorer passed it)."""
CHECKED: dict[str, str] = {}
"""Verdicts on model recordings already read from the object store: "narrator", "other" or "none"."""
CHECKS: dict[str, asyncio.Future[str]] = {}
"""Checks running now, so a burst of requests for one text (iOS fetches audio in byte ranges) checks it once."""


def _check_key(language: str, text: str) -> str:
    recipe = f"{CHECK_EDITION}|{NARRATION_EDITION}|{language}|{text}"
    return f"cache/model-check/{hashlib.sha256(recipe.encode()).hexdigest()}"


def _first_stage(gym: Gym, text: str) -> tuple[Drill, Stage] | None:
    """The drill and spoken stage a text is first said at, for judging its model the way a learner's take is judged."""
    for drill in gym.drills:
        for stage in (Stage.WORDS, Stage.PAIRS, Stage.PHRASES, Stage.SENTENCE):
            if text in drill.items(stage):
                return drill, stage
    return None


async def _clean(state: AppState, text: str, language: Language, pcm: bytes) -> bool:
    """Nothing heard beyond the text's own sounds: no breath, "euh" or stray syllable before or after it."""
    if state.pronunciation is None:
        raise RuntimeError("model checks need the pronunciation service")
    asked = {"text": text, "language": language, "pcm_b64": base64.b64encode(pcm).decode()}
    heard = (await state.pronunciation.post("/heard", json=asked)).json()
    if heard.get("before") or heard.get("after"):
        log.info("model of %r has stray sounds: heard %s", text, heard.get("heard"))
        return False
    return True


async def _passes(state: AppState, gym: Gym, text: str, language: Language, pcm: bytes) -> bool:
    """Whether a recording of a drill text can be a model: nothing heard beyond the text's own sounds, and the scorer
    passing it as it would pass a learner saying it (a contrast compared by ear passes: the machine doesn't judge
    it)."""
    found = _first_stage(gym, text)
    if state.pronunciation is None:
        raise RuntimeError("model checks need the pronunciation service")
    if found is None:
        return True
    if not await _clean(state, text, language, pcm):
        return False
    audio = base64.b64encode(pcm).decode()
    drill, stage = found
    g2p = _g2p(state.settings.content_root)
    payload = {
        "text": text,
        "language": language,
        "learner_pcm_b64": audio,
        "reference_pcm_b64": audio,
        "partners": partners(drill, lambda t: g2p.phonemes(t, language)),
    }
    result = _expected_melody((await state.pronunciation.post("/shadow", json=payload)).json(), text, drill)
    words = result.get("words", [])
    _, by_ear = target_score(drill, words)
    return by_ear or record_attempt(Progress(stage), drill, stage, text, words, result.get("prosody"))


async def check_model(state: AppState, text: str, language: Language) -> str:
    """Verifies a drill text's model before learners hear it, since they imitate it and are scored against it: the
    narrator's render if it is clean and the scorer passes it, else a fresh narrator take, else another native voice
    (the kept take is stored), else "none" and the text is left out of its drill rather than taught with a doubtful
    model. Run once per text, the first time it is asked for (or by ``cli warm-studio``)."""
    key = _check_key(language, text)
    if (known := await _verdict(state, text, language)) is not None:
        return known
    if (running := CHECKS.get(key)) is not None:
        return await asyncio.shield(running)
    done: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    done.add_done_callback(lambda f: f.cancelled() or f.exception())  # an error nobody awaited is not "unretrieved"
    CHECKS[key] = done
    try:
        verdict = await _find_model(state, key, text, language)
    except BaseException as exc:
        done.set_exception(exc)
        raise
    else:
        done.set_result(verdict)
    finally:
        CHECKS.pop(key, None)
    return verdict


async def _find_model(state: AppState, key: str, text: str, language: Language) -> str:
    gym = _gym(state, language)
    verdict, kept = "none", None
    for take in range(NARRATOR_TAKES):
        pcm = await narrate(state, text, language, take)
        if await _passes(state, gym, text, language, pcm):
            verdict, kept = ("narrator", None) if take == 0 else ("other", pcm)
            break
    live = _live_settings(state)
    if verdict == "none" and live.openai_api_key:
        tts = OpenAITts(live.openai_api_key.get_secret_value(), model=live.openai_tts_model)
        narrator = load_language(state.settings.content_root, language).narrator_voice
        style = gym.melody_model.get("question" if ending(text) == "rise" else "statement", "")
        for _ in range(OTHER_TAKES):
            spec = VoiceSpec(voice_id=narrator, language=language, style=style)
            pcm = b"".join([chunk.pcm async for chunk in tts.stream(text, spec)])
            if await _passes(state, gym, text, language, pcm):
                verdict, kept = "other", pcm
                break
    if kept is not None:
        await state.objects.put(AUDIO_BUCKET, f"{key}.pcm", kept, "audio/L16")
    await state.objects.put(AUDIO_BUCKET, f"{key}.verdict", verdict.encode(), "text/plain")
    CHECKED[key] = verdict
    return verdict


async def _verdict(state: AppState, text: str, language: Language) -> str | None:
    """A text's checked verdict, ``None`` when not checked yet."""
    key = _check_key(language, text)
    if key not in CHECKED:
        try:
            CHECKED[key] = (await state.objects.get(AUDIO_BUCKET, f"{key}.verdict")).decode()
        except Exception:
            return None
    return CHECKED[key]


async def _checked_model(state: AppState, text: str, language: Language) -> bytes | None:
    """The model of a drill text, checked first if it hasn't been: the kept take when the narrator's first render
    wasn't clean; ``None`` to use the narrator's render (it passed, the text isn't a drill text, or no take passed)."""
    gym = _gym(state, language)
    if text in gym.melody_texts() or _first_stage(gym, text) is None or state.pronunciation is None:
        return None
    try:
        verdict = await check_model(state, text, language)
    except Exception:  # the pronunciation service or TTS is unreachable: the narrator's render, checked next time
        log.warning("model check failed for %r", text, exc_info=True)
        return None
    if verdict != "other":
        return None
    try:
        return await state.objects.get(AUDIO_BUCKET, f"{_check_key(language, text)}.pcm")
    except Exception:  # its render went missing: the narrator's stands in
        return None


async def _with_models(state: AppState, texts: list[str], language: Language) -> list[str]:
    """A drill's texts without those no checked model could be found for (all of them if that would empty it)."""
    kept = [text for text in texts if await _verdict(state, text, language) != "none"]
    return kept or texts


def _expected_melody(result: dict[str, Any], text: str, drill: Drill | None) -> dict[str, Any]:
    """In a melody drill the ending is fixed by the text, not by however a model happened to read it: rising where a
    question must rise passes that part, and moving the wrong way never does."""
    music = result.get("prosody")
    want = ending(text)
    if drill is None or drill.focus != "intonation" or want is None or not music or not music.get("intonation"):
        return result
    intonation = dict(music["intonation"])
    final = {**(intonation.get("final") or {}), "expected": want}
    score = float(intonation["score"])
    intonation["score"] = round(max(score, 75.0) if final.get("yours") == want else min(score, 50.0), 1)
    intonation["final"] = final
    return {**result, "prosody": {**music, "intonation": intonation}}


@router.get("/reference")
async def reference(
    request: Request, principal: Principal, state: State, db: Db, line: str, language: Language
) -> Response:
    if not _speakable(state, language, line):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a studio line")
    pcm = await _reference(state, db, principal.user_id, line, language)
    if pcm is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no TTS provider available")
    return wav_response(pcm, request, revalidate=True)


@router.post("/shadow")
async def shadow(
    principal: Principal,
    state: State,
    db: Db,
    audio: Annotated[UploadFile, File()],
    line: Annotated[str, Form()],
    language: Annotated[Language, Form()],
    attempt: Annotated[int, Form(ge=1, le=MAX_ATTEMPTS)] = 1,
    drill: Annotated[str | None, Form()] = None,
    stage: Annotated[int | None, Form(ge=Stage.WORDS, le=Stage.MASTERED)] = None,
) -> dict[str, Any]:
    """Scores one recording of a studio line or drill text. A drill attempt (``drill`` and ``stage``) climbs that
    drill's ladder; a line keeps its three tries and its FSRS review."""
    known = _line_nodes(state, language)
    if not _speakable(state, language, line):
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
    gym = _gym(state, language)
    try:
        chosen = gym.drill(drill) if drill is not None else None
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such drill") from exc
    payload: dict[str, Any] = {"text": line, "language": language, "learner_pcm_b64": base64.b64encode(pcm).decode()}
    if chosen is not None:  # the trained sounds get the two-way test against their pair partners
        g2p = _g2p(state.settings.content_root)
        payload["partners"] = partners(chosen, lambda text: g2p.phonemes(text, language))
    if (reference_pcm := await _reference(state, db, principal.user_id, line, language)) is not None:
        payload["reference_pcm_b64"] = base64.b64encode(reference_pcm).decode()
    try:
        response = await state.pronunciation.post("/shadow", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "pronunciation service unreachable") from exc
    if response.status_code != 200:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, response.json().get("detail", "scoring failed"))
    result: dict[str, Any] = _expected_melody(response.json(), line, chosen)

    await state.graph_deps.store.mark_active(principal.user_id, datetime.now(UTC).date(), "sounds")
    user, profile = await _learner(db, principal.user_id)
    _remember_sounds(profile, language, result.get("words", []))
    tips = _tips(gym, result.get("words", []), user.ui_locale, chosen.sounds if chosen else ())
    if chosen is not None and stage is not None:
        progress = _progress(profile, language, chosen)
        good = _attempt(progress, chosen, Stage(stage), line, result)
        _save_progress(profile, language, chosen, progress)
        await db.commit()
        _, by_ear = target_score(chosen, result.get("words", []))
        return {
            **result,
            "tips": tips,
            "good": good,
            "by_ear": by_ear,  # the trained sound is judged by ear, not by machine
            "progress": _progress_view(chosen, progress),
        }
    await db.commit()
    if line not in known:
        return {
            **result,
            "tips": tips,
            "passed": result["intelligibility"] >= PASS_SCORE,
            "final": True,
            "attempts_left": 0,
        }
    passed = result["intelligibility"] >= PASS_SCORE
    final = passed or attempt >= MAX_ATTEMPTS
    if final:  # one FSRS review per line per session: pass first time = Good, on a retry = Hard, never = Again
        store, node_key = state.graph_deps.store, known[line]
        card = (await store.fsrs(principal.user_id)).get(node_key) or new_card()
        await store.save_fsrs(principal.user_id, node_key, review(card, passed, hesitant=passed and attempt > 1))
    return {
        **result,
        "tips": tips,
        "passed": passed,
        "final": final,
        "attempts_left": 0 if final else MAX_ATTEMPTS - attempt,
    }


# ---- sound gym (decision 0028) ---------------------------------------------------------------------------------------

REVIEW_DAYS = (2, 5, 12, 30, 75)
"""Days to each review of a climbed drill: a sound sticks once it has held across weeks, not one good afternoon."""
EMA = 0.3
"""Weight of the newest attempt in a sound's running score."""


async def _learner(db: AsyncSession, user_id: uuid.UUID) -> tuple[User, LearnerProfile]:
    user = await db.get_one(User, user_id)
    profile = (await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == user_id))).scalar_one()
    return user, profile


def _remember_sounds(profile: LearnerProfile, language: str, words: list[dict[str, Any]]) -> None:
    """A running score per sound across every attempt: what the gym's "your sounds" ranks by."""
    sounds = dict(profile.settings.get("gym_sounds", {}).get(language, {}))
    for phoneme in (p for w in words for p in w["phonemes"]):
        old = sounds.get(phoneme["phoneme"])
        new = float(phoneme["score"])
        sounds[phoneme["phoneme"]] = round(new if old is None else (1 - EMA) * old + EMA * new, 1)
    profile.settings = {**profile.settings, "gym_sounds": {**profile.settings.get("gym_sounds", {}), language: sounds}}


def _guide_language(ui_locale: str | None) -> str:
    return ui_locale if ui_locale in ("en", "fr") else "en"


def _tips(
    gym: Gym, words: list[dict[str, Any]], ui_locale: str | None, targets: tuple[str, ...]
) -> list[dict[str, Any]]:
    """What to change, for each sound said wrong: the fix for what it was heard as, else how to make it."""
    lang = _guide_language(ui_locale)
    tips: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for word in words:
        for sound in word["phonemes"]:
            phoneme, heard = sound["phoneme"], sound.get("heard_as")
            guide = gym.phonemes.get(phoneme)
            if guide is None or sound["score"] >= 70 or (phoneme, heard) in seen or not sound.get("checked", True):
                continue
            if targets and phoneme not in targets and sound["score"] >= 50:
                continue  # in a drill, other sounds are only mentioned when clearly off
            seen.add((phoneme, heard))
            fix = (guide.get("confusions") or {}).get(heard, {}).get(lang) if heard else None
            tips.append(
                {
                    "phoneme": phoneme,
                    "example": guide["example"],
                    "word": word["text"],
                    "heard_as": heard,
                    "text": fix or guide[lang]["check"],
                    "steps": [] if fix else guide[lang]["steps"],
                }
            )
    # The trained sound first: in "poisson" said as "poison", the s/z fix leads, not a note about another sound.
    return sorted(tips, key=lambda tip: tip["phoneme"] not in targets)


def _all_progress(profile: LearnerProfile, language: str) -> dict[str, Any]:
    return dict(profile.settings.get("gym", {}).get(language, {}))


def _progress(profile: LearnerProfile, language: str, drill: Drill) -> Progress:
    progress = Progress.load(_all_progress(profile, language).get(drill.key))
    progress.start(drill)
    return progress


def _save_progress(profile: LearnerProfile, language: str, drill: Drill, progress: Progress) -> None:
    raw = _all_progress(profile, language)
    old = raw.get(drill.key, {})
    entry = {**old, **progress.dump()}
    if progress.stage is Stage.MASTERED and old.get("stage") != Stage.MASTERED:
        entry["reviews"] = 0
        entry["due"] = (datetime.now(UTC) + timedelta(days=REVIEW_DAYS[0])).isoformat()
    raw[drill.key] = entry
    profile.settings = {**profile.settings, "gym": {**profile.settings.get("gym", {}), language: raw}}


def _attempt(progress: Progress, drill: Drill, stage: Stage, text: str, result: dict[str, Any]) -> bool:
    """A climbing attempt, or (on a mastered drill) a review: holding up moves the next review further out; slipping
    sends the drill back to its words."""
    words, music = result.get("words", []), result.get("prosody")
    if stage is not Stage.MASTERED:
        return record_attempt(progress, drill, stage, text, words, music)
    return record_attempt(Progress(Stage.SENTENCE), drill, Stage.SENTENCE, text, words, music)


def _review(profile: LearnerProfile, language: str, drill: Drill, held: bool) -> None:
    raw = _all_progress(profile, language)
    entry = dict(raw.get(drill.key, {}))
    if held:
        reviews = int(entry.get("reviews", 0)) + 1
        days = REVIEW_DAYS[min(reviews, len(REVIEW_DAYS) - 1)]
        entry.update(reviews=reviews, due=(datetime.now(UTC) + timedelta(days=days)).isoformat())
    else:
        first_spoken = next(s for s in drill.stages() if s >= Stage.WORDS)
        entry.update(stage=int(first_spoken), passed_items=[], reviews=0, due=None)
    raw[drill.key] = entry
    profile.settings = {**profile.settings, "gym": {**profile.settings.get("gym", {}), language: raw}}


class GymText(BaseModel):
    text: str
    words: list[dict[str, Any]]
    """Each written word with its phonemes and which of them the drill trains (to mark them)."""


class SoundGuide(BaseModel):
    phoneme: str
    example: str
    features: dict[str, Any]
    how: dict[str, Any]
    """lips, tongue, jaw, voice, air, steps and check, in the learner's interface language."""
    confusions: dict[str, str]
    """What was heard instead → how to fix it."""


class DrillSummary(BaseModel):
    key: str
    title: str
    sounds: list[str]
    examples: list[str]
    stage: int
    stages: list[int]
    mastered: bool
    due: datetime | None = None
    review_due: bool = False
    score: float | None = None
    """The running score of the drill's weakest sound (or of the whole drill when it trains no sounds)."""


class DrillView(DrillSummary):
    guides: list[SoundGuide]
    pairs: list[tuple[str, str]]
    pair_texts: list[GymText]
    """Each pair as said in the pairs stage ("rue / roue"), its sounds marked."""
    features: dict[str, dict[str, Any]]
    """Where every sound of the language (and every sound learners substitute) is made, for the mouth map."""
    words: list[GymText]
    phrases: list[GymText]
    sentence: GymText
    focus: str | None
    """For a drill on the music of speech: stress, emphasis, rhythm or intonation."""
    passed_items: list[str]
    needed: int


class GymView(BaseModel):
    drills: list[DrillSummary]
    workout: list[str]
    """Today's short session: reviews that are due, then the drills being climbed, weakest first (at most three)."""
    sounds: dict[str, float]


async def _title(state: AppState, drill: Drill, gym: Gym) -> str:
    node = await state.curriculum.get(drill.key)
    if node is not None:
        return str(node.title)
    return " · ".join(f"/{s}/ {gym.phonemes[s]['example']}" for s in drill.sounds)


def _summary_fields(drill: Drill, gym: Gym, entry: dict[str, Any], sounds: dict[str, float]) -> dict[str, Any]:
    progress = Progress.load(entry)
    progress.start(drill)
    due = datetime.fromisoformat(entry["due"]) if entry.get("due") else None
    mastered = progress.stage is Stage.MASTERED
    scores = [sounds[s] for s in drill.sounds if s in sounds]
    return {
        "key": drill.key,
        "sounds": list(drill.sounds),
        "examples": [str(gym.phonemes[s]["example"]) for s in drill.sounds],
        "stage": int(progress.stage),
        "stages": [int(s) for s in drill.stages()],
        "mastered": mastered,
        "due": due,
        "review_due": mastered and due is not None and due <= datetime.now(UTC),
        "score": min(scores) if scores else None,
    }


def _progress_view(drill: Drill, progress: Progress) -> dict[str, Any]:
    return {
        "stage": int(progress.stage),
        "passed_items": progress.passed_items,
        "mastered": progress.stage is Stage.MASTERED,
        "best": progress.best,
    }


@router.get("/gym", response_model=GymView)
async def gym_overview(principal: Principal, state: State, db: Db, language: Language) -> GymView:
    _, profile = await _learner(db, principal.user_id)
    return await overview(state, profile, language)


async def overview(state: AppState, profile: LearnerProfile, language: Language) -> GymView:
    """Every drill with where the learner stands on it, and today's workout (also the sounds stop of today's path)."""
    gym = _gym(state, language)
    entries = _all_progress(profile, language)
    sounds = dict(profile.settings.get("gym_sounds", {}).get(language, {}))
    drills = [
        DrillSummary(title=await _title(state, d, gym), **_summary_fields(d, gym, entries.get(d.key, {}), sounds))
        for d in gym.drills
    ]
    due = [d.key for d in drills if d.review_due]
    # Being climbed means begun: a drill without sounds starts on a later rung, but is still new until touched.
    climbing = sorted(
        (d for d in drills if not d.mastered and d.key in entries),
        key=lambda d: d.score if d.score is not None else 100,
    )
    fresh = [d.key for d in drills if not d.mastered and d.key not in entries]
    workout = [*due, *(d.key for d in climbing), *fresh][:3]
    return GymView(drills=drills, workout=workout, sounds=sounds)


@cache
def _g2p(content_root: Path) -> LexiconG2P:
    return LexiconG2P(content_root)


def _marked(drill: Drill, text: str, language: str, state: AppState) -> GymText:
    words = []
    for written, phonemes in _g2p(state.settings.content_root).words(text, language):
        targets = [i for i, p in enumerate(phonemes) if p in drill.sounds]
        words.append({"text": written, "phonemes": phonemes, "targets": targets})
    return GymText(text=text, words=words)


@router.get("/gym/{key}", response_model=DrillView)
async def gym_drill(key: str, principal: Principal, state: State, db: Db, language: Language) -> DrillView:
    user, profile = await _learner(db, principal.user_id)
    gym = _gym(state, language)
    try:
        drill = gym.drill(key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such drill") from exc
    lang = _guide_language(user.ui_locale)
    entry = _all_progress(profile, language).get(key, {})
    sounds = dict(profile.settings.get("gym_sounds", {}).get(language, {}))
    progress = _progress(profile, language, drill)
    guides = [
        SoundGuide(
            phoneme=s,
            example=str(gym.phonemes[s]["example"]),
            features=gym.features.get(s, {}),
            how=gym.phonemes[s][lang],
            confusions={heard: fix[lang] for heard, fix in (gym.phonemes[s].get("confusions") or {}).items()},
        )
        for s in drill.sounds
    ]
    stage = Stage(progress.stage) if progress.stage in NEEDED_STAGES else Stage.SENTENCE
    return DrillView(
        title=await _title(state, drill, gym),
        **_summary_fields(drill, gym, entry, sounds),
        guides=guides,
        pairs=list(drill.pairs),
        pair_texts=[
            _marked(drill, text, language, state)
            for text in await _with_models(state, [f"{a} / {b}" for a, b in drill.pairs], language)
        ],
        features=gym.features,
        words=[_marked(drill, w, language, state) for w in await _with_models(state, list(drill.words), language)],
        phrases=[
            _marked(drill, p, language, state)
            for p in await _with_models(state, await _with_melody(state, drill, drill.phrases, language), language)
        ],
        sentence=_marked(drill, drill.sentence, language, state),
        focus=drill.focus,
        passed_items=progress.passed_items,
        needed=min(GYM_NEEDED.get(stage, 1), max(len(drill.items(stage)), 1)),
    )


class StepBody(BaseModel):
    language: Language
    stage: Literal[0, 1]
    """0: the learner has read how the sounds are made; 1: the listening quiz, with its score."""
    score: float | None = Field(default=None, ge=0, le=1)


@router.post("/gym/{key}/step")
async def gym_step(key: str, body: StepBody, principal: Principal, state: State, db: Db) -> dict[str, Any]:
    """The two stages the server cannot hear: having learned the sounds, and the listening quiz."""
    _, profile = await _learner(db, principal.user_id)
    gym = _gym(state, body.language)
    try:
        drill = gym.drill(key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such drill") from exc
    progress = _progress(profile, body.language, drill)
    passed = body.stage == 0 or (body.score is not None and body.score >= HEAR_GOOD)
    if passed and int(progress.stage) == body.stage:
        progress.advance(drill)
        _save_progress(profile, body.language, drill, progress)
        await db.commit()
    return {"passed": passed, "progress": _progress_view(drill, progress)}


class ReviewBody(BaseModel):
    language: Language
    held: bool


@router.post("/gym/{key}/review")
async def gym_review(key: str, body: ReviewBody, principal: Principal, state: State, db: Db) -> dict[str, Any]:
    """A review of a climbed drill is over: it held (the next one moves further out) or slipped (back to words)."""
    _, profile = await _learner(db, principal.user_id)
    try:
        drill = _gym(state, body.language).drill(key)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such drill") from exc
    _review(profile, body.language, drill, body.held)
    await db.commit()
    entry = _all_progress(profile, body.language)[key]
    return {"stage": entry["stage"], "due": entry.get("due"), "reviews": entry.get("reviews", 0)}
