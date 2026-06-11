#!/bin/sh
set -eu

. /scripts/common-certs.sh

DOMAIN="$(cert_domain)"
FULLCHAIN="/certs/fullchain.pem"
PRIVKEY="/certs/privkey.pem"

mkdir -p /certs

if [ -f "$FULLCHAIN" ] && [ -f "$PRIVKEY" ]; then
  echo "Certificate files already exist for $DOMAIN"
  exit 0
fi

python - <<'PY'
from pathlib import Path
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import os

cert_path = Path('/certs/fullchain.pem')
key_path = Path('/certs/privkey.pem')
domain = os.environ['MATRIX_DOMAIN']

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
now = datetime.now(timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=1))
    .not_valid_after(now + timedelta(days=7))
    .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
    .sign(key, hashes.SHA256())
)
key_path.write_bytes(
    key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
)
cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
PY

echo "Generated temporary bootstrap certificate for $DOMAIN"
