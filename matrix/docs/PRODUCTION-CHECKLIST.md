# Production Checklist

Use this checklist before exposing your homeserver publicly.

## Security baseline

- Use real TLS certificates from a trusted CA.
- Keep `enable_registration` disabled in Synapse config.
- Use long random secrets for database and registration shared secret.
- Restrict host firewall to ports 80/443 and required SSH management ports.
- Keep Docker and host OS updated.

## Operations

- Define backup retention for `matrix/data/postgres` and `matrix/data/synapse`.
- Test restore process at least once before production cutover.
- Configure log shipping and alerting for container failures.
- Document on-call and incident recovery steps.

## Matrix posture

- Keep federation disabled unless you explicitly need public federation.
- Create dedicated admin and assistant accounts; do not share credentials.
- Rotate assistant credentials regularly and update project `.env`.
