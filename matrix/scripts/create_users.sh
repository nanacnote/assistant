#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: docker"
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo "Missing matrix/.env. Copy .env.example and fill required values."
  exit 1
fi

# shellcheck disable=SC1091
source .env

required_vars=(
  MATRIX_DOMAIN
  MATRIX_ADMIN_PASSWORD
  MATRIX_ASSISTANT_PASSWORD
)

for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "Missing required variable: $var"
    exit 1
  fi
done

docker compose \
  --project-directory "$COMPOSE_ROOT" \
  --env-file "$ROOT_DIR/.env" \
  up matrix-users

"$ROOT_DIR/scripts/prefill-assistant-env.sh"

echo "Done. Assistant handoff file: matrix/runtime/assistant.env"
