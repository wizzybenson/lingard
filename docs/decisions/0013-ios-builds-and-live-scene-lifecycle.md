# 0013: iOS through EAS development builds; one LiveKit room per scene screen

- **Date:** 2026-10-18
- **Status:** accepted (reversible)

## Context

The founder asked for the new errors to be fixed, the app to be ready for iOS, and the UI to feel seamless.

The Expo dev log held about 290,000 lines, almost all from one evening:

- **LiveKit loop.** Room `scene-c07b8fec…` stayed alive for 10 h 45 min (2026-10-15 21:13 to 2026-10-16 07:58) with
  2,419 participant joins. The server log shows two joins with the same identity 200 ms apart. LiveKit evicts the older
  one (`DUPLICATE_IDENTITY`), its client reconnects and evicts the newer one, and so on. `useLiveScene` only stored the
  room after `connect` and the mic publish had both succeeded, so neither the Leave button nor unmounting the screen
  could disconnect a room that was still joining. The double join came from the start button, which had no busy state
  until the ticket request returned (four sessions were also planned within 12 s that evening, from the same unguarded
  button on the City screen).
- **CanvasKit aborts** (`Aborted()` ×16,392, `null function` ×1,192, `table index is out of bounds` ×2). These are wasm
  traps in the Reanimated frame loop that drives the map's idle animation. They began during the LiveKit loop. Once
  CanvasKit trapped, every frame threw again. The map also rebuilt its skyline `SkPath`s in wasm on every render (a new
  `size` object each time) and kept animating while its tab was hidden.
- `expo-doctor` failed 3 of 21 checks. The two that would break a native build: `expo-font` and `expo-asset` were
  missing (the app would crash outside Expo Go), and the Android icon path pointed at a file that doesn't exist.

## Decision

- `useLiveScene` keeps at most one room: a second `connect` while one is joining is ignored, the room is tracked from
  the moment it's created, and leaving or unmounting always disconnects it. A join has a 20 s limit, and an eviction by
  a duplicate identity ends the scene with an explanation instead of reconnecting. The ticket is fetched inside
  `connect`, so "Connecting…" shows straight away. Tests: `src/__tests__/live.test.ts`.
- The skyline is plain SVG path text (`world/model.ts: skyline`), memoised on a stable size. The idle animation runs
  only while the City tab is focused. The map pans horizontally only, so vertical drags scroll the page on a phone.
- iOS builds go through EAS (no Xcode on the dev Mac): `eas.json` defines development, simulator, preview and
  production profiles, and `expo-dev-client` is installed. `docs/ios.md` covers the steps that need the founder's
  accounts.
- In development on a phone, loopback API and LiveKit URLs are rewritten to the host Metro serves from
  (`config.ts: reachable`). LiveKit's `--node-ip` comes from `LIVEKIT_NODE_IP` (default `127.0.0.1`).
- The interface is light-only (`userInterfaceStyle: light`, dark status bar). The palette has no dark variant, and
  "automatic" gave white status-bar text on the paper background in iOS dark mode. A dark theme is future work.

## Not verified here

- No iOS build has run: that needs the founder's Expo and Apple accounts. `expo prebuild --platform ios` succeeds in a
  scratch copy, and the generated Info.plist carries the purpose strings, background audio and ATS settings.
- No live scene was run after the fix (paid providers). The hook's join, double-tap and timeout behaviour is covered by
  unit tests with a fake `Room`.
- The CanvasKit aborts weren't reproduced on a clean load. The fixes remove the per-render wasm allocations and the
  background animation, but don't prove the traps can't recur.
