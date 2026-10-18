# Running Lingard on an iPhone

Live scenes use LiveKit's native WebRTC module, which Expo Go doesn't include. On a phone, Lingard therefore runs as a
**development build** (our own Expo Go with the native modules built in). This Mac has no Xcode, so builds run on EAS,
Expo's cloud build service (decision 0013).

## One-time setup (founder)

These steps need your Expo and Apple Developer accounts, so they can't be automated from here.

```bash
npm install -g eas-cli
cd apps/mobile
eas login
eas init                    # links the project and writes extra.eas.projectId into app.json (commit that)
eas device:create           # registers your iPhone for internal builds (open the link on the phone)
eas build --profile development --platform ios
```

Install the build from the link or QR code EAS prints. On the phone, turn on **Settings → Privacy & Security →
Developer Mode** the first time.

## Each session: point the phone at your Mac

The phone and the Mac must be on the same Wi-Fi. Find the Mac's address with `ipconfig getifaddr en0`.

```bash
# API, listening on the network rather than loopback only
uv run uvicorn lingard_api.main:app --host 0.0.0.0 --port 58000

# LiveKit must advertise the LAN address in its ICE candidates, or the phone's audio never connects
LIVEKIT_NODE_IP=192.168.x.y docker compose up -d livekit

# Workers as usual
uv run python -m lingard_live.worker
uv run python -m lingard_graphs.worker

# Metro for the development build
cd apps/mobile && npx expo start --dev-client
```

Open the development build and pick the Mac's server. You don't need to change any app config: in development the app
rewrites `localhost` in the API URL and in the LiveKit ticket to the address Metro is served from
(`src/config.ts`, `reachable`). iOS asks once for local-network access; allow it.

## TestFlight / App Store

A store build can't reach your Mac. Before running `eas build --profile production`, you need:

- the API deployed over HTTPS, with its address set for the build: `eas env:create --name EXPO_PUBLIC_API_URL --value https://…`;
- LiveKit reachable over `wss://`, with `LIVEKIT_PUBLIC_URL` set on the API to that address;
- `eas submit --platform ios` to upload, plus App Store Connect metadata (privacy labels: microphone audio, used for app
  functionality, linked to the user).

What's already configured in `app.json`: bundle id `app.lingard`, microphone, Face ID and camera purpose strings (WebRTC
links camera APIs even though Lingard never uses them), background audio for live scenes,
`ITSAppUsesNonExemptEncryption: false` (HTTPS only), a light-only interface, and local-network ATS for development.
