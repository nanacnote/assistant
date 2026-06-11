"""PostgreSQL implementation of PendingQuestionRepository."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from psycopg import Connection

from assistant.interaction.ports import PendingQuestion


class PostgresPendingQuestionRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def _rollback_on_error(self) -> None:
        try:
            self._conn.rollback()
        except Exception:
            pass

    def save(self, q: PendingQuestion) -> None:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pending_questions
                        (id, room_id, thread_root, question, original_prompt,
                         tool_history, request_metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        q["id"],
                        q["room_id"],
                        q["thread_root"],
                        q["question"],
                        q["original_prompt"],
                        json.dumps(q["tool_history"]),
                        json.dumps(q["request_metadata"]),
                        q["created_at"],
                    ),
                )
            self._conn.commit()
        except Exception:
            self._rollback_on_error()
            raise

    def find_by_room_thread(self, room_id: str, thread_root: str) -> PendingQuestion | None:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, room_id, thread_root, question, original_prompt,
                           tool_history, request_metadata, created_at
                    FROM pending_questions
                    WHERE room_id = %s AND thread_root = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (room_id, thread_root),
                )
                row = cur.fetchone()
            if row is None:
                return None
            return PendingQuestion(
                id=row["id"],
                room_id=row["room_id"],
                thread_root=row["thread_root"],
                question=row["question"],
                original_prompt=row["original_prompt"],
                tool_history=[tuple(step) for step in row["tool_history"]],
                request_metadata=dict(row["request_metadata"]),
                created_at=_to_datetime(row["created_at"]),
            )
        except Exception:
            self._rollback_on_error()
            raise

    def delete(self, question_id: str) -> None:
        try:
            with self._conn.cursor() as cur:
                cur.execute("DELETE FROM pending_questions WHERE id = %s", (question_id,))
            self._conn.commit()
        except Exception:
            self._rollback_on_error()
            raise

    def delete_expired(self, ttl_seconds: int) -> int:
        try:
            from datetime import timedelta

            cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
            with self._conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM pending_questions WHERE created_at < %s",
                    (cutoff,),
                )
                deleted = cur.rowcount
            self._conn.commit()
            return deleted
        except Exception:
            self._rollback_on_error()
            raise


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
