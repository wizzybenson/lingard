from pathlib import Path

import yaml

from tools.voicebench.probe import measured_profile, with_measured

ASSUMED = yaml.safe_load((Path(__file__).parents[1] / "profiles.yaml").read_text())["assumed_cloud"]


def test_measured_profile_uses_preferred_providers_and_keeps_network_assumed() -> None:
    result = {
        "stt": {"deepgram": {"median": 210.0, "p95": 300.0, "sigma": 0.2}, "openai": {"median": 500, "sigma": 0.3}},
        "tts": {"elevenlabs": {"median": 150.0, "p95": 200.0, "sigma": 0.25}},
        "llm_first_token": {},
        "llm_token": {},
    }
    profile = measured_profile(result, ASSUMED)
    assert profile["status"] == "measured"
    assert profile["stt_ms"] == {"median": 210.0, "sigma": 0.2}
    assert profile["providers"] == {
        "stt_ms": "deepgram",
        "tts_first_chunk_ms": "elevenlabs",
        "llm_first_token_ms": "assumed",
        "llm_token_ms": "assumed",
    }
    assert profile["llm_first_token_ms"] == ASSUMED["llm_first_token_ms"]
    assert profile["network_ms"] == ASSUMED["network_ms"]


def test_writing_the_profile_keeps_comments_and_replaces_only_measured() -> None:
    text = "# planning assumptions\nassumed_cloud:\n  network_ms: {median: 45, sigma: 0.25}  # one way\n"
    profile = measured_profile({"stt": {}, "tts": {}, "llm_first_token": {}, "llm_token": {}}, ASSUMED)
    once = with_measured(text, profile)
    assert once.startswith(text) and "&id" not in once
    assert with_measured(once, profile) == once, "re-running replaces the block instead of appending another"
    assert yaml.safe_load(once)["measured"]["status"] == "measured"
