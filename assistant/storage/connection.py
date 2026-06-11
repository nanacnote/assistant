"""PostgreSQL connection factory for the assistant storage layer."""

from __future__ import annotations

import logging
import os
from threading import Lock

from psycopg import Connection, connect
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

_DEFAULT_DB_DSN = ""
_connection_lock = Lock()
_shared_connection: Connection | None = None


def get_db_dsn() -> str:
    return os.getenv("ASSISTANT_DB_DSN", _DEFAULT_DB_DSN).strip()


def open_connection(dsn: str | None = None) -> Connection:
    resolved_dsn = (dsn if dsn is not None else get_db_dsn()).strip()
    if not resolved_dsn:
        raise ValueError("ASSISTANT_DB_DSN is required for PostgreSQL storage.")
    logger.debug("opening database connection")
    conn = connect(resolved_dsn, row_factory=dict_row, connect_timeout=10)
    conn.autocommit = False
    logger.debug("database connection established")
    return conn


def get_shared_connection() -> Connection:
    global _shared_connection
    with _connection_lock:
        if _shared_connection is None or _shared_connection.closed:
            logger.debug("shared connection unavailable, creating new connection")
            _shared_connection = open_connection()
        else:
            logger.debug("reusing existing shared connection")
        return _shared_connection
