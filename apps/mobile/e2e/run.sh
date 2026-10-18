#!/usr/bin/env bash
# Run a Maestro flow on the booted iOS Simulator: ./e2e/run.sh [flow.yaml]  (default: tour.yaml)
# Needs Maestro and Java 17 (docs/ios.md). The test learner's name and PIN come from the repo's .env.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
set -a; source "$here/../../../.env"; set +a
export MAESTRO_LINGARD_TEST_NAME="$LINGARD_TEST_NAME" MAESTRO_LINGARD_TEST_PIN="$LINGARD_TEST_PIN"
export MAESTRO_CLI_NO_ANALYTICS=1 DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
exec maestro test "$here/${1:-tour.yaml}"
