import asyncio
import statistics
import uuid
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from lingard_contracts.live import BargeIn, Closed, LearnerTurnEnded, LiveSessionConfig, TurnPolicy
from lingard_live.actor import NpcActor
from lingard_live.events import MemoryBus
from lingard_live.guard import ContractGuard
from lingard_live.languages import LanguageIdentifier, load_language
from lingard_live.loop import LiveLoop, SceneIdentity
from lingard_live.scene import SceneRuntime
from lingard_live.stt import ScriptedStt, Transcript
from lingard_live.transport import LoopbackSession, LoopbackTransport
from lingard_live.tts import ScriptedTts
from lingard_llm import LLMConfig, LLMRouter, ModelSpec, PromptRegistry
from lingard_llm.testing import ScriptedChatModel, message_text

ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]


def turn(audio_ms: int = 2000) -> LearnerTurnEnded:
    return LearnerTurnEnded(
        audio=b"\x00\x00" * 16 * audio_ms,
        speech_start_ms=0,
        speech_end_ms=audio_ms,
        eot_decided_ms=audio_ms + 900,
        pauses_ms=(400,),
    )


async def build(
    runtime: SceneRuntime,
    responder: Callable[[list[BaseMessage]], str],
    transcripts: list[str],
    *,
    llm_first_token_s: float = 0.0,
    stt_delay_ms: int = 0,
    tts_delay_ms: int = 0,
) -> tuple[LiveLoop, LoopbackSession, MemoryBus, ScriptedChatModel, ScriptedTts]:
    model = ScriptedChatModel(responder=responder, first_token_delay_s=llm_first_token_s, token_delay_s=0.005)
    config = LLMConfig.model_validate(
        {"tiers": {"fast": {"retries": 0, "models": [{"provider": "scripted", "model": "s"}]}}}
    )

    def factory(spec: ModelSpec) -> BaseChatModel:
        return model

    router = LLMRouter(config, factory=factory)
    prompt = PromptRegistry(ROOT / "prompts").get("npc_actor")
    session = await LoopbackTransport().open(
        LiveSessionConfig(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            scene_id=runtime.state.contract.scene_id,
            room="r",
            locale="fr-FR",
            policy=TurnPolicy(eot_ms=950),
        )
    )
    bus = MemoryBus()
    tts = ScriptedTts(first_chunk_delay_ms=tts_delay_ms)
    languages = [load_language(ROOT / "content", "fr"), load_language(ROOT / "content", "en")]
    loop = LiveLoop(
        session=session,
        state=runtime.state,
        identity=SceneIdentity(user_id=uuid.uuid4(), session_id=uuid.uuid4(), trace_id=uuid.uuid4(), learner_band=6),
        actor=NpcActor(router, prompt),
        guard=ContractGuard(LanguageIdentifier(languages)),
        guard_ctx=runtime.guard_ctx,
        language=runtime.language,
        identifier=LanguageIdentifier(languages),
        stt=ScriptedStt([Transcript(t, 0.92, "scripted") for t in transcripts], delay_ms=stt_delay_ms),
        tts=tts,
        publisher=bus,
        hints=bus,
    )
    return loop, session, bus, model, tts


async def test_full_turn_publishes_events_and_speaks_guarded_sentences(runtime: SceneRuntime) -> None:
    replies = iter(
        [
            "Bonjour Ernest. Le dépôt était de 900 dollars.",
            "Je vous rends 450 dollars. Si je refusais, que feriez-vous ?",
            "Hmm. Je vais réfléchir.",
        ]
    )
    loop, session, bus, model, tts = await build(
        runtime,
        lambda m: next(replies),
        ["Bonjour monsieur, je viens pour mon dépôt.", "Je voudrais récupérer tout mon dépôt, s'il vous plaît."],
    )
    await loop.opening()
    task = asyncio.create_task(loop.run())
    session.push(turn())
    await asyncio.sleep(0.2)
    session.push(turn())
    await asyncio.sleep(0.2)
    session.push(Closed())
    await task

    assert tts.spoken[0] == "Bonjour Ernest."
    assert ("npc", "Bonjour Ernest.") in session.captions
    assert ("learner", "Bonjour monsieur, je viens pour mon dépôt.") in session.captions
    assert ("npc", "Je vous rends 450 dollars.") not in session.captions, "blocked sentences are never captioned"
    assert "Je vous rends 450 dollars." not in tts.spoken, "invented amount must be blocked before TTS"
    assert "Si je refusais, que feriez-vous ?" in tts.spoken
    learner_events = [e for e in bus.events if e.speaker == "learner"]
    assert [e.turn_index for e in bus.events] == sorted(e.turn_index for e in bus.events)
    assert learner_events[0].targets_active and learner_events[0].pauses_ms == [400]
    assert learner_events[0].npc_context is not None and "900" in learner_events[0].npc_context.last_npc_line
    assert learner_events[1].npc_context is not None
    assert learner_events[1].npc_context.last_npc_line == "Si je refusais, que feriez-vous ?"
    system = message_text(model.calls[-1][0])
    assert "Le dépôt était de 900 dollars" in system and "Martin Lefebvre" in system
    assert "si_imparfait" not in system, "hidden curriculum keys never reach the actor"
    assert session.policy.eot_ms >= 950


async def test_other_language_gets_in_world_reply_without_llm(runtime: SceneRuntime) -> None:
    loop, session, _bus, model, tts = await build(runtime, lambda m: "unused", ["Sorry, do you speak English please?"])
    task = asyncio.create_task(loop.run())
    session.push(turn())
    await asyncio.sleep(0.1)
    session.push(Closed())
    await task
    assert loop.outcomes[0].status == "other_language"
    assert tts.spoken[0] in runtime.language.other_language_reply
    assert model.calls == []


async def test_low_confidence_asks_to_repeat(runtime: SceneRuntime) -> None:
    loop, session, _, model, _tts = await build(runtime, lambda m: "unused", ["peut-être le dépôt"])
    loop.stt = ScriptedStt([Transcript("Je voudrais mon dépôt", 0.5, "scripted")])
    task = asyncio.create_task(loop.run())
    session.push(turn())
    await asyncio.sleep(0.1)
    session.push(Closed())
    await task
    assert loop.outcomes[0].status == "clarify" and model.calls == []


async def test_barge_in_cancels_npc_speech_and_flags_interruption(runtime: SceneRuntime) -> None:
    long_reply = " ".join(["Écoutez, la fissure est là depuis votre arrivée."] * 6)
    loop, session, _, model, _tts = await build(
        runtime, lambda m: long_reply, ["Je voudrais mon dépôt.", "Attendez !"], tts_delay_ms=30
    )
    task = asyncio.create_task(loop.run())
    session.push(turn())
    await asyncio.sleep(0.15)
    session.push(BargeIn(utterance_id="any", at_ms=0))
    await asyncio.sleep(0.05)
    assert any(u.cancelled for u in session.spoken)
    session.push(turn())
    await asyncio.sleep(0.3)
    session.push(Closed())
    await task
    assert "interrupted" in message_text(model.calls[-1][0])


async def test_pipeline_overhead_on_top_of_provider_latency(runtime: SceneRuntime) -> None:
    """With realistic provider latencies, Lingard's own code must add almost nothing on top of them."""
    stt_ms, llm_ms, tts_ms = 150, 250, 120
    replies = ["D'accord. Le mur a une petite fissure, vous savez."] * 10
    it = iter(replies)
    loop, _session, _, _, _ = await build(
        runtime,
        lambda m: next(it),
        ["Je voudrais récupérer mon dépôt."] * 10,
        llm_first_token_s=llm_ms / 1000,
        stt_delay_ms=stt_ms,
        tts_delay_ms=tts_ms,
    )
    for _ in range(10):
        await loop.handle_turn(turn())
    first_audio = [o.timing.first_audio_ms for o in loop.outcomes if o.timing.first_audio_ms]
    p50 = statistics.median(first_audio)
    provider_floor = stt_ms + llm_ms + tts_ms
    assert p50 < provider_floor + 120, f"overhead {p50 - provider_floor:.0f} ms over providers"
    assert max(max(o.timing.guard_ms) for o in loop.outcomes if o.timing.guard_ms) < 50


async def test_speculation_commits_prepared_audio_almost_instantly(runtime: SceneRuntime) -> None:
    from lingard_contracts.live import SpeculativeTurn

    loop, _, _, model, _ = await build(
        runtime,
        lambda m: "D'accord. Le mur a une petite fissure.",
        ["Je voudrais récupérer mon dépôt."],
        llm_first_token_s=0.3,
        stt_delay_ms=200,
        tts_delay_ms=150,
    )
    spec = SpeculativeTurn(audio=b"\x00\x00" * 32000, speech_start_ms=0, speech_end_ms=2000, at_ms=2400)
    end = LearnerTurnEnded(audio=spec.audio, speech_start_ms=0, speech_end_ms=2000, eot_decided_ms=3300)
    await loop.handle_speculative_turn(spec, end)
    outcome = loop.outcomes[-1]
    assert outcome.timing.speculative and outcome.status == "ok"
    assert outcome.timing.first_audio_ms is not None and outcome.timing.first_audio_ms < 60
    assert len(model.calls) == 1


async def test_resumed_speech_discards_speculation_without_side_effects(runtime: SceneRuntime) -> None:
    from lingard_contracts.live import LearnerSpeechResumed, SpeculativeTurn

    loop, session, bus, model, tts = await build(
        runtime,
        lambda m: "Hmm. D'accord.",
        ["Je voudrais", "Je voudrais récupérer mon dépôt complet."],
        llm_first_token_s=0.05,
    )
    loop.hints.hints[loop.scene_id] = "steer gently"  # type: ignore[attr-defined]
    task = asyncio.create_task(loop.run())
    session.push(SpeculativeTurn(audio=b"\x00\x00" * 16000, speech_start_ms=0, speech_end_ms=1000, at_ms=1400))
    await asyncio.sleep(0.02)
    session.push(LearnerSpeechResumed(speech_start_ms=0, at_ms=1500))
    await asyncio.sleep(0.1)
    assert loop.discarded_speculations == 1 and tts.spoken == [] and bus.events == []
    assert loop.state.pending_hint == "steer gently", "a hint consumed by a discarded draft is kept for the next reply"
    session.push(
        LearnerTurnEnded(audio=b"\x00\x00" * 48000, speech_start_ms=0, speech_end_ms=3000, eot_decided_ms=3900)
    )
    await asyncio.sleep(0.3)
    session.push(Closed())
    await task
    assert [o.learner_text for o in loop.outcomes] == ["Je voudrais récupérer mon dépôt complet."]
    assert "steer gently" in message_text(model.calls[-1][0])
