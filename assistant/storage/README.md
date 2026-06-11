# storage

Database infrastructure for the assistant runtime. Provides PostgreSQL connection management and schema migrations.

## What it does

- **Connection management** -- Thread-safe shared connection singleton (`get_shared_connection`) used by all repositories. Also provides `open_connection()` for standalone connections.
- **Schema migrations** -- `run_migrations()` creates all required tables and indexes on startup using `CREATE TABLE IF NOT EXISTS`.

## Tables managed

| Table | Used by |
|---|---|
| `calendar_events` | `builtin_tools/calendar/` |
| `wellbeing_checkins` | `builtin_tools/wellbeing/` |
| `wellbeing_state_logs` | `builtin_tools/wellbeing/` |
| `wellbeing_preferences` | `builtin_tools/wellbeing/` |
| `conversation_messages` | `memory/` |
| `memory_facts` | `memory/` |
| `procedure_memories` | `memory/` |

## Structure

| File | Role |
|---|---|
| `connection.py` | `get_db_dsn()` reads `ASSISTANT_DB_DSN` from env; `open_connection()` creates a psycopg connection; `get_shared_connection()` is a thread-safe singleton |
| `migrations.py` | `run_migrations()` executes DDL for all tables and indexes |

## How it fits

All repositories (memory, calendar, wellbeing) share a single PostgreSQL connection via `get_shared_connection()`. Migrations are run at startup before the runtime begins processing messages. The DSN is configured via the `ASSISTANT_DB_DSN` environment variable.
