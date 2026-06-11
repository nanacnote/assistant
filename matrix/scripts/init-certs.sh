#!/bin/sh
set -eu

. /scripts/common-certs.sh

if [ -z "${MATRIX_ACME_EMAIL:-}" ]; then
  echo "MATRIX_ACME_EMAIL is not set; keeping the temporary self-signed certificate in place."
  tail -f /dev/null
fi

DOMAIN="$(cert_domain)"
FULLCHAIN="/certs/fullchain.pem"
PRIVKEY="/certs/privkey.pem"
WEBROOT="/var/www/certbot"
LE_DIR="/etc/letsencrypt/live/$DOMAIN"

mkdir -p "$WEBROOT"

request_cert() {
  certbot certonly \
    --webroot \
    --webroot-path "$WEBROOT" \
    --non-interactive \
    --agree-tos \
    --email "$MATRIX_ACME_EMAIL" \
    -d "$DOMAIN"
}

copy_cert() {
  if [ -f "$LE_DIR/fullchain.pem" ] && [ -f "$LE_DIR/privkey.pem" ]; then
    cp "$LE_DIR/fullchain.pem" "$FULLCHAIN"
    cp "$LE_DIR/privkey.pem" "$PRIVKEY"
  fi
}

wait_for_challenge_server() {
  count=60
  while [ "$count" -gt 0 ]; do
    if python -c "import urllib.request; urllib.request.urlopen('http://nginx/.well-known/matrix/client', timeout=3)" >/dev/null 2>&1; then
      return 0
    fi
    count=$((count - 1))
    sleep 2
  done
  return 1
}

if ! wait_for_challenge_server; then
  echo "Nginx did not become ready in time for certificate issuance."
  tail -f /dev/null
fi

if [ ! -f "$FULLCHAIN" ] || [ ! -f "$PRIVKEY" ]; then
  echo "No certificate found, requesting an initial Let's Encrypt certificate for $DOMAIN"
  request_cert || true
  copy_cert || true
fi

if [ ! -f "$FULLCHAIN" ] || [ ! -f "$PRIVKEY" ]; then
  echo "Let's Encrypt issuance did not complete yet; waiting for DNS/TLS prerequisites."
fi

while true; do
  certbot renew --webroot --webroot-path "$WEBROOT" || true
  copy_cert || true
  sleep 12h
done
