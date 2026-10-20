"""A few real turns through the real live loop: real STT (streaming and batch), NPC model, Contract Guard and TTS,
driven by synthesised learner speech played through the real endpointer at real-time pace. Paid but small
(a couple of turns ≈ a few cents); the LiveKit network hop is the only part left out.

    uv run python -m tools.voicebench.live_turns --turns 2 [--language fr|en] [--no-streaming]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from dotenv import load_dotenv

from evals.scenes import eval_scenes
from lingard_contracts.common import CITY_LOCALE
from lingard_contracts.live import Closed, LiveSessionConfig, personalised_turn_policy
from lingard_contracts.scene import SceneContract
from lingard_live.actor import NpcActor
from lingard_live.claims import LlmClaimChecker
from lingard_live.events import MemoryBus
from lingard_live.guard import ContractGuard
from lingard_live.languages import LanguageIdentifier, load_language
from lingard_live.loop import LiveLoop, SceneIdentity
from lingard_live.scene import build_scene
from lingard_live.settings import LiveSettings, build_streaming_stt, build_stt, build_tts
from lingard_live.transport import LoopbackTransport
from lingard_live.tts import VoiceSpec
from lingard_live.vad import FRAME_SAMPLES, Endpointer
from lingard_llm import LLMConfig, LLMRouter, PromptRegistry

LINES = {
    "fr": [
        "Bonjour, je voudrais vous parler de mon dépôt, s'il vous plaît.",
        "Pourquoi est-ce que vous gardez une partie ?",
    ],
    "en": ["Hello, I'd like to talk to you about my deposit, please.", "Why are you keeping part of it?"],
}
CHUNK = FRAME_SAMPLES * 2 * 5
"""100 ms of 16 kHz mono PCM, played every 100 ms like a microphone."""


async def run(
    turns: int, language: str, streaming: bool, contract: SceneContract | None = None, lines: list[str] | None = None
) -> list[dict[str, object]]:
    settings = LiveSettings()
    settings.stt_streaming = streaming
    band = 6
    if contract is None:
        contract, band, _ = next((c, b, n) for c, b, n in eval_scenes(10) if c.language == language)
    runtime = build_scene(contract, settings.content_root, learner_name="Sam")
    languages = [load_language(settings.content_root, "fr"), load_language(settings.content_root, "en")]
    identifier = LanguageIdentifier(languages)
    router = LLMRouter(LLMConfig.load(settings.llm_config))
    prompts = PromptRegistry(settings.prompts_root)
    policy = personalised_turn_policy(band, [])
    session = await LoopbackTransport().open(
        LiveSessionConfig(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            scene_id=contract.scene_id,
            room="bench",
            locale=CITY_LOCALE[contract.city],
            policy=policy,
        )
    )
    tts = build_tts(settings)
    bus = MemoryBus()
    loop = LiveLoop(
        session=session,
        state=runtime.state,
        identity=SceneIdentity(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), band),
        actor=NpcActor(router, prompts.get("npc_actor")),
        guard=ContractGuard(
            identifier,
            claims=LlmClaimChecker(
                router,
                prompts.get("claim_check"),
                deadline_s=settings.claim_check_deadline_s,
                context_lines=settings.claim_check_context_lines,
            ),
            claim_free_words=settings.claim_free_words,
        ),
        guard_ctx=runtime.guard_ctx,
        language=runtime.language,
        identifier=identifier,
        stt=build_stt(settings),
        tts=tts,
        publisher=bus,
        hints=bus,
        filler_after_ms=settings.filler_after_ms,
        streaming_stt=build_streaming_stt(settings),
    )
    await loop.opening()
    task = asyncio.create_task(loop.run())
    endpointer = Endpointer(policy=policy, semantic_eot=session.semantic_eot)
    learner = VoiceSpec(voice_id=f"{language}_m_speaker2", language=language)
    for line in (lines or LINES[language])[:turns]:
        speech = b"".join([chunk.pcm async for chunk in tts.stream(line, learner)])
        audio = speech + b"\x00\x00" * (16 * (policy.eot_ms + 600))
        before = len(loop.outcomes)
        for offset in range(0, len(audio), CHUNK):
            for event in endpointer.feed(audio[offset : offset + CHUNK]):
                session.push(event)
            await asyncio.sleep(0.1)
        for _ in range(150):
            if len(loop.outcomes) > before:
                break
            await asyncio.sleep(0.1)
    session.push(Closed())
    await task
    return [
        {
            "learner": o.learner_text,
            "npc": o.npc_text,
            "status": o.status,
            "stt_ms": round(o.timing.stt_ms),
            "first_token_ms": round(o.timing.first_token_ms or 0),
            "first_sentence_ms": round(o.timing.first_sentence_ms or 0),
            "first_audio_ms": round(o.timing.first_audio_ms or 0),
            "speculative": o.timing.speculative,
            "filler": o.timing.filler,
        }
        for o in loop.outcomes[1:]
    ]


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--turns", type=int, default=2)
    parser.add_argument("--language", choices=["fr", "en"], default="fr")
    parser.add_argument("--no-streaming", action="store_true")
    parser.add_argument("--contract", type=Path, help="a scene contract as JSON (e.g. an examiner scene)")
    parser.add_argument("--line", action="append", help="what the learner says, one per turn")
    args = parser.parse_args()
    contract = SceneContract.model_validate_json(args.contract.read_text()) if args.contract else None
    language = contract.language if contract else args.language
    result = asyncio.run(run(args.turns, language, not args.no_streaming, contract, args.line))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
