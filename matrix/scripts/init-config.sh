#!/bin/sh
set -eu

required_var() {
  var_name="$1"
  eval var_value="\${$var_name:-}"
  if [ -z "$var_value" ]; then
    echo "Missing required variable: $var_name"
    exit 1
  fi
}

required_var MATRIX_DOMAIN
required_var POSTGRES_DB
required_var POSTGRES_USER
required_var POSTGRES_PASSWORD
required_var SYNAPSE_REGISTRATION_SHARED_SECRET

MATRIX_SERVER_NAME="${MATRIX_SERVER_NAME:-$MATRIX_DOMAIN}"
MATRIX_PUBLIC_BASEURL="${MATRIX_PUBLIC_BASEURL:-https://$MATRIX_DOMAIN}"
MATRIX_CLIENT_BASEURL="${MATRIX_CLIENT_BASEURL:-$MATRIX_PUBLIC_BASEURL}"
SYNAPSE_REPORT_STATS="${SYNAPSE_REPORT_STATS:-no}"
MATRIX_FEDERATION_ENABLED="${MATRIX_FEDERATION_ENABLED:-false}"
SYNAPSE_ALLOW_UNSAFE_LOCALE="${SYNAPSE_ALLOW_UNSAFE_LOCALE:-true}"

is_local_domain=false
case "$MATRIX_DOMAIN" in
  localhost|127.0.0.1)
    is_local_domain=true
    ;;
esac

if [ "${MATRIX_PUBLIC_BASEURL#https://}" = "$MATRIX_PUBLIC_BASEURL" ]; then
  if [ "$is_local_domain" = true ] && [ "${MATRIX_PUBLIC_BASEURL#http://}" != "$MATRIX_PUBLIC_BASEURL" ]; then
    :
  else
    echo "MATRIX_PUBLIC_BASEURL must start with https:// (http:// is allowed only for localhost local-dev)"
    exit 1
  fi
fi

mkdir -p /data /runtime/nginx /runtime/element

if [ ! -f /data/homeserver.yaml ]; then
  echo "Generating initial Synapse config"
  python -m synapse.app.homeserver \
    --server-name "$MATRIX_SERVER_NAME" \
    --config-path /data/homeserver.yaml \
    --generate-config \
    --report-stats "$SYNAPSE_REPORT_STATS"
fi

LOG_CONFIG_PATH="/data/${MATRIX_SERVER_NAME}.log.config"
if [ -f "$LOG_CONFIG_PATH" ]; then
  # Use stdout logging in containers to keep log delivery consistent across restarts.
  cat > "$LOG_CONFIG_PATH" <<'EOF'
version: 1

formatters:
  precise:
    format: '%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(request)s - %(message)s'

handlers:
  console:
    class: logging.StreamHandler
    formatter: precise

loggers:
  synapse.storage.SQL:
    level: INFO

root:
  level: INFO
  handlers: [console]

disable_existing_loggers: false
EOF
fi

extract_yaml_value() {
  key="$1"
  file="$2"
  if [ ! -f "$file" ]; then
    return 0
  fi
  sed -n "s/^${key}:[[:space:]]*\"\{0,1\}\([^\" ]*\)\"\{0,1\}$/\1/p" "$file" | head -n1
}

random_hex() {
  python - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
}

escape_sed_replacement() {
  # Escape characters that are special in sed replacement strings.
  # This keeps randomly generated secrets safe for template substitution.
  printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'
}

EXISTING_MACAROON="$(extract_yaml_value macaroon_secret_key /data/homeserver.yaml || true)"
EXISTING_FORM="$(extract_yaml_value form_secret /data/homeserver.yaml || true)"

is_placeholder_token() {
  value="$1"
  printf '%s' "$value" | grep -Eq '__[A-Z0-9_]+__'
}

if [ -n "$EXISTING_MACAROON" ] && is_placeholder_token "$EXISTING_MACAROON"; then
  EXISTING_MACAROON=""
fi

if [ -n "$EXISTING_FORM" ] && is_placeholder_token "$EXISTING_FORM"; then
  EXISTING_FORM=""
fi

MACAROON_SECRET_KEY="${EXISTING_MACAROON:-$(random_hex)}"
FORM_SECRET="${EXISTING_FORM:-$(random_hex)}"

ESC_MATRIX_SERVER_NAME="$(escape_sed_replacement "$MATRIX_SERVER_NAME")"
ESC_MATRIX_PUBLIC_BASEURL="$(escape_sed_replacement "$MATRIX_PUBLIC_BASEURL")"
ESC_MATRIX_CLIENT_BASEURL="$(escape_sed_replacement "$MATRIX_CLIENT_BASEURL")"
ESC_POSTGRES_DB="$(escape_sed_replacement "$POSTGRES_DB")"
ESC_POSTGRES_USER="$(escape_sed_replacement "$POSTGRES_USER")"
ESC_POSTGRES_PASSWORD="$(escape_sed_replacement "$POSTGRES_PASSWORD")"
ESC_SYNAPSE_REGISTRATION_SHARED_SECRET="$(escape_sed_replacement "$SYNAPSE_REGISTRATION_SHARED_SECRET")"
ESC_SYNAPSE_REPORT_STATS="$(escape_sed_replacement "$SYNAPSE_REPORT_STATS")"
ESC_SYNAPSE_ALLOW_UNSAFE_LOCALE="$(escape_sed_replacement "$SYNAPSE_ALLOW_UNSAFE_LOCALE")"
ESC_MATRIX_FEDERATION_ENABLED="$(escape_sed_replacement "$MATRIX_FEDERATION_ENABLED")"
ESC_MACAROON_SECRET_KEY="$(escape_sed_replacement "$MACAROON_SECRET_KEY")"
ESC_FORM_SECRET="$(escape_sed_replacement "$FORM_SECRET")"
ESC_MATRIX_DOMAIN="$(escape_sed_replacement "$MATRIX_DOMAIN")"

sed \
  -e "s|__MATRIX_SERVER_NAME__|$ESC_MATRIX_SERVER_NAME|g" \
  -e "s|__MATRIX_PUBLIC_BASEURL__|$ESC_MATRIX_PUBLIC_BASEURL|g" \
  -e "s|__POSTGRES_DB__|$ESC_POSTGRES_DB|g" \
  -e "s|__POSTGRES_USER__|$ESC_POSTGRES_USER|g" \
  -e "s|__POSTGRES_PASSWORD__|$ESC_POSTGRES_PASSWORD|g" \
  -e "s|__SYNAPSE_REGISTRATION_SHARED_SECRET__|$ESC_SYNAPSE_REGISTRATION_SHARED_SECRET|g" \
  -e "s|__SYNAPSE_REPORT_STATS__|$ESC_SYNAPSE_REPORT_STATS|g" \
  -e "s|__SYNAPSE_ALLOW_UNSAFE_LOCALE__|$ESC_SYNAPSE_ALLOW_UNSAFE_LOCALE|g" \
  -e "s|__MATRIX_FEDERATION_ENABLED__|$ESC_MATRIX_FEDERATION_ENABLED|g" \
  -e "s|__MACAROON_SECRET_KEY__|$ESC_MACAROON_SECRET_KEY|g" \
  -e "s|__FORM_SECRET__|$ESC_FORM_SECRET|g" \
  /templates/homeserver.yaml.template > /data/homeserver.yaml

sed -e "s|__MATRIX_DOMAIN__|$ESC_MATRIX_DOMAIN|g" \
  /templates/matrix.conf.template > /runtime/nginx/matrix.conf

sed \
  -e "s|__MATRIX_CLIENT_BASEURL__|$ESC_MATRIX_CLIENT_BASEURL|g" \
  -e "s|__MATRIX_SERVER_NAME__|$ESC_MATRIX_SERVER_NAME|g" \
  /templates/element.config.json.template > /runtime/element/config.json

cat > /runtime/nginx/client-well-known.json <<EOF
{"m.homeserver": {"base_url": "$MATRIX_CLIENT_BASEURL"}}
EOF

cat > /runtime/nginx/server-well-known.json <<EOF
{"m.server": "$MATRIX_DOMAIN:443"}
EOF

if grep -Eq '__[A-Z0-9_]+__' /data/homeserver.yaml \
  || grep -Eq '__[A-Z0-9_]+__' /runtime/nginx/matrix.conf \
  || grep -Eq '__[A-Z0-9_]+__' /runtime/element/config.json; then
  echo "Config rendering left unresolved placeholders"
  exit 1
fi

echo "Matrix init completed"
