# Running Lingard on iOS

Live scenes use LiveKit's native WebRTC module, which Expo Go doesn't include, so Lingard runs as a **development
build**: our own app with the native modules compiled in. It builds locally with Xcode (decision 0013).

## Requirements (one time)

- Xcode (26.4 here) with the iOS platform: `xcodebuild -downloadPlatform iOS` (about 8.5 GB).
- CocoaPods: `brew install cocoapods`.
- If `xcode-select -p` prints `/Library/Developer/CommandLineTools`, either run
  `sudo xcode-select -s /Applications/Xcode.app` once, or prefix the commands below with
  `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`.

## Simulator

The Simulator shares the Mac's network, so `localhost` works for the API and LiveKit unchanged.

```bash
cd apps/mobile
npx expo prebuild --platform ios          # generates ios/ (gitignored) and installs the pods
npx expo run:ios                          # builds, installs, boots a Simulator, starts Metro
```

Without `expo run`, the equivalent by hand:

```bash
cd apps/mobile/ios
xcodebuild -workspace Lingard.xcworkspace -scheme Lingard -configuration Debug -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath build CODE_SIGN_IDENTITY=- build
xcrun simctl install booted build/Build/Products/Debug-iphonesimulator/Lingard.app
xcrun simctl launch booted app.lingard     # finds Metro on :8081 by itself
```

Keep code signing on (`CODE_SIGN_IDENTITY=-`, ad hoc, no Apple account needed). A build with
`CODE_SIGNING_ALLOWED=NO` has no keychain access, so SecureStore fails and the saved session can't be read.

Rerun `npx expo prebuild --platform ios` after changing `app.json` or adding a native package. JavaScript changes
only need Metro.

## A real iPhone

Plug it in, trust the Mac, and turn on **Settings → Privacy & Security → Developer Mode**. Signing for a device needs
your Apple ID in Xcode (Settings → Accounts), because the build is signed with your personal team:

```bash
npx expo run:ios --device
```

The phone reaches the Mac over Wi-Fi, so run the services on the LAN address (`ipconfig getifaddr en0`):

```bash
uv run uvicorn lingard_api.main:app --host 0.0.0.0 --port 58000
LIVEKIT_NODE_IP=192.168.x.y docker compose up -d livekit   # ICE candidates must carry an address the phone can reach
```

In development the app rewrites `localhost` in the API URL and in the LiveKit ticket to the address Metro is served from
(`src/config.ts`, `reachable`). iOS asks once for local-network access; allow it.

## Release builds

`eas.json` has profiles for the day a hosted build is wanted. Locally, an archive is made with Xcode
(Product → Archive) once the API is deployed over HTTPS and `EXPO_PUBLIC_API_URL` points to it.

What's already configured in `app.json`: bundle id `app.lingard`, microphone, Face ID and camera purpose strings (WebRTC
links camera APIs even though Lingard never uses them), background audio for live scenes,
`ITSAppUsesNonExemptEncryption: false`, a light-only interface, and local-network ATS for development.
