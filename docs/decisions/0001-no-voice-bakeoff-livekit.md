# 0001: No voice bake-off; LiveKit is the transport

- **Date:** 2026-10-14
- **Status:** accepted (founder decision)
- **Supersedes:** SPEC §2 "Voice transport" row and §4.2

## Decision

The founder removed the Phase 0 voice bake-off. The transport is **LiveKit** (self-hosted `livekit-server`, Apache-2.0), used through the
`livekit` Python RTC SDK, with our own cascaded pipeline (STT → Actor → Contract Guard → TTS) rather than the LiveKit Agents
pipeline, so every NPC sentence passes the Guard before audio exists.

## Why LiveKit over the alternatives (without measurements)

- Meets every §4.2 hard constraint: cascaded (we own the pipeline), providers swappable, self-hostable, Apache-2.0,
  Expo SDK (`@livekit/react-native`) for iOS/Android plus a JS SDK for web.
- WebRTC gives on-device echo cancellation, a jitter buffer and loss recovery. Those are exactly the metrics (§4.2 echo, 4G)
  that a plain WebSocket transport handles badly.
- Simupatient candidate A was disqualified by the audit (OpenAI Realtime S2S; TTS not swappable; not self-hostable).

## Consequences

- `VoiceTransport` keeps two implementations: `LiveKitTransport` (production) and `LoopbackTransport` (tests, evals, CI).
  Both pass the same contract test suite.
- `tools/voicebench/` stays, as a latency/regression harness (SPEC §20 `latency` suite) rather than a bake-off.
- Turn-taking (§6.2) is implemented by us on top of a pluggable VAD, not delegated to the transport.
