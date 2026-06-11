# Matrix Operator Utilities

Ad-hoc admin scripts for the Matrix homeserver. These are run manually by an operator, not by Docker or the bootstrap flow.

## Prerequisites

All scripts import from the `assistant` package. Activate the project virtual environment from the repository root before running any of them:

```bash
source .venv/bin/activate
```

All scripts read credentials from `matrix/.env`. Ensure `MATRIX_DOMAIN`, `MATRIX_ADMIN_PASSWORD`, and `MATRIX_ASSISTANT_PASSWORD` are set there.

## Scripts

### create_matrix_room.py

Creates a private Matrix room and adds named users to it (admin and assistant by default).

```bash
python matrix/scripts/ops/create_matrix_room.py
```

For local dev with self-signed TLS bypassed by direct HTTP:

```bash
python matrix/scripts/ops/create_matrix_room.py --base-url http://localhost:8008
```

Additional users can be invited with repeated `--user` flags. Auth is read from `matrix/.env`:

| User | Password env var |
|------|------------------|
| Admin | `MATRIX_ADMIN_PASSWORD` |
| Assistant | `MATRIX_ASSISTANT_PASSWORD` |
| Extra | `MATRIX_USER_<LOCALPART>_PASSWORD` |

The homeserver URL is derived from `MATRIX_PUBLIC_BASEURL` or `MATRIX_DOMAIN` in `matrix/.env`.

By default the script uses a stable alias localpart (`default`) so repeated runs reuse the same room when it already exists.

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--base-url` | env-derived | Matrix client API URL |
| `--room-name` | `Default` | Room display name |
| `--topic` | (empty) | Room topic |
| `--user` | (none) | Extra user localparts to invite (repeatable) |
| `--room-alias-localpart` | `default` | Stable room alias localpart to create/reuse |
| `--insecure` | off | Skip TLS verification for HTTPS homeservers |

### redact_matrix_room.py

Redacts all `m.room.message` events in a Matrix room. Useful for clearing test or setup noise before a room goes into production use.

```bash
# Dry-run — prints what would be redacted without making changes
python matrix/scripts/ops/redact_matrix_room.py --room-id '!<id>:<domain>'

# Confirm and perform redactions
python matrix/scripts/ops/redact_matrix_room.py --room-id '!<id>:<domain>' --confirm
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--room-id` | `$ASSISTANT_MATRIX_ROOM_ID` | Target room ID |
| `--confirm` | off | Actually perform redactions |
| `--batch-size` | 50 | Events per page |
| `--max-pages` | 0 (no limit) | Stop after N pages |

Messages sent by `@admin:<MATRIX_DOMAIN>` are excluded from redaction. If `MATRIX_DOMAIN` is not set in the env, no sender filter is applied.

### delete_matrix_room.py

Deletes a room through Synapse admin APIs. This is destructive and intended for operator-led cleanup or decommissioning.

```bash
# Dry-run — fetches and prints room metadata plus delete settings
python matrix/scripts/ops/delete_matrix_room.py --room-id '!<id>:<domain>'

# Confirm and execute room delete
python matrix/scripts/ops/delete_matrix_room.py --room-id '!<id>:<domain>' --confirm
```

Auth is read from `matrix/.env` — logs in as admin using `MATRIX_ADMIN_PASSWORD`.

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--room-id` | `$ASSISTANT_MATRIX_ROOM_ID` | Target room ID |
| `--confirm` | off | Actually execute deletion |
| `--block/--no-block` | block | Block future joins |
| `--purge/--no-purge` | purge | Purge room history |
| `--force-purge` | off | Force purge when members still exist |
| `--reason` | `Room deleted by operator` | Audit reason for room shutdown |
| `--request-timeout-seconds` | 30.0 | HTTP timeout per request |

### get_sync_token.py

Fetches the assistant account's current Matrix sync stream position (`next_batch`) and optionally writes it into the env file as `ASSISTANT_MATRIX_INITIAL_SYNC_TOKEN`.

Normally you do not need this — the assistant performs a fast priming sync on startup and skips historical messages automatically. Use this script when you want to pin the assistant to a specific point, for example after restoring from a database backup or when handing over to a replacement host.

```bash
# Print the current token
python matrix/scripts/ops/get_sync_token.py

# Write it directly into matrix/.env
python matrix/scripts/ops/get_sync_token.py --write-env
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--write-env` | off | Update `ASSISTANT_MATRIX_INITIAL_SYNC_TOKEN` in `matrix/.env` in place |
| `--insecure` | off | Skip TLS verification for HTTPS homeservers |
