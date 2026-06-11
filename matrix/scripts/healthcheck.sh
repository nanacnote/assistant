#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f ".env" ]]; then
  echo "Missing matrix/.env. Copy .env.example and fill required values."
  exit 1
fi

# shellcheck disable=SC1091
source .env

MATRIX_PUBLIC_BASEURL="${MATRIX_PUBLIC_BASEURL:-https://$MATRIX_DOMAIN}"
MATRIX_DISCOVERY_URL="https://$MATRIX_DOMAIN"
curl_args=("-fsS")

if [[ -z "${MATRIX_ACME_EMAIL:-}" ]]; then
  # Local or early bootstrap flow may still be on the temporary self-signed certificate.
  curl_args+=("-k")
fi

check() {
  local name="$1"
  local url="$2"
  local response

  set +e
  response=$(curl "${curl_args[@]}" "$url" 2>/dev/null)
  local exit_code=$?
  set -e

  if [[ $exit_code -ne 0 ]]; then
    echo "FAIL: $name ($url)"
    exit 1
  fi

  echo "OK: $name"
  echo "$response" | head -c 200 > /dev/null
}

check "client versions" "$MATRIX_PUBLIC_BASEURL/_matrix/client/versions"
check "well-known client" "$MATRIX_DISCOVERY_URL/.well-known/matrix/client"
check "well-known server" "$MATRIX_DISCOVERY_URL/.well-known/matrix/server"

echo "All health checks passed."
