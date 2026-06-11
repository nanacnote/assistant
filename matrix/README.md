# Matrix Bootstrap Module

This module bootstraps and operates a self-hosted Matrix homeserver for the assistant and Element mobile clients.

## What It Provides

- Single-instance Synapse deployment using Docker Compose.
- Nginx reverse proxy with TLS termination and Element discovery endpoints.
- Automated certificate bootstrap plus Let’s Encrypt renewal.
- Assistant user provisioning and root `.env` prefill.
- Federation disabled by default.

This is production-capable with hardening steps in [docs/PRODUCTION-CHECKLIST.md](docs/PRODUCTION-CHECKLIST.md).

## Prerequisites

- A domain name you control, pointing to this host.
- Port 80 and 443 reachable from the internet.
- A valid contact email for ACME certificate issuance.
- Docker and Docker Compose installed.

For local dev testing, the ACME email can be left blank and the stack will stay on the temporary bootstrap certificate.

## Files You Configure

- [`.env`](.env) in this directory
- TLS certificate files under `matrix/certs/` are handled automatically by the bootstrap flow

The first boot uses a temporary certificate so the stack can start immediately. Let’s Encrypt renewal takes over once DNS and port reachability are correct.

## First Boot

1. Copy the environment template:

```bash
cd matrix
cp .env.example .env
```

2. Fill in the required values in `.env`:

- `MATRIX_DOMAIN`
- `MATRIX_ACME_EMAIL`
- `POSTGRES_PASSWORD`
- `SYNAPSE_REGISTRATION_SHARED_SECRET`
- `MATRIX_ADMIN_PASSWORD`
- `MATRIX_ASSISTANT_PASSWORD`

Make sure the repository root `.env` also contains:

- `ASSISTANT_LLM_API_URL`
- `ASSISTANT_LLM_API_KEY`
- `ASSISTANT_LLM_MODEL`

3. Start the full stack from the repository root:

```bash
cd ..
bash ./scripts/stack-up.sh
```

This runs a preflight check on both env files and then starts the init container, temporary cert bootstrap, Synapse, Nginx, cert renewal, and the assistant container together.

4. Provision the Matrix users and sync assistant Matrix values into the root `.env`:

```bash
cd matrix
./scripts/create_users.sh
```

This also recreates the assistant container so the updated Matrix values are picked up immediately.

5. Check health:

```bash
./scripts/healthcheck.sh
```

6. Inspect the generated assistant handoff values:

```bash
cat runtime/assistant.env
```

## Later Restarts

Restart the stack from the repository root with:

```bash
bash ./scripts/stack-up.sh
```

If you change Matrix credentials or assistant login values, rerun `cd matrix && ./scripts/create_users.sh` to refresh the managed root `.env` block and recreate the assistant container.

## Operator Notes

- The assistant container reads environment at startup, so the prefill script recreates it after Matrix values change.
- If `MATRIX_ACME_EMAIL` is missing, the stack will stay on the bootstrap certificate and Let’s Encrypt will not take over.
- Federation remains disabled unless you explicitly enable it in configuration.

## Element Mobile

- Homeserver URL: `https://<MATRIX_DOMAIN>`
- Sign in with a created user (`@<localpart>:<MATRIX_SERVER_NAME>`).

## Element Web For Local Dev

- The compose stack now includes an Element Web container for same-machine testing.
- URL: `http://localhost:8081`
- It uses generated runtime config from your Matrix env and automatically falls back to `MATRIX_PUBLIC_BASEURL`.
- Set `MATRIX_CLIENT_BASEURL` only when you want Element Web to use a different API endpoint.
- If the homeserver picker entry for `localhost` does not connect, use **Other homeserver** and enter `http://localhost:8008` directly.
- The picker flow relies on `https://localhost/.well-known/...`, and browsers reject the bootstrap self-signed cert by default.
- During sign-in, Element may show **Confirm your digital identity** for secure messaging setup. For local dev this is optional, so choose **Skip for now**.
- Sign in with users created by `./scripts/create_users.sh`.

## Assistant Integration

`runtime/assistant.env` includes:

- `ASSISTANT_MATRIX_HOMESERVER_URL`
- `ASSISTANT_MATRIX_USER_ID`
- `ASSISTANT_MATRIX_PASSWORD`
- `ASSISTANT_MATRIX_DEVICE_ID`

Use password login first, then rotate to access token after initial provisioning if desired.
