#!/usr/bin/env bash
set -euo pipefail

MATRIX_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$MATRIX_DIR/.." && pwd)"
COMPOSE_ROOT="$REPO_ROOT"
ASSISTANT_ENV_FILE="$REPO_ROOT/.env"
MATRIX_ENV_FILE="$MATRIX_DIR/.env"
RUNTIME_ENV_FILE="$MATRIX_DIR/runtime/assistant.env"

if [[ ! -f "$MATRIX_ENV_FILE" ]]; then
  echo "Missing matrix/.env. Create it from matrix/.env.example first."
  exit 1
fi

# shellcheck disable=SC1091
source "$MATRIX_ENV_FILE"

MATRIX_SERVER_NAME="${MATRIX_SERVER_NAME:-$MATRIX_DOMAIN}"
MATRIX_PUBLIC_BASEURL="${MATRIX_PUBLIC_BASEURL:-https://$MATRIX_DOMAIN}"
MATRIX_ASSISTANT_LOCALPART="${MATRIX_ASSISTANT_LOCALPART:-assistant}"
MATRIX_ASSISTANT_DEVICE_ID="${MATRIX_ASSISTANT_DEVICE_ID:-assistant}"

required_vars=(
  MATRIX_DOMAIN
  MATRIX_ASSISTANT_PASSWORD
)

for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "Missing required variable in matrix/.env: $var"
    exit 1
  fi
done

if [[ ! -f "$ASSISTANT_ENV_FILE" ]]; then
  cp "$REPO_ROOT/.env.example" "$ASSISTANT_ENV_FILE"
fi

if [[ -f "$RUNTIME_ENV_FILE" ]]; then
  # shellcheck disable=SC1091
  source "$RUNTIME_ENV_FILE"
fi

ASSISTANT_MATRIX_HOMESERVER_URL="${ASSISTANT_MATRIX_HOMESERVER_URL:-$MATRIX_PUBLIC_BASEURL}"
ASSISTANT_MATRIX_USER_ID="${ASSISTANT_MATRIX_USER_ID:-@$MATRIX_ASSISTANT_LOCALPART:$MATRIX_SERVER_NAME}"
ASSISTANT_MATRIX_PASSWORD="${ASSISTANT_MATRIX_PASSWORD:-$MATRIX_ASSISTANT_PASSWORD}"
ASSISTANT_MATRIX_DEVICE_ID="${ASSISTANT_MATRIX_DEVICE_ID:-$MATRIX_ASSISTANT_DEVICE_ID}"

BEGIN_MARK="# BEGIN MANAGED BY matrix/scripts/prefill-assistant-env.sh"
END_MARK="# END MANAGED BY matrix/scripts/prefill-assistant-env.sh"

TMP_FILE="$(mktemp)"

awk -v begin="$BEGIN_MARK" -v end="$END_MARK" '
  $0 == begin {skip=1; next}
  $0 == end {skip=0; next}
  !skip {print}
' "$ASSISTANT_ENV_FILE" > "$TMP_FILE"

cat >> "$TMP_FILE" <<EOF

$BEGIN_MARK
# Managed by the Matrix bootstrap flow; these values are safe to regenerate.
ASSISTANT_MATRIX_HOMESERVER_URL=$ASSISTANT_MATRIX_HOMESERVER_URL
ASSISTANT_MATRIX_USER_ID=$ASSISTANT_MATRIX_USER_ID
ASSISTANT_MATRIX_PASSWORD=$ASSISTANT_MATRIX_PASSWORD
ASSISTANT_MATRIX_DEVICE_ID=$ASSISTANT_MATRIX_DEVICE_ID
ASSISTANT_MATRIX_ACCESS_TOKEN=
$END_MARK
EOF

mv "$TMP_FILE" "$ASSISTANT_ENV_FILE"

if command -v docker >/dev/null 2>&1; then
  docker compose \
    --project-directory "$COMPOSE_ROOT" \
    --env-file "$MATRIX_ENV_FILE" \
    up -d --force-recreate assistant >/dev/null
fi

echo "Updated $ASSISTANT_ENV_FILE with managed assistant Matrix values."
