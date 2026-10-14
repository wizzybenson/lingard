from pathlib import Path

import yaml

from tools.voicebench.probe import measured_profile

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
