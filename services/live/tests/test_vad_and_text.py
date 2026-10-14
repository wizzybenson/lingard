from lingard_contracts.live import (
    BargeIn,
    LearnerSpeechResumed,
    LearnerSpeechStarted,
    LearnerTurnEnded,
    SpeculativeTurn,
    TurnPolicy,
)
from lingard_live.audio import silence, tone
from lingard_live.sentences import SentenceSplitter
from lingard_live.turn_gate import validate_turn
from lingard_live.vad import Endpointer


def speech(ms: int) -> bytes:
    return tone(ms, freq=180, amplitude=8000)


def test_endpointer_waits_through_hesitation_pauses_shorter_than_policy() -> None:
    ep = Endpointer(policy=TurnPolicy(eot_ms=1200))
    events = ep.feed(silence(200) + speech(800) + silence(900) + speech(600) + silence(1300))
    kinds = [type(e) for e in events if isinstance(e, (LearnerSpeechStarted, LearnerTurnEnded))]
    assert kinds == [LearnerSpeechStarted, LearnerTurnEnded], "a 900 ms mid-sentence pause must not end the turn"
    ended = events[-1]
    assert isinstance(ended, LearnerTurnEnded)
    assert 880 <= ended.pauses_ms[0] <= 920
    assert ended.eot_decided_ms - ended.speech_end_ms >= 1200


def test_endpointer_ends_quickly_for_fluent_band() -> None:
    ep = Endpointer(policy=TurnPolicy(eot_ms=600))
    events = ep.feed(speech(1000) + silence(700))
    assert isinstance(events[-1], LearnerTurnEnded)
    assert events[-1].eot_decided_ms - events[-1].speech_end_ms <= 620


def test_premature_cutoff_happens_with_too_short_policy() -> None:
    ep = Endpointer(policy=TurnPolicy(eot_ms=600))
    events = ep.feed(speech(800) + silence(900) + speech(600) + silence(700))
    assert sum(isinstance(e, LearnerTurnEnded) for e in events) == 2


def test_semantic_model_can_end_turn_early() -> None:
    ep = Endpointer(policy=TurnPolicy(eot_ms=1500), semantic_eot=lambda audio: 0.95)
    events = ep.feed(speech(800) + silence(500))
    assert isinstance(events[-1], LearnerTurnEnded)


def test_barge_in_after_250ms_of_learner_speech_during_npc_audio() -> None:
    ep = Endpointer(policy=TurnPolicy(eot_ms=900, barge_in_ms=250))
    ep.npc_started("u1")
    events = ep.feed(speech(200))
    assert not any(isinstance(e, BargeIn) for e in events)
    events = ep.feed(speech(100))
    barge = [e for e in events if isinstance(e, BargeIn)]
    assert barge and barge[0].utterance_id == "u1"
    ended = [e for e in ep.feed(speech(300) + silence(1000)) if isinstance(e, LearnerTurnEnded)]
    assert ended and ended[0].interrupted_npc


def test_clicks_are_discarded() -> None:
    ep = Endpointer(policy=TurnPolicy(eot_ms=600))
    events = ep.feed(speech(60) + silence(800))
    assert not any(isinstance(e, LearnerTurnEnded) for e in events)


def test_sentence_splitter_streams_and_respects_abbreviations() -> None:
    splitter = SentenceSplitter(["M.", "Mme"])
    out = []
    for piece in ["Bonjour M. ", "Martin. Vous ", "allez bien ? Je pa", "ssais par là… Voilà"]:
        out += splitter.feed(piece)
    out += splitter.flush()
    assert out == ["Bonjour M. Martin.", "Vous allez bien ?", "Je passais par là…", "Voilà"]


def test_turn_gate_rejects_echo_and_noise_accepts_real_turns() -> None:
    npc = ["Le dépôt était de neuf cents dollars, c'est ça."]
    assert (
        validate_turn(
            "le dépôt était de neuf cents dollars c'est ça", confidence=0.9, speech_ms=3000, recent_npc_lines=npc
        ).reason
        == "echo_similarity"
    )
    assert validate_turn("la la la la la", confidence=0.9, speech_ms=2000, recent_npc_lines=[]).status == "ignored"
    assert (
        validate_turn("Je voudrais récupérer mon dépôt", confidence=0.5, speech_ms=2500, recent_npc_lines=npc).status
        == "needs_confirmation"
    )
    assert (
        validate_turn("Je voudrais récupérer mon dépôt", confidence=0.9, speech_ms=2500, recent_npc_lines=npc).status
        == "accepted"
    )


def test_speculation_fires_at_40_percent_of_eot_and_is_cancelled_by_resumed_speech() -> None:
    ep = Endpointer(policy=TurnPolicy(eot_ms=1200))
    events = ep.feed(speech(800) + silence(700) + speech(500) + silence(1300))
    kinds = [type(e) for e in events]
    assert kinds == [LearnerSpeechStarted, SpeculativeTurn, LearnerSpeechResumed, SpeculativeTurn, LearnerTurnEnded]
    first = next(e for e in events if isinstance(e, SpeculativeTurn))
    assert 480 <= first.at_ms - first.speech_end_ms <= 500
    final = [e for e in events if isinstance(e, SpeculativeTurn)][-1]
    ended = events[-1]
    assert isinstance(ended, LearnerTurnEnded) and final.audio == ended.audio[: len(final.audio)]
    assert final.speech_start_ms == ended.speech_start_ms


def test_speculation_can_be_disabled() -> None:
    ep = Endpointer(policy=TurnPolicy(eot_ms=900, speculate=False))
    assert not any(isinstance(e, SpeculativeTurn) for e in ep.feed(speech(800) + silence(1000)))
