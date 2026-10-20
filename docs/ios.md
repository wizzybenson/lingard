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

## UI tests (Maestro)

`apps/mobile/e2e/` holds Maestro flows. `tour.yaml` signs in, then visits every tab, the Studio and the goal screen,
taking a screenshot at each stop. They sign in as the shared local test learner (`LINGARD_TEST_NAME` and
`LINGARD_TEST_PIN` in `.env`, which is gitignored; reset with `python -m lingard_api.cli reset-pin --name Ernest`).

```bash
# Homebrew wants newer Command Line Tools for maestro, so both live in ~/.local/share/lingard-tools:
#   Temurin JDK 17 (api.adoptium.net) in jdk/, maestro.zip (GitHub releases) in maestro/
export JAVA_HOME=~/.local/share/lingard-tools/jdk/Contents/Home
export PATH=$JAVA_HOME/bin:~/.local/share/lingard-tools/maestro/bin:$PATH
apps/mobile/e2e/run.sh            # or: run.sh sign-in.yaml
```

Screenshots land in `~/.maestro/tests/<timestamp>/`.

## A real iPhone

Lingard needs its own development build: **Expo Go can't run it**, because live conversations use LiveKit's native
WebRTC module, which Expo Go doesn't include. The development build works like Expo Go (it loads JavaScript from Metro
and reloads on save) but contains LiveKit.

Once per phone (and again every 7 days with a free Apple ID):

1. Plug the iPhone into the Mac, unlock it and tap **Trust**.
2. On the phone: **Settings → Privacy & Security → Developer Mode** → on (it restarts).
3. In Xcode: **Settings → Accounts** → add your Apple ID (the build is signed with your personal team).
4. Build and install:
   ```bash
   cd apps/mobile && npx expo run:ios --device
   ```
5. On the phone: **Settings → General → VPN & Device Management** → trust your developer certificate.

Each test session (phone and Mac on the same Wi-Fi):

```bash
./tools/tester_session.sh        # services on the LAN address, LiveKit announcing it, migrations, seed, Metro
./tools/tester_session.sh stop   # stops the API, workers and pronunciation service
```

Open Lingard on the phone. The first time, it asks for local-network access; allow it. In development the app rewrites
`localhost` in the API URL and in the LiveKit ticket to the address Metro is served from (`src/config.ts`,
`reachable`), so nothing else needs configuring.

For someone else's phone, use TestFlight (Apple Developer Program): archive and upload from Xcode. That build needs an
API reachable from the internet, not the Mac's LAN.

## Release builds

`eas.json` has profiles for the day a hosted build is wanted. Locally, an archive is made with Xcode
(Product → Archive) once the API is deployed over HTTPS and `EXPO_PUBLIC_API_URL` points to it.

What's already configured in `app.json`: bundle id `app.lingard`, microphone, Face ID and camera purpose strings (WebRTC
links camera APIs even though Lingard never uses them), background audio for live scenes,
`ITSAppUsesNonExemptEncryption: false`, a light-only interface, and local-network ATS for development.
