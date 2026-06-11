"""Pluggable interfaces for memory persistence."""

from __future__ import annotations

import logging
import time
from typing import Protocol

from assistant.memory.models import ConversationMessage, MemoryFact, ProcedureMemory

logger = logging.getLogger(__name__)


class MemoryStorageNotConfiguredError(RuntimeError):
    """Raised when memory tools are used without a storage backend."""


class MemoryRepository(Protocol):
    """Persistence boundary for memory operations."""

    def store_message(self, message: ConversationMessage) -> None: ...

    def get_history(self, conversation_id: str, limit: int) -> list[ConversationMessage]: ...

    def prune_conversation(self, conversation_id: str, keep_limit: int) -> int: ...

    def store_fact(self, fact: MemoryFact) -> None: ...

    def search_facts(self, user_id: str, query: str, limit: int) -> list[MemoryFact]: ...

    def touch_fact(self, fact_id: str) -> None: ...

    def count_facts(self, user_id: str) -> int: ...

    def prune_old_facts(self, user_id: str, max_facts: int) -> int: ...

    def decay_importance(self, days_threshold: int, factor: float) -> int: ...

    def store_procedure(self, procedure: ProcedureMemory) -> None: ...

    def search_procedures(self, user_id: str, query: str, limit: int) -> list[ProcedureMemory]: ...

    def get_procedure(self, procedure_id: str) -> ProcedureMemory | None: ...

    def touch_procedure(self, procedure_id: str) -> None: ...

    def record_procedure_execution(self, procedure_id: str, success: bool) -> None: ...

    def count_procedures(self, user_id: str) -> int: ...

    def prune_old_procedures(self, user_id: str, max_procedures: int) -> int: ...

    def decay_procedure_importance(self, days_threshold: int, factor: float) -> int: ...


class UnconfiguredMemoryRepository:
    """Placeholder repository until a storage backend is supplied."""

    def _raise(self) -> None:
        raise MemoryStorageNotConfiguredError(
            "Memory storage is not configured. Set ASSISTANT_DB_DSN to enable "
            "conversational memory."
        )

    def store_message(self, message: ConversationMessage) -> None:
        self._raise()

    def get_history(self, conversation_id: str, limit: int) -> list[ConversationMessage]:
        self._raise()

    def prune_conversation(self, conversation_id: str, keep_limit: int) -> int:
        self._raise()

    def store_fact(self, fact: MemoryFact) -> None:
        self._raise()

    def search_facts(self, user_id: str, query: str, limit: int) -> list[MemoryFact]:
        self._raise()

    def touch_fact(self, fact_id: str) -> None:
        self._raise()

    def count_facts(self, user_id: str) -> int:
        self._raise()

    def prune_old_facts(self, user_id: str, max_facts: int) -> int:
        self._raise()

    def decay_importance(self, days_threshold: int, factor: float) -> int:
        self._raise()

    def store_procedure(self, procedure: ProcedureMemory) -> None:
        self._raise()

    def search_procedures(self, user_id: str, query: str, limit: int) -> list[ProcedureMemory]:
        self._raise()

    def get_procedure(self, procedure_id: str) -> ProcedureMemory | None:
        self._raise()

    def touch_procedure(self, procedure_id: str) -> None:
        self._raise()

    def record_procedure_execution(self, procedure_id: str, success: bool) -> None:
        self._raise()

    def count_procedures(self, user_id: str) -> int:
        self._raise()

    def prune_old_procedures(self, user_id: str, max_procedures: int) -> int:
        self._raise()

    def decay_procedure_importance(self, days_threshold: int, factor: float) -> int:
        self._raise()


def build_memory_repository() -> MemoryRepository:
    """Build the memory repository backed by the assistant PostgreSQL database."""
    from assistant.memory.repository import PostgresMemoryRepository
    from assistant.storage import get_db_dsn, get_shared_connection, run_migrations

    if not get_db_dsn():
        return UnconfiguredMemoryRepository()

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            conn = get_shared_connection()
            run_migrations(conn)
            return PostgresMemoryRepository(conn)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Memory repository connection attempt %d/3 failed: %s",
                attempt + 1,
                exc,
            )
            if attempt < 2:
                time.sleep(2)
    raise last_exc  # type: ignore[misc]
