# Assistant

An assistant runtime powered by Beacon and Keel, built to run against a real Matrix homeserver and a real LLM API.

## What It Does

- Beacon receives events and turns messages into LLM requests.
- Keel handles tool-calling and self-correction.
- The assistant runtime bridges Beacon requests into Keel responses and re-injects them back into Beacon.

## Complete Quickstart

Use this path if you want the full system up and running from scratch.

1. Copy the assistant and Matrix env templates:

```bash
cp .env.example .env
cp matrix/.env.example matrix/.env
```

2. Fill in `matrix/.env` with your domain, TLS email, passwords, and secrets.

3. Fill in root `.env` with your required LLM settings:

- `ASSISTANT_LLM_API_URL`
- `ASSISTANT_LLM_API_KEY`
- `ASSISTANT_LLM_MODEL`

4. Start the full stack from the repository root:

```bash
bash ./scripts/stack-up.sh
```

This runs a preflight check on both env files and then starts Matrix, the bootstrap cert flow, and the assistant container together.

5. Provision the Matrix users and sync assistant Matrix values into root `.env`:

```bash
cd matrix && ./scripts/create_users.sh
```

6. Verify the stack:

```bash
cd matrix && ./scripts/healthcheck.sh
```

At this point the assistant container should be running against Matrix. If you need to regenerate assistant Matrix settings later, rerun `cd matrix && ./scripts/create_users.sh`.

For local dev testing without public ACME, you can leave `MATRIX_ACME_EMAIL` blank and use the temporary bootstrap certificate. The healthcheck script will tolerate that self-signed cert.

For browser-based Matrix testing on the same machine, the compose stack also includes Element Web at `http://localhost:8081`. It is preconfigured from your Matrix env, so you can sign in with the users created by `cd matrix && ./scripts/create_users.sh`.

## Local Development

If you want to run the assistant directly on your machine instead of in Docker:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
assistant --check-config
```

The CLI loads values from `.env` automatically when present.

## Configuration

Matrix authentication can use `ASSISTANT_MATRIX_ACCESS_TOKEN` or `ASSISTANT_MATRIX_PASSWORD`.

Optional settings:

- `ASSISTANT_LLM_SYSTEM_PROMPT`
- `ASSISTANT_LLM_TEMPERATURE`
- `ASSISTANT_LLM_REQUEST_TIMEOUT_SECONDS`
- `ASSISTANT_MATRIX_SYNC_TIMEOUT_MS`
- `ASSISTANT_MATRIX_REQUEST_TIMEOUT_SECONDS`
- `ASSISTANT_EVENT_WORKERS`
- `ASSISTANT_QUEUE_SIZE`
- `ASSISTANT_LOG_LEVEL`
- `ASSISTANT_ERROR_REPLY`
- `ASSISTANT_TOOL_MODULES` (defaults to `assistant.builtin_tools`; extend with comma-separated custom modules)
- `ASSISTANT_DB_DSN` (PostgreSQL DSN; auto-provided in Docker Compose)

## Builtin Tools

Default builtin tools include:

- Reply tool for final assistant responses.
- Calendar manager tools for event workflows.
- Wellbeing coaching tools for short wake/mid/sleep check-ins, state logs, history retrieval, and trend insights.

## Run The Assistant

```bash
assistant
```

## Bootstrap Matrix Server

For the Matrix homeserver and assistant bootstrap flow, see [`matrix/README.md`](matrix/README.md). It covers the full stack startup, certificate automation, user provisioning, and operator workflow without duplicating the main quickstart above.

## Project Layout

- `assistant/runtime.py` wires Beacon, Matrix, and Keel together.
- `assistant/matrix.py` polls Matrix events and sends replies.
- `assistant/llm.py` calls an OpenAI-compatible chat completions API.
- `assistant/grounding.py` builds temporal and identity context for LLM prompts.
- `assistant/builtin_tools/` provides default builtin plugins (Reply, Calendar, Wellbeing).
- `assistant/tools.py` loads tool modules dynamically.
- `assistant/main.py` validates configuration and starts the runtime.
- `scripts/preflight-stack.sh` checks all required env values and runtime prerequisites before stack startup.
- `scripts/stack-up.sh` runs preflight, creates required data directories, and starts the full Docker Compose stack. Use this for both local dev and production.

## Dependencies

The project currently pins Beacon and Keel from their Git repositories in `pyproject.toml`.
