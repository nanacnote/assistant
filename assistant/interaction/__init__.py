"""Interaction module for pending question persistence."""

from __future__ import annotations

from assistant.interaction.ports import PendingQuestion, PendingQuestionRepository
from assistant.interaction.repository import PostgresPendingQuestionRepository

__all__ = [
    "PendingQuestion",
    "PendingQuestionRepository",
    "PostgresPendingQuestionRepository",
    "UnconfiguredPendingQuestionRepository",
    "build_pending_question_repository",
]


class UnconfiguredPendingQuestionRepository:
    """Placeholder repository until a shared storage backend is supplied."""

    def _raise(self) -> None:
        raise RuntimeError(
            "Pending question storage is not configured yet. "
            "Set the DATABASE_URL environment variable to enable AskUser persistence."
        )

    def save(self, q: PendingQuestion) -> None:
        self._raise()

    def find_by_room_thread(
        self, room_id: str, thread_root: str
    ) -> PendingQuestion | None:
        self._raise()

    def delete(self, question_id: str) -> None:
        self._raise()

    def delete_expired(self, ttl_seconds: int) -> int:
        self._raise()


def build_pending_question_repository() -> PendingQuestionRepository:
    """Build the pending question repository backed by the assistant PostgreSQL database."""
    from assistant.storage import get_db_dsn, get_shared_connection, run_migrations

    if not get_db_dsn():
        return UnconfiguredPendingQuestionRepository()

    conn = get_shared_connection()
    run_migrations(conn)
    return PostgresPendingQuestionRepository(conn)
