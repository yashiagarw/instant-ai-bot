#!/bin/sh
# The whole test command (Phase 5.4): backend tests and lint, frontend unit tests and lint, then dependency and
# container scanning. Playwright and the ZAP scan are separate (they need servers): README "Phase 5.4".
#   pnpm test:all
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT/backend" && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
cd "$ROOT" && pnpm lint && pnpm test
sh "$ROOT/scripts/security-scan.sh"
