#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ASSISTANT_ENV_FILE="$ROOT_DIR/.env"
MATRIX_ENV_FILE="$ROOT_DIR/matrix/.env"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed or not on PATH."
  exit 1
fi

if [[ ! -f "$ASSISTANT_ENV_FILE" ]]; then
  echo "Missing $ASSISTANT_ENV_FILE. Copy .env.example to .env first."
  exit 1
fi

if [[ ! -f "$MATRIX_ENV_FILE" ]]; then
  echo "Missing $MATRIX_ENV_FILE. Copy matrix/.env.example to matrix/.env first."
  exit 1
fi

# shellcheck disable=SC1090
source "$ASSISTANT_ENV_FILE"
# shellcheck disable=SC1090
source "$MATRIX_ENV_FILE"

required_assistant_vars=(
  ASSISTANT_LLM_API_URL
  ASSISTANT_LLM_API_KEY
  ASSISTANT_LLM_MODEL
)

required_matrix_vars=(
  MATRIX_DOMAIN
  POSTGRES_DB
  POSTGRES_USER
  POSTGRES_PASSWORD
  SYNAPSE_REGISTRATION_SHARED_SECRET
  MATRIX_ADMIN_PASSWORD
  MATRIX_ASSISTANT_PASSWORD
)

MATRIX_PUBLIC_BASEURL="${MATRIX_PUBLIC_BASEURL:-https://${MATRIX_DOMAIN:-}}"
is_local_domain=false
case "$MATRIX_DOMAIN" in
  localhost|127.0.0.1)
    is_local_domain=true
    ;;
esac

if [[ "$MATRIX_PUBLIC_BASEURL" != https://* ]]; then
  if [[ "$is_local_domain" == true && "$MATRIX_PUBLIC_BASEURL" == http://* ]]; then
    :
  else
    echo "MATRIX_PUBLIC_BASEURL must start with https:// (http:// is allowed only for localhost local-dev)"
    exit 1
  fi
fi

missing=0

for var in "${required_assistant_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "Missing required assistant setting: $var"
    missing=1
  fi
done

for var in "${required_matrix_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "Missing required matrix setting: $var"
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "Preflight failed. Fill the missing values before starting the stack."
  exit 1
fi

if [[ -z "${MATRIX_ACME_EMAIL:-}" ]]; then
  echo "Warning: MATRIX_ACME_EMAIL is not set. The stack will remain on the temporary bootstrap certificate."
fi

echo "Preflight passed. Safe next step: bash ./scripts/stack-up.sh"
