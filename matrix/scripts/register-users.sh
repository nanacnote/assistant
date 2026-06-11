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
required_var MATRIX_ADMIN_PASSWORD
required_var MATRIX_ASSISTANT_PASSWORD

MATRIX_SERVER_NAME="${MATRIX_SERVER_NAME:-$MATRIX_DOMAIN}"
MATRIX_PUBLIC_BASEURL="${MATRIX_PUBLIC_BASEURL:-https://$MATRIX_DOMAIN}"
MATRIX_ADMIN_LOCALPART="${MATRIX_ADMIN_LOCALPART:-admin}"
MATRIX_ASSISTANT_LOCALPART="${MATRIX_ASSISTANT_LOCALPART:-assistant}"
MATRIX_ASSISTANT_DEVICE_ID="${MATRIX_ASSISTANT_DEVICE_ID:-assistant}"

wait_for_synapse() {
  retries=45
  while [ "$retries" -gt 0 ]; do
    if python -c "import urllib.request; urllib.request.urlopen('http://synapse:8008/_matrix/client/versions', timeout=3)" >/dev/null 2>&1; then
      return 0
    fi
    retries=$((retries - 1))
    sleep 2
  done
  return 1
}

register_user() {
  localpart="$1"
  password="$2"
  admin_flag="$3"

  set +e
  output=$(register_new_matrix_user \
    --config /data/homeserver.yaml \
    --user "$localpart" \
    --password "$password" \
    "$admin_flag" \
    http://synapse:8008 2>&1)
  exit_code=$?
  set -e

  if [ "$exit_code" -ne 0 ]; then
    if echo "$output" | grep -qi "already taken"; then
      echo "User @$localpart:$MATRIX_SERVER_NAME already exists, continuing."
      return 0
    fi
    echo "$output"
    return "$exit_code"
  fi

  echo "Created user @$localpart:$MATRIX_SERVER_NAME"
}

if ! wait_for_synapse; then
  echo "Synapse did not become ready in time."
  exit 1
fi

register_user "$MATRIX_ADMIN_LOCALPART" "$MATRIX_ADMIN_PASSWORD" --admin
register_user "$MATRIX_ASSISTANT_LOCALPART" "$MATRIX_ASSISTANT_PASSWORD" --no-admin

mkdir -p /runtime
cat > /runtime/assistant.env <<EOF
ASSISTANT_MATRIX_HOMESERVER_URL=$MATRIX_PUBLIC_BASEURL
ASSISTANT_MATRIX_USER_ID=@$MATRIX_ASSISTANT_LOCALPART:$MATRIX_SERVER_NAME
ASSISTANT_MATRIX_PASSWORD=$MATRIX_ASSISTANT_PASSWORD
ASSISTANT_MATRIX_DEVICE_ID=$MATRIX_ASSISTANT_DEVICE_ID
EOF

echo "Wrote assistant handoff values to matrix/runtime/assistant.env"
