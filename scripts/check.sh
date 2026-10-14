#!/usr/bin/env bash
# Local equivalent of CI's python job: lint, format, strict types, tests.
set -euo pipefail
cd "$(dirname "$0")/.."
PACKAGES=(lingard_contracts lingard_llm agent_memory lingard_curriculum lingard_exam_packs lingard_economy lingard_world lingard_storage lingard_db
          lingard_telemetry lingard_api lingard_live lingard_graphs lingard_pronunciation)
uv run ruff check .
uv run ruff format --check .
uv run mypy $(printf -- '-p %s ' "${PACKAGES[@]}") -p evals
uv run pytest "$@"
