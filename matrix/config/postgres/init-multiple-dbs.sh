#!/bin/sh
set -eu

if [ -n "${ASSISTANT_TOOLS_DB:-}" ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE ${ASSISTANT_TOOLS_DB};
EOSQL
fi
