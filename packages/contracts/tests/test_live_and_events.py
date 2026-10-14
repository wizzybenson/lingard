from uuid import uuid4

from pydantic import TypeAdapter

from lingard_contracts.assessment import ErrorTag, Span
from lingard_contracts.events import TurnEvent
from lingard_contracts.live import AudioChunk, LiveEvent, base_eot_for_band, personalised_turn_policy


def test_turn_event_roundtrip_through_stream_fields() -> None:
    event = TurnEvent(
        trace_id=uuid4(),
        user_id=uuid4(),
        session_id=uuid4(),
        scene_id=uuid4(),
        turn_index=14,
        speaker="learner",
        language="fr-FR",
        transcript="Si j'aurais su, je serais venu plus tôt.",
        stt_confidence=0.91,
        pauses_ms=[380, 920],
        targets_active=["fr.grammar.si_plus_pluperfect"],
    )
    again = TurnEvent.from_stream_fields(event.stream_fields())
    assert again == event


def test_base_eot_by_band() -> None:
    assert [base_eot_for_band(b) for b in (3, 4, 5, 6, 7, 8, 9, 12)] == [1200, 1200, 950, 950, 750, 750, 600, 600]


def test_personalised_policy_uses_p90_plus_margin_and_cap() -> None:
    assert personalised_turn_policy(9, []).eot_ms == 600
    assert personalised_turn_policy(9, [300] * 8 + [1000] * 2).eot_ms == 1150
    assert personalised_turn_policy(3, [2000] * 10).eot_ms == 1600


def test_live_event_discriminator() -> None:
    adapter: TypeAdapter[LiveEvent] = TypeAdapter(LiveEvent)
    event = adapter.validate_python({"kind": "barge_in", "utterance_id": "u1", "at_ms": 10})
    assert event.kind == "barge_in"


def test_audio_chunk_duration() -> None:
    assert AudioChunk(pcm=b"\x00\x00" * 16000).duration_ms == 1000


def test_error_tag_showable_needs_confidence_and_second_check() -> None:
    span = Span(start=0, end=10, text="Si j'aurais")
    base = {"node_key": "fr.grammar.si_imparfait", "span": span}
    assert not ErrorTag(**base, confidence=0.9).showable
    assert not ErrorTag(**base, confidence=0.8, second_check_agrees=True).showable
    assert ErrorTag(**base, confidence=0.9, second_check_agrees=True).showable
