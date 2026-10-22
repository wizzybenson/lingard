#!/usr/bin/env bash
# Everything a phone on the same Wi-Fi needs to use Lingard fully, voice included: ./tools/tester_session.sh
#
# Starts Postgres, Redis, object storage and LiveKit (announcing this Mac's LAN address, so a phone's WebRTC can reach
# it), migrates and seeds, then runs the API on the LAN, both workers, the pronunciation service and Metro for the
# Lingard development build. The phone runs that build (docs/ios.md, "A real iPhone"), not Expo Go: Expo Go has no
# LiveKit. Ctrl-C stops Metro; ./tools/tester_session.sh stop stops the rest.
#
# The API is reachable by anyone on this network while it runs: use a network you trust.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
logs="${TMPDIR:-/tmp}/lingard-session"
mkdir -p "$logs"
cd "$root"

stop() {
  pkill -f "uvicorn lingard_api.main" || true
  pkill -f "lingard_graphs.worker" || true
  pkill -f "lingard_live.worker" || true
  pkill -f "lingard_pronunciation.server" || true
}

if [[ "${1:-}" == "stop" ]]; then
  stop
  echo "Stopped the API, workers and pronunciation service (Docker services keep running: docker compose stop)."
  exit 0
fi

ip="${LINGARD_LAN_IP:-$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || true)}"
if [[ -z "$ip" ]]; then
  echo "No Wi-Fi address found. Join a network, or set LINGARD_LAN_IP." >&2
  exit 1
fi

echo "› Services for $ip"
LIVEKIT_NODE_IP="$ip" docker compose up -d postgres redis objects livekit
uv run python -m lingard_api.cli migrate
uv run python -m lingard_api.cli seed

stop
# A clean environment: the services read .env themselves (a shell that exported it would mangle JSON values).
run() { env -i HOME="$HOME" PATH="$PATH" TMPDIR="${TMPDIR:-/tmp}" "$@"; }
run nohup uv run uvicorn lingard_api.main:app --host 0.0.0.0 --port 58000 >"$logs/api.log" 2>&1 &
run nohup uv run python -m lingard_graphs.worker >"$logs/graphs.log" 2>&1 &
run nohup uv run python -m lingard_live.worker >"$logs/live.log" 2>&1 &
if [[ -e /opt/homebrew/lib/libespeak-ng.dylib ]]; then
  run PHONEMIZER_ESPEAK_LIBRARY=/opt/homebrew/lib/libespeak-ng.dylib nohup uv run uvicorn --factory \
    lingard_pronunciation.server:build_app --port 58100 >"$logs/pronunciation.log" 2>&1 &
else
  echo "  (no espeak-ng: Accent Studio scoring is off; brew install espeak-ng to turn it on)"
fi

for _ in $(seq 1 30); do
  curl -sf -o /dev/null "http://$ip:58000/openapi.json" && break
  sleep 1
done
curl -sf -o /dev/null "http://$ip:58000/openapi.json" || { echo "The API did not start: see $logs/api.log" >&2; exit 1; }
# Melody-drill models are rendered and checked before anyone needs them (a first take otherwise waits for them).
if [[ -e /opt/homebrew/lib/libespeak-ng.dylib ]]; then
  run nohup uv run python -m lingard_api.cli warm-studio >"$logs/warm-studio.log" 2>&1 &
fi
echo "› API on http://$ip:58000, LiveKit on ws://$ip:57880, logs in $logs"
echo "› Open the Lingard app on the phone (same Wi-Fi). It finds this Mac through Metro below."
cd apps/mobile
if [[ -d /Applications/Xcode.app ]]; then export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"; fi
# The phone must reach this Mac over Wi-Fi. A phone on the USB cable would otherwise find Metro over the cable's
# private 169.254.x link, then send every API call there too, and that link drops whenever it likes (2026-10-22: "could
# not connect to the server" after Begin day). Pinning the address keeps Metro, the API and LiveKit on the Wi-Fi.
export REACT_NATIVE_PACKAGER_HOSTNAME="$ip"
exec npx expo start --dev-client
