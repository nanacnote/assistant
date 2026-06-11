#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

bash "$ROOT_DIR/scripts/preflight-stack.sh"

cd "$ROOT_DIR"
mkdir -p matrix/data/synapse matrix/data/postgres matrix/runtime/nginx matrix/certs

docker compose --env-file matrix/.env up -d "$@"
