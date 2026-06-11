# Troubleshooting

## Assistant cannot login

- Confirm `ASSISTANT_MATRIX_HOMESERVER_URL` matches `MATRIX_PUBLIC_BASEURL` in `matrix/.env` or the managed root `.env` block.
- Verify assistant user exists: run `cd matrix && ./scripts/create_users.sh` again.
- Check Synapse logs from the repository root: `docker compose --env-file matrix/.env logs synapse`.

## Element cannot discover homeserver

- Verify DNS for `MATRIX_DOMAIN` points to the server.
- Confirm `.well-known` endpoints respond:
  - `https://<domain>/.well-known/matrix/client`
  - `https://<domain>/.well-known/matrix/server`
- Verify nginx is healthy from the repository root: `docker compose --env-file matrix/.env ps`.
- Element Web is auto-configured from `MATRIX_PUBLIC_BASEURL`; set `MATRIX_CLIENT_BASEURL` only for a custom client endpoint.
- For local dev with `localhost` and bootstrap certs, choose **Other homeserver** in Element Web and enter `http://localhost:8008`.
- The `localhost` picker path uses HTTPS discovery and fails until the local cert is trusted by the browser.

## TLS errors

- Verify `MATRIX_ACME_EMAIL` is set in `matrix/.env`.
- Check that `matrix/certs/fullchain.pem` and `matrix/certs/privkey.pem` exist after bootstrap.
- Ensure certificate CN/SAN includes `MATRIX_DOMAIN`.
- Check nginx logs from the repository root: `docker compose --env-file matrix/.env logs nginx`.

## Synapse startup issues

- Confirm Postgres container is healthy first.
- Validate rendered config exists: `matrix/data/synapse/homeserver.yaml`.
- Check for template substitutions that left placeholders unresolved.
