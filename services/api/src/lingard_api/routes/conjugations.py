"""``/v1/conjugations``: verb tables a learner opens by tapping a verb anywhere in a lesson or a mission brief.

Built from the language's conjugation content with no model call. The index says which words in a sentence are verbs
(and which verb); the tables come one verb at a time, when a verb is tapped.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel

from lingard_api.deps import Principal, State
from lingard_api.routes.speech import narrate, wav_response
from lingard_contracts.common import Language
from lingard_curriculum.conjugation import Conjugations, Conjugator, Form, TenseTable, VerbTables, load_conjugator

router = APIRouter(prefix="/v1/conjugations", tags=["conjugations"])


class VerbIndex(BaseModel):
    persons: list[str]
    tenses: list[TenseTable]
    """Each tense's name and level, easiest first (no forms)."""
    index: dict[str, str]
    """A word as written in a sentence (lower-cased, without an elided pronoun such as j') → its verb's key."""
    focus: list[str]
    """The tenses the grammar point asked about (``node``) is about: the tables open on the first."""


@cache
def _conjugator(content_root: Path, language: Language) -> tuple[Conjugator, Conjugations] | None:
    conjugator = load_conjugator(content_root / "curriculum" / language / "conjugation.yaml")
    return (conjugator, conjugator.tables()) if conjugator else None


def _require(content_root: Path, language: Language) -> tuple[Conjugator, Conjugations]:
    loaded = _conjugator(content_root, language)
    if loaded is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No verb tables for this language")
    return loaded


@router.get("/{language}", response_model=VerbIndex)
async def verb_index(language: Language, _: Principal, state: State, node: str | None = None) -> VerbIndex:
    conjugator, tables = _require(state.settings.content_root, language)
    return VerbIndex(
        persons=tables.persons,
        tenses=tables.tenses,
        index=tables.index,
        focus=conjugator.focus(node) if node else [],
    )


@router.get("/{language}/{verb}", response_model=VerbTables)
async def verb_tables(language: Language, verb: str, _: Principal, state: State) -> VerbTables:
    tables = _require(state.settings.content_root, language)[1]
    found = next((v for v in tables.verbs if v.key == verb), None)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such verb")
    return found


def spoken(form: Form) -> str:
    """« j'ai parlé », « il parle » (il/elle is said as il), as a narrator reads the cell."""
    subject = form.subject.split("/", 1)[0]
    return f"{subject}{'' if subject.endswith("'") else ' '}{form.word}"


@router.get("/{language}/{verb}/say")
async def say_form(
    language: Language, verb: str, tense: str, person: int, request: Request, _: Principal, state: State
) -> Response:
    """Hear one form of a verb's table, with its subject, said by the language's narrator (cached once rendered)."""
    found = await verb_tables(language, verb, _, state)
    table = next((t for t in found.tenses if t.tense == tense), None)
    if table is None or not 0 <= person < len(table.forms):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such form")
    try:
        pcm = await narrate(state, spoken(table.forms[person]), language)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return wav_response(pcm, request)
