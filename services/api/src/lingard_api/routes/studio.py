"""Accent Studio (SPEC §13.4): shadowing lines, scoring through the pronunciation service, FSRS on the final attempt."""

from __future__ import annotations

import base64
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
from lingard_api.routes.speech import MAX_UPLOAD_BYTES, decode_audio, narrate, wav_response
from lingard_api.state import AppState
from lingard_contracts.common import CITY_LOCALE, LANGUAGE_CITY, Language
from lingard_db.models import LearnerProfile, User, VoiceProfile
from lingard_graphs.pedagogy.review import new_card, review
from lingard_pronunciation.g2p import LexiconG2P
from lingard_pronunciation.gym import HEAR_GOOD, Drill, Gym, Progress, Stage, load_gym, record_attempt
from lingard_pronunciation.gym import NEEDED as GYM_NEEDED
from lingard_pronunciation.studio import MAX_ATTEMPTS, PASS_SCORE

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
    if not _speakable(state, language, line):
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
    user, profile = await _learner(db, principal.user_id)
    gym = _gym(state, language)
    _remember_sounds(profile, language, result.get("words", []))
    try:
        chosen = gym.drill(drill) if drill is not None else None
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such drill") from exc
    tips = _tips(gym, result.get("words", []), user.ui_locale, chosen.sounds if chosen else ())
    if chosen is not None and stage is not None:
        progress = _progress(profile, language, chosen)
        good = _attempt(progress, chosen, Stage(stage), line, result)
        _save_progress(profile, language, chosen, progress)
        await db.commit()
        return {**result, "tips": tips, "good": good, "progress": _progress_view(chosen, progress)}
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
            if guide is None or sound["score"] >= 70 or (phoneme, heard) in seen:
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
    return tips


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
    words, intonation = result.get("words", []), result.get("intonation")
    if stage is not Stage.MASTERED:
        return record_attempt(progress, drill, stage, text, words, intonation)
    return record_attempt(Progress(Stage.SENTENCE), drill, Stage.SENTENCE, text, words, intonation)


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
    words: list[GymText]
    phrases: list[GymText]
    sentence: GymText
    melody: bool
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
    gym = _gym(state, language)
    entries = _all_progress(profile, language)
    sounds = dict(profile.settings.get("gym_sounds", {}).get(language, {}))
    drills = [
        DrillSummary(title=await _title(state, d, gym), **_summary_fields(d, gym, entries.get(d.key, {}), sounds))
        for d in gym.drills
    ]
    due = [d.key for d in drills if d.review_due]
    climbing = sorted(
        (d for d in drills if not d.mastered and d.stage > Stage.LEARN),
        key=lambda d: d.score if d.score is not None else 100,
    )
    fresh = [d.key for d in drills if not d.mastered and d.stage <= Stage.LEARN]
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
        words=[_marked(drill, w, language, state) for w in drill.words],
        phrases=[_marked(drill, p, language, state) for p in drill.phrases],
        sentence=_marked(drill, drill.sentence, language, state),
        melody=drill.melody,
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
