"""Per-turn live loop (SPEC §6.3): STT → gate → language check → Actor stream → sentence → Guard → TTS → speak.

Replies are *prepared* (STT, actor, guard and TTS run into a buffer) and later *committed* (spoken, recorded,
published). A ``SpeculativeTurn`` starts preparation during the end-of-turn silence, so most of the cascade's latency
is hidden inside the wait the learner needs anyway; ``LearnerSpeechResumed`` discards it. Side effects happen only
on commit. Every committed learner turn is published as a ``TurnEvent``; assessment never blocks the conversation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

import lingard_telemetry as telemetry
from lingard_contracts.common import CITY_LOCALE
from lingard_contracts.events import NpcContext, TurnEvent, TurnTimings
from lingard_contracts.live import (
    AudioChunk,
    BargeIn,
    Closed,
    LearnerAudio,
    LearnerSpeechResumed,
    LearnerSpeechStarted,
    LearnerTurnEnded,
    SpeculativeTurn,
    personalised_turn_policy,
)
from lingard_live.actor import ActorState, DialogueTurn, NpcActor
from lingard_live.events import HintSource, TurnPublisher, fire_and_forget
from lingard_live.guard import ContractGuard, GuardContext, GuardResult, Verdict
from lingard_live.languages import LanguageConfig, LanguageIdentifier, words
from lingard_live.sentences import SentenceSplitter, split_stream
from lingard_live.stt import SttProvider, Transcript
from lingard_live.stt_stream import StreamingStt, SttStream
from lingard_live.transport import LiveSession
from lingard_live.tts import TtsProvider, VoiceSpec
from lingard_live.turn_end import completeness
from lingard_live.turn_gate import EchoCheck, GatePolicy, TurnDecision, validate_turn

logger = logging.getLogger(__name__)
_NO_ECHO = EchoCheck(checked=False, matched=False)
STREAM_FINISH_TIMEOUT_S = 1.5
SECOND_EAR_TIMEOUT_S = 10.0
"""The second hearing only delays the turn's assessment, never the reply; past this it is skipped."""
"""Longer than a streamed commit ever takes (≈0.3 s), shorter than giving up on batch would cost."""
SHORT_REACTION_WORDS = 3
"""A sentence this short ("Ah, d'accord.") is a reaction, not one of the reply's sentences."""
WRAP_UP_HINT = "The scene is nearly over: bring the conversation to a natural close in the next reply."


@dataclass
class TurnTiming:
    """Preparation stages in ms from preparation start; ``first_audio_ms`` from the end-of-turn decision."""

    stt_ms: float = 0
    first_token_ms: float | None = None
    first_sentence_ms: float | None = None
    guard_ms: list[float] = field(default_factory=list)
    first_audio_ms: float | None = None
    total_ms: float = 0
    speculative: bool = False
    filler: bool = False
    """A hesitation played while the first sentence was still being checked."""


def hesitations_for(sentence: str, fillers: list[str]) -> list[str]:
    """The hesitations that don't echo the sentence's first word ("Right… Right, I'll tell you" was heard live)."""
    opening = words(sentence)[:1]
    return [f for f in fillers if words(f)[:1] != opening] or fillers


def _ms(value: float | None) -> str:
    return "-" if value is None else str(round(value))


@dataclass
class TurnOutcome:
    learner_text: str
    npc_text: str
    status: str
    timing: TurnTiming
    guard_results: list[GuardResult] = field(default_factory=list)


@dataclass
class SceneIdentity:
    user_id: uuid.UUID
    session_id: uuid.UUID
    trace_id: uuid.UUID
    learner_band: int


@dataclass
class Prepared:
    transcript: Transcript
    decision: TurnDecision
    status: str  # ignored | clarify | other_language | npc
    timing: TurnTiming
    audio: asyncio.Queue[AudioChunk | str | None] = field(default_factory=asyncio.Queue)
    """Audio chunks, each sentence's text queued just before its audio (for captions), then ``None``."""
    sentences: list[str] = field(default_factory=list)
    guard_results: list[GuardResult] = field(default_factory=list)
    producer: asyncio.Task[None] | None = None
    hint: str | None = None
    failed: bool = False
    """No model produced the reply (provider errors or timeouts on every model of the tier)."""


Spoken = tuple[str, AsyncIterator[AudioChunk]]
"""A sentence to speak and its audio."""


class Prefetch:
    """Synthesises a sentence into a buffer before it is cleared to play; cancelled if the Guard changes it."""

    def __init__(self, audio: AsyncIterator[AudioChunk]) -> None:
        self._chunks: asyncio.Queue[AudioChunk | None] = asyncio.Queue()
        self._task = asyncio.create_task(self._run(audio))

    async def _run(self, audio: AsyncIterator[AudioChunk]) -> None:
        try:
            async for chunk in audio:
                await self._chunks.put(chunk)
        finally:
            await self._chunks.put(None)

    async def chunks(self) -> AsyncIterator[AudioChunk]:
        while (chunk := await self._chunks.get()) is not None:
            yield chunk
        await self._task  # re-raises a synthesis error

    def cancel(self) -> None:
        self._task.cancel()


class LiveLoop:
    def __init__(
        self,
        *,
        session: LiveSession,
        state: ActorState,
        identity: SceneIdentity,
        actor: NpcActor,
        guard: ContractGuard,
        guard_ctx: GuardContext,
        language: LanguageConfig,
        identifier: LanguageIdentifier,
        stt: SttProvider,
        tts: TtsProvider,
        publisher: TurnPublisher,
        hints: HintSource,
        gate: GatePolicy | None = None,
        filler_after_ms: float | None = None,
        stall_filler_after_ms: float | None = None,
        max_reply_sentences: int = 3,
        streaming_stt: StreamingStt | None = None,
        second_ear: SttProvider | None = None,
    ) -> None:
        """``filler_after_ms``: if a reply's first sentence is still held by the claim check this long after it was
        screened, the NPC says a hesitation (``LanguageConfig.fillers``) first; ``None`` never does.
        ``stall_filler_after_ms``: the same when a reply has no first sentence this long after preparation began."""
        self.session = session
        self.state = state
        self.identity = identity
        self.actor = actor
        self.guard = guard
        self.guard_ctx = guard_ctx
        self.language = language
        self.identifier = identifier
        self.stt = stt
        self.tts = tts
        self.publisher = publisher
        self.hints = hints
        self.gate = gate or GatePolicy()
        self.filler_after_ms = filler_after_ms
        self.stall_filler_after_ms = stall_filler_after_ms
        self.max_reply_sentences = max_reply_sentences
        self.streaming_stt = streaming_stt
        self.second_ear = second_ear or stt
        self._stream: tuple[int, SttStream] | None = None
        """The streaming transcription of the utterance in progress, keyed by its speech start."""
        session.set_semantic_eot(self._utterance_complete)  # says "not yet" whenever nothing is streaming
        self.outcomes: list[TurnOutcome] = []
        self.pauses: list[int] = []
        self.learner_turns = 0
        self.discarded_speculations = 0
        self._turn_index = 0
        self._pending: set[asyncio.Task[None]] = set()
        self._current: asyncio.Task[None] | None = None
        self._utterance: str | None = None
        self._speculation: tuple[int, asyncio.Task[Prepared]] | None = None
        self.voice = VoiceSpec(
            voice_id=state.cast.voice_id, language=state.contract.language, rate=state.contract.speech_rate
        )

    @property
    def scene_id(self) -> str:
        return str(self.state.contract.scene_id)

    async def prewarm(self) -> None:
        """Synthesise the stock lines (hesitations, "not sure", "pardon?") in this NPC's voice, so a caching TTS
        can play them without a provider round trip when they are needed."""
        language = self.language
        for line in dict.fromkeys([*language.fillers, *language.unsure, *language.clarify, *language.stalled]):
            async for _ in self.tts.stream(line, self.voice):
                pass

    # ---- event loop ----------------------------------------------------------------------------------------------

    async def run(self) -> None:
        async for event in self.session.events():
            if isinstance(event, LearnerSpeechStarted):
                await self._close_stream()
                if self.streaming_stt is not None:
                    self._stream = (event.at_ms, self.streaming_stt.open(CITY_LOCALE[self.state.contract.city]))
            elif isinstance(event, LearnerAudio):
                if self._stream is not None and self._stream[0] == event.speech_start_ms:
                    await self._stream[1].feed(event.pcm)
            elif isinstance(event, SpeculativeTurn):
                await self._discard_speculation()
                task = asyncio.create_task(
                    self._prepare(event.audio, event.speech_end_ms - event.speech_start_ms, event.speech_start_ms)
                )
                self._speculation = (event.speech_start_ms, task)
            elif isinstance(event, LearnerSpeechResumed):
                await self._discard_speculation()
            elif isinstance(event, LearnerTurnEnded):
                committed_at = time.perf_counter()
                if self._current is not None and not self._current.done():
                    await self._interrupt()
                self._current = asyncio.create_task(self._end_of_turn(event, committed_at))
            elif isinstance(event, BargeIn):
                await self._interrupt()
            elif isinstance(event, Closed):
                break
        await self._discard_speculation()
        if self._current is not None:
            await asyncio.gather(self._current, return_exceptions=True)
        await self._close_stream()
        await asyncio.gather(*self._pending, return_exceptions=True)

    def _utterance_complete(self, _audio: bytes) -> float:
        """Semantic end of turn from the running transcript of the utterance in progress."""
        return completeness(self._stream[1].partial(), self.language) if self._stream is not None else 0.0

    async def _close_stream(self) -> None:
        if self._stream is not None:
            stream, self._stream = self._stream[1], None
            await stream.close()

    async def _end_of_turn(self, event: LearnerTurnEnded, committed_at: float) -> None:
        prepared: Prepared | None = None
        if self._speculation is not None and self._speculation[0] == event.speech_start_ms:
            _, task = self._speculation
            self._speculation = None
            prepared = await task
            prepared.timing.speculative = True
        else:
            await self._discard_speculation()
        if prepared is None:
            prepared = await self._prepare(
                event.audio, event.speech_end_ms - event.speech_start_ms, event.speech_start_ms
            )
        await self._commit(prepared, event, committed_at)

    async def handle_turn(self, event: LearnerTurnEnded) -> None:
        """Non-speculative turn (also used by tests and benchmarks)."""
        committed_at = time.perf_counter()
        await self._commit(
            await self._prepare(event.audio, event.speech_end_ms - event.speech_start_ms), event, committed_at
        )

    async def handle_speculative_turn(self, speculation: SpeculativeTurn, event: LearnerTurnEnded) -> None:
        """Prepare at the speculation point, wait out the rest of the end-of-turn silence, then commit."""
        task = asyncio.create_task(
            self._prepare(speculation.audio, speculation.speech_end_ms - speculation.speech_start_ms)
        )
        await asyncio.sleep(max(event.eot_decided_ms - speculation.at_ms, 0) / 1000)
        committed_at = time.perf_counter()
        prepared = await task
        prepared.timing.speculative = True
        await self._commit(prepared, event, committed_at)

    async def _discard_speculation(self) -> None:
        if self._speculation is None:
            return
        _, task = self._speculation
        self._speculation = None
        self.discarded_speculations += 1
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            prepared = await task
            await self._abandon(prepared)

    async def _abandon(self, prepared: Prepared) -> None:
        if prepared.producer is not None:
            prepared.producer.cancel()
            await asyncio.gather(prepared.producer, return_exceptions=True)
        if prepared.hint and self.state.pending_hint is None:
            self.state.pending_hint = prepared.hint  # the hint was taken for a reply that never played

    async def _interrupt(self) -> None:
        if self._utterance is not None:
            await self.session.cancel_speech(self._utterance)
            self.state.interrupted = True
        if self._current is not None and not self._current.done():
            self._current.cancel()
            await asyncio.gather(self._current, return_exceptions=True)

    # ---- preparation (no side effects visible to the learner or the world) ----------------------------------------

    async def _transcribe(self, audio: bytes, speech_start_ms: int | None) -> Transcript:
        """The streamed transcript when this utterance was streamed; batch transcription otherwise or on any failure."""
        locale = CITY_LOCALE[self.state.contract.city]
        if self._stream is not None and self._stream[0] == speech_start_ms:
            try:
                streamed = await self._stream[1].finish(STREAM_FINISH_TIMEOUT_S)
                if streamed.text:
                    return streamed
            except Exception as exc:  # streaming only speeds a turn up; batch stays the source of truth
                logger.warning("streaming STT failed, using batch: %s", exc)
        return await self.stt.transcribe(audio, locale)

    async def _prepare(self, audio: bytes, speech_ms: int, speech_start_ms: int | None = None) -> Prepared:
        started = time.perf_counter()
        timing = TurnTiming()
        transcript = await self._transcribe(audio, speech_start_ms)
        timing.stt_ms = (time.perf_counter() - started) * 1000
        recent = [t.text for t in self.state.dialogue[-4:] if t.speaker != "learner"]
        decision = validate_turn(
            transcript.text,
            confidence=transcript.confidence,
            speech_ms=speech_ms,
            recent_npc_lines=recent,
            policy=self.gate,
        )
        if decision.status == "ignored":
            return Prepared(transcript, decision, "ignored", timing)
        if decision.status == "needs_confirmation":
            return self._fixed(transcript, decision, "clarify", self.language.pick(self.language.clarify), timing)
        detected = self.identifier.identify(transcript.text)
        if detected is not None and detected != self.language.language:
            line = self.language.pick(self.language.other_language_reply)
            return self._fixed(transcript, decision, "other_language", line, timing)

        prepared = Prepared(transcript, decision, "npc", timing)
        prepared.hint = await self.hints.take(self.scene_id)
        hint = prepared.hint or self.state.pending_hint
        if self.learner_turns + 1 >= self.state.contract.max_turns - 1:
            hint = WRAP_UP_HINT
        self.guard_ctx.admit_learner_text(transcript.text)
        tokens = self.actor.reply(self.state, str(self.identity.trace_id), pending_learner=transcript.text, hint=hint)
        prepared.producer = asyncio.create_task(self._produce(prepared, tokens, started))
        return prepared

    def _fixed(
        self, transcript: Transcript, decision: TurnDecision, status: str, line: str, timing: TurnTiming
    ) -> Prepared:
        prepared = Prepared(transcript, decision, status, timing)

        async def one() -> AsyncIterator[Spoken]:
            yield line, self.tts.stream(line, self.voice)

        prepared.producer = asyncio.create_task(self._synthesise(prepared, one()))
        return prepared

    async def _produce(self, prepared: Prepared, tokens: AsyncIterator[str], started: float) -> None:
        """Rules screen each sentence as it completes (a blocked sentence never reaches TTS). The claim check then runs
        while earlier sentences play and the screened sentence's audio is prefetched, so it costs only what exceeds
        the time to that sentence's first audio chunk. Prefetched audio plays only once the check confirms it."""
        timing = prepared.timing
        pending: asyncio.Queue[tuple[GuardResult, asyncio.Task[GuardResult], Prefetch | None] | None] = asyncio.Queue()
        tasks: list[Prefetch | asyncio.Task[GuardResult]] = []

        async def timed() -> AsyncIterator[str]:
            async for token in tokens:
                if timing.first_token_ms is None:
                    timing.first_token_ms = (time.perf_counter() - started) * 1000
                yield token

        async def split() -> None:
            said = 0
            try:
                async for sentence in split_stream(timed(), SentenceSplitter(self.language.abbreviations)):
                    if timing.first_sentence_ms is None:
                        timing.first_sentence_ms = (time.perf_counter() - started) * 1000
                    screened = await self.guard.screen(sentence, self.guard_ctx)
                    timing.guard_ms.append(screened.elapsed_ms)
                    confirm = asyncio.create_task(self.guard.confirm(screened, self.guard_ctx))
                    prefetch = None
                    if self.guard.will_check_claims(screened, self.guard_ctx):
                        prefetch = Prefetch(self.tts.stream(screened.text, self.voice))
                        tasks.append(prefetch)
                    tasks.append(confirm)
                    await pending.put((screened, confirm, prefetch))
                    if len(words(sentence)) > SHORT_REACTION_WORDS:
                        said += 1
                    if said >= self.max_reply_sentences:
                        break  # a learner needs room to answer: the rest of a long reply is never spoken
            except Exception as exc:  # every model failed: the fallback line covers it, the scene goes on
                prepared.failed = True
                logger.warning("no model produced the reply: %s", exc)
            finally:
                await pending.put(None)

        def hesitate(before: str | None = None) -> Spoken:
            timing.filler = True
            fillers = hesitations_for(before, self.language.fillers) if before else self.language.fillers
            filler = self.language.pick(fillers)
            return filler, self.tts.stream(filler, self.voice)

        async def guarded() -> AsyncIterator[Spoken]:
            # A hesitation covers the wait for an answer; the opening line answers nobody ("So… Hiya" was heard live).
            first = prepared.decision.reason != "opening"
            head = asyncio.ensure_future(pending.get())
            if first and self.stall_filler_after_ms is not None:
                waited_ms = (time.perf_counter() - started) * 1000
                ready, _ = await asyncio.wait({head}, timeout=max(self.stall_filler_after_ms - waited_ms, 0) / 1000)
                if not ready:
                    yield hesitate()  # the model is slow: a silence would read as the line having dropped

            async def items() -> AsyncIterator[tuple[GuardResult, asyncio.Task[GuardResult], Prefetch | None]]:
                try:
                    item = await head
                    while item is not None:
                        yield item
                        item = await pending.get()
                finally:
                    head.cancel()

            async for screened, confirm, prefetch in items():
                if first and not timing.filler and prefetch is not None and self.filler_after_ms is not None:
                    done, _ = await asyncio.wait({confirm}, timeout=self.filler_after_ms / 1000)
                    if not done:
                        yield hesitate(screened.text)
                first = False
                result = await confirm
                prepared.guard_results.append(result)
                if result.verdict is Verdict.BLOCK:
                    logger.info("guard blocked sentence (%s)", ",".join(result.reasons))
                    if prefetch is not None:
                        prefetch.cancel()
                    continue
                if prefetch is not None and result.text == screened.text:
                    yield result.text, prefetch.chunks()
                    continue
                if prefetch is not None:
                    prefetch.cancel()
                yield result.text, self.tts.stream(result.text, self.voice)

        splitter = asyncio.create_task(split())
        try:
            await self._synthesise(prepared, guarded(), fallback=lambda: self._fallback(prepared))
        finally:
            splitter.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(splitter, return_exceptions=True)

    def _fallback(self, prepared: Prepared) -> str:
        if prepared.failed:
            return self.language.pick(self.language.stalled)
        withheld_claim = any(
            r.verdict is Verdict.BLOCK and {"unsupported_claim", "claim_check_timeout"} & set(r.reasons)
            for r in prepared.guard_results
        )
        return self.language.pick(self.language.unsure if withheld_claim else self.language.clarify)

    async def _synthesise(
        self, prepared: Prepared, spoken: AsyncIterator[Spoken], fallback: Callable[[], str] | None = None
    ) -> None:
        try:
            async for sentence, audio in spoken:
                prepared.sentences.append(sentence)
                await prepared.audio.put(sentence)
                async for chunk in audio:
                    await prepared.audio.put(chunk)
            if fallback and all(s in self.language.fillers for s in prepared.sentences):
                line = fallback()
                prepared.sentences.append(line)
                await prepared.audio.put(line)
                async for chunk in self.tts.stream(line, self.voice):
                    await prepared.audio.put(chunk)
        finally:
            await prepared.audio.put(None)

    # ---- commit (speak, remember, publish) -------------------------------------------------------------------------

    async def _commit(self, prepared: Prepared, event: LearnerTurnEnded, committed_at: float) -> None:
        timing = prepared.timing
        text = prepared.transcript.text
        if prepared.status == "ignored":
            self.outcomes.append(TurnOutcome(text, "", f"ignored:{prepared.decision.reason}", timing))
            return
        with telemetry.span(
            "live.turn", trace_id=str(self.identity.trace_id), scene=self.scene_id, speculative=timing.speculative
        ):
            self.pauses.extend(event.pauses_ms)
            self.learner_turns += 1
            await self.session.set_turn_policy(personalised_turn_policy(self.identity.learner_band, self.pauses))
            self._publish_learner(prepared.transcript, event)
            await self.session.caption("learner", text)
            if prepared.status == "npc":
                self.state.dialogue.append(DialogueTurn("learner", text))
                self.state.pending_hint = None
                self.state.interrupted = False
            try:
                await self._speak(prepared, committed_at)
            except asyncio.CancelledError:
                await self._abandon(prepared)
                raise
            npc_text = " ".join(prepared.sentences)
            if prepared.status == "npc":
                self.state.dialogue.append(DialogueTurn(self.state.persona.key, npc_text))
                self.guard_ctx.admit_npc_text(npc_text)
                self._publish_npc(npc_text)
            timing.total_ms = (time.perf_counter() - committed_at) * 1000
            status = "ok" if prepared.status == "npc" else prepared.status
            self.outcomes.append(TurnOutcome(text, npc_text, status, timing, prepared.guard_results))
            logger.info(
                "turn %s: waited %d ms for the end of turn, then first audio after %s ms (speculative=%s filler=%s; "
                "from preparation start: stt %d, first token %s, first sentence %s, guard %s)",
                status,
                event.eot_decided_ms - event.speech_end_ms,
                _ms(timing.first_audio_ms),
                timing.speculative,
                timing.filler,
                timing.stt_ms,
                _ms(timing.first_token_ms),
                _ms(timing.first_sentence_ms),
                [round(ms) for ms in timing.guard_ms],
            )

    async def opening(self) -> TurnOutcome:
        """The NPC speaks first when the scene starts."""
        committed_at = time.perf_counter()
        timing = TurnTiming()
        prepared = Prepared(
            Transcript("", None, "none"), TurnDecision("accepted", "opening", _NO_ECHO, ""), "npc", timing
        )
        tokens = self.actor.reply(self.state, str(self.identity.trace_id))
        prepared.producer = asyncio.create_task(self._produce(prepared, tokens, committed_at))
        await self._speak(prepared, committed_at)
        npc_text = " ".join(prepared.sentences)
        self.state.dialogue.append(DialogueTurn(self.state.persona.key, npc_text))
        self.guard_ctx.admit_npc_text(npc_text)
        self._publish_npc(npc_text)
        outcome = TurnOutcome("", npc_text, "ok", timing, prepared.guard_results)
        self.outcomes.append(outcome)
        return outcome

    async def _speak(self, prepared: Prepared, committed_at: float) -> None:
        utterance_id = uuid.uuid4().hex
        self._utterance = utterance_id

        async def audio() -> AsyncIterator[AudioChunk]:
            hesitation: str | None = None  # "Mm…" joins the sentence it leads into instead of a bubble of its own
            while (item := await prepared.audio.get()) is not None:
                if isinstance(item, str):
                    if item in self.language.fillers:
                        hesitation = item
                    else:
                        await self.session.caption("npc", f"{hesitation} {item}" if hesitation else item)
                        hesitation = None
                    continue
                if prepared.timing.first_audio_ms is None:
                    prepared.timing.first_audio_ms = (time.perf_counter() - committed_at) * 1000
                yield item
            if hesitation:
                await self.session.caption("npc", hesitation)

        try:
            await self.session.speak(audio(), utterance_id)
        finally:
            self._utterance = None
        if prepared.producer is not None:
            await asyncio.gather(prepared.producer, return_exceptions=True)

    def _event(self, speaker: str, text: str, **extra: object) -> TurnEvent:
        event = TurnEvent(
            trace_id=self.identity.trace_id,
            user_id=self.identity.user_id,
            session_id=self.identity.session_id,
            scene_id=self.state.contract.scene_id,
            turn_index=self._turn_index,
            speaker=speaker,
            language=CITY_LOCALE[self.state.contract.city],
            transcript=text,
            targets_active=self.state.contract.targets.all(),
            **extra,
        )
        self._turn_index += 1
        return event

    def _publish_learner(self, transcript: Transcript, event: LearnerTurnEnded) -> None:
        last_npc = next((t.text for t in reversed(self.state.dialogue) if t.speaker != "learner"), "")
        turn = self._event(
            "learner",
            transcript.text,
            stt_confidence=transcript.confidence,
            timings_ms=TurnTimings(
                speech_start=event.speech_start_ms, speech_end=event.speech_end_ms, eot_decided=event.eot_decided_ms
            ),
            pauses_ms=list(event.pauses_ms),
            npc_context=NpcContext(npc_id=self.state.persona.key, last_npc_line=last_npc),
            interrupted_npc=event.interrupted_npc,
        )
        streamed = self.streaming_stt is not None and transcript.provider == self.streaming_stt.name
        fire_and_forget(self.publisher, turn, self._pending, self._second_ear(event.audio) if streamed else None)

    def _second_ear(self, audio: bytes) -> Callable[[TurnEvent], Awaitable[TurnEvent]]:
        """The batch recogniser's hearing of a streamed turn, so corrections can be checked against both."""

        async def hear(turn: TurnEvent) -> TurnEvent:
            try:
                async with asyncio.timeout(SECOND_EAR_TIMEOUT_S):
                    other = await self.second_ear.transcribe(audio, CITY_LOCALE[self.state.contract.city])
            except Exception as exc:  # no second hearing: corrections then rest on the checks alone
                logger.warning("second hearing failed: %s", exc)
                return turn
            return turn.model_copy(update={"transcript_alternatives": [other.text]}) if other.text else turn

        return hear

    def _publish_npc(self, text: str) -> None:
        fire_and_forget(self.publisher, self._event("npc", text), self._pending)
