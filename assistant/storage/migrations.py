"""Schema migrations for the assistant PostgreSQL database.

All migrations use CREATE ... IF NOT EXISTS so they are safe to run on every
startup — no version tracking is required while the schema is still pre-1.0.
"""

from __future__ import annotations

import logging

from psycopg import Connection

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calendar_events (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL DEFAULT '',
    title                   TEXT NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    start_time              TIMESTAMPTZ NOT NULL,
    end_time                TIMESTAMPTZ NOT NULL,
    timezone                TEXT NOT NULL DEFAULT 'UTC',
    category                TEXT NOT NULL DEFAULT 'general',
    attendees               JSONB NOT NULL DEFAULT '[]'::jsonb,
    recurrence              JSONB,
    reminder_minutes_before INTEGER,
    created_at              TIMESTAMPTZ NOT NULL,
    updated_at              TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_calendar_events_start_time
    ON calendar_events (start_time);

CREATE INDEX IF NOT EXISTS idx_calendar_events_category
    ON calendar_events (category);

CREATE INDEX IF NOT EXISTS idx_calendar_events_user
    ON calendar_events (user_id);

CREATE TABLE IF NOT EXISTS wellbeing_checkins (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    session_type TEXT NOT NULL,
    answers      JSONB NOT NULL DEFAULT '{}'::jsonb,
    reflection   TEXT NOT NULL DEFAULT '',
    mood         INTEGER NOT NULL,
    energy       INTEGER NOT NULL,
    stress       INTEGER NOT NULL,
    emotions     JSONB NOT NULL DEFAULT '[]'::jsonb,
    note         TEXT NOT NULL DEFAULT '',
    captured_at  TIMESTAMPTZ NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wellbeing_checkins_user_captured
    ON wellbeing_checkins (user_id, captured_at);

CREATE TABLE IF NOT EXISTS wellbeing_state_logs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    context     TEXT NOT NULL DEFAULT 'mid',
    mood        INTEGER NOT NULL,
    energy      INTEGER NOT NULL,
    stress      INTEGER NOT NULL,
    emotions    JSONB NOT NULL DEFAULT '[]'::jsonb,
    note        TEXT NOT NULL DEFAULT '',
    captured_at TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wellbeing_state_logs_user_captured
    ON wellbeing_state_logs (user_id, captured_at);

CREATE TABLE IF NOT EXISTS wellbeing_preferences (
    user_id                  TEXT PRIMARY KEY,
    checkin_cadence          JSONB NOT NULL DEFAULT '["wake","mid","sleep"]'::jsonb,
    focus_areas              JSONB NOT NULL DEFAULT '[]'::jsonb,
    tone                     TEXT NOT NULL DEFAULT 'reflective',
    crisis_guidance_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at               TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    actor_id        TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_messages_lookup
    ON conversation_messages (conversation_id, created_at DESC);

CREATE TABLE IF NOT EXISTS memory_facts (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    fact_text       TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'general',
    importance      REAL NOT NULL DEFAULT 0.5,
    source_conv_id  TEXT NOT NULL DEFAULT '',
    access_count    INTEGER NOT NULL DEFAULT 0,
    last_accessed   TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_facts_user_importance
    ON memory_facts (user_id, importance DESC, last_accessed DESC);

CREATE INDEX IF NOT EXISTS idx_memory_facts_fts
    ON memory_facts USING GIN (to_tsvector('english', fact_text));

CREATE TABLE IF NOT EXISTS procedure_memories (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    description     TEXT NOT NULL,
    steps           JSONB NOT NULL DEFAULT '[]'::jsonb,
    category        TEXT NOT NULL DEFAULT 'general',
    importance      REAL NOT NULL DEFAULT 0.5,
    source_conv_id  TEXT NOT NULL DEFAULT '',
    execution_count INTEGER NOT NULL DEFAULT 0,
    success_count   INTEGER NOT NULL DEFAULT 0,
    access_count    INTEGER NOT NULL DEFAULT 0,
    last_accessed   TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_procedure_memories_user
    ON procedure_memories (user_id, importance DESC, last_accessed DESC);

CREATE INDEX IF NOT EXISTS idx_procedure_memories_fts
    ON procedure_memories USING GIN (to_tsvector('english', description));

CREATE TABLE IF NOT EXISTS pending_questions (
    id              TEXT PRIMARY KEY,
    room_id         TEXT NOT NULL,
    thread_root     TEXT NOT NULL DEFAULT '',
    question        TEXT NOT NULL,
    original_prompt TEXT NOT NULL,
    tool_history    JSONB NOT NULL DEFAULT '[]'::jsonb,
    request_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pending_questions_room_thread
    ON pending_questions (room_id, thread_root);
"""


def run_migrations(conn: Connection) -> None:
    logger.debug("running database migrations")
    with conn.cursor() as cur:
        cur.execute(_SCHEMA)
    conn.commit()
    logger.debug("database migrations complete")
