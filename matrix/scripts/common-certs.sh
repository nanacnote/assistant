#!/bin/sh
set -eu

cert_paths() {
  echo "/certs/fullchain.pem /certs/privkey.pem"
}

cert_domain() {
  echo "${MATRIX_DOMAIN:?MATRIX_DOMAIN is required}"
}
