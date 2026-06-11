"""PostgreSQL implementation of the memory repository."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from psycopg import Connection

from assistant.memory.models import ConversationMessage, MemoryFact, ProcedureMemory

logger = logging.getLogger(__name__)


class PostgresMemoryRepository:
    """Memory persistence backed by PostgreSQL."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def store_message(self, message: ConversationMessage) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_messages
                    (id, conversation_id, actor_id, role, content, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (message.id, message.conversation_id, message.actor_id,
                 message.role, message.content, message.created_at),
            )
        self._conn.commit()
        logger.debug(
            "stored message: id=%s conversation=%s role=%s",
            message.id, message.conversation_id, message.role,
        )

    def get_history(self, conversation_id: str, limit: int) -> list[ConversationMessage]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, conversation_id, actor_id, role, content, created_at
                FROM conversation_messages
                WHERE conversation_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()
        logger.debug(
            "get_history: conversation=%s limit=%d rows=%d",
            conversation_id, limit, len(rows),
        )
        return [
            ConversationMessage(
                id=row["id"],
                conversation_id=row["conversation_id"],
                actor_id=row["actor_id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        ]

    def prune_conversation(self, conversation_id: str, keep_limit: int) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM conversation_messages
                WHERE id IN (
                    SELECT id FROM conversation_messages
                    WHERE conversation_id = %s
                    ORDER BY created_at DESC
                    OFFSET %s
                )
                """,
                (conversation_id, keep_limit),
            )
            deleted = cur.rowcount
        self._conn.commit()
        if deleted:
            logger.debug("prune_conversation: conversation=%s deleted=%d", conversation_id, deleted)
        return deleted

    def store_fact(self, fact: MemoryFact) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memory_facts (id, user_id, fact_text, category, importance,
                                          source_conv_id, access_count, last_accessed, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (fact.id, fact.user_id, fact.fact_text, fact.category, fact.importance,
                 fact.source_conv_id, fact.access_count, fact.last_accessed, fact.created_at),
            )
        self._conn.commit()
        logger.debug("stored fact: id=%s user=%s category=%s", fact.id, fact.user_id, fact.category)

    def search_facts(self, user_id: str, query: str, limit: int) -> list[MemoryFact]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, fact_text, category, importance,
                       source_conv_id, access_count, last_accessed, created_at,
                       ts_rank(to_tsvector('english', fact_text),
                               plainto_tsquery('english', %s)) AS rank
                FROM memory_facts
                WHERE user_id = %s
                  AND to_tsvector('english', fact_text) @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC, importance DESC, last_accessed DESC
                LIMIT %s
                """,
                (query, user_id, query, limit),
            )
            rows = cur.fetchall()
        logger.debug(
            "search_facts: user=%s query_len=%d results=%d",
            user_id, len(query), len(rows),
        )
        return [
            MemoryFact(
                id=row["id"],
                user_id=row["user_id"],
                fact_text=row["fact_text"],
                category=row["category"],
                importance=row["importance"],
                source_conv_id=row["source_conv_id"],
                access_count=row["access_count"],
                last_accessed=row["last_accessed"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def touch_fact(self, fact_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE memory_facts
                SET access_count = access_count + 1, last_accessed = %s
                WHERE id = %s
                """,
                (datetime.now(timezone.utc), fact_id),
            )
        self._conn.commit()

    def count_facts(self, user_id: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM memory_facts WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        return row["cnt"] if row else 0

    def prune_old_facts(self, user_id: str, max_facts: int) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM memory_facts
                WHERE id IN (
                    SELECT id FROM memory_facts
                    WHERE user_id = %s
                    ORDER BY importance ASC, last_accessed ASC
                    OFFSET %s
                )
                """,
                (user_id, max_facts),
            )
            deleted = cur.rowcount
        self._conn.commit()
        if deleted:
            logger.debug("prune_old_facts: user=%s deleted=%d", user_id, deleted)
        return deleted

    def decay_importance(self, days_threshold: int, factor: float) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE memory_facts
                SET importance = importance * %s
                WHERE last_accessed < now() - make_interval(days => %s)
                  AND importance > 0.1
                """,
                (factor, days_threshold),
            )
            updated = cur.rowcount
        self._conn.commit()
        if updated:
            logger.debug(
                "decay_importance: updated=%d days_threshold=%d factor=%.2f",
                updated, days_threshold, factor,
            )
        return updated

    # ------------------------------------------------------------------
    # Procedure memory
    # ------------------------------------------------------------------

    def store_procedure(self, procedure: ProcedureMemory) -> None:
        import json as _json

        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO procedure_memories
                    (id, user_id, description, steps, category, importance,
                     source_conv_id, execution_count, success_count,
                     access_count, last_accessed, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (procedure.id, procedure.user_id, procedure.description,
                 _json.dumps(procedure.steps), procedure.category,
                 procedure.importance, procedure.source_conv_id,
                 procedure.execution_count, procedure.success_count,
                 procedure.access_count, procedure.last_accessed,
                 procedure.created_at),
            )
        self._conn.commit()
        logger.debug(
            "stored procedure: id=%s user=%s desc=%s",
            procedure.id, procedure.user_id, procedure.description[:60],
        )

    def search_procedures(self, user_id: str, query: str, limit: int) -> list[ProcedureMemory]:
        import json as _json

        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, description, steps, category, importance,
                       source_conv_id, execution_count, success_count,
                       access_count, last_accessed, created_at,
                       ts_rank(to_tsvector('english', description),
                               plainto_tsquery('english', %s)) AS rank
                FROM procedure_memories
                WHERE user_id = %s
                  AND to_tsvector('english', description) @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC, importance DESC, last_accessed DESC
                LIMIT %s
                """,
                (query, user_id, query, limit),
            )
            rows = cur.fetchall()
        logger.debug(
            "search_procedures: user=%s query_len=%d results=%d",
            user_id, len(query), len(rows),
        )
        return [
            ProcedureMemory(
                id=row["id"],
                user_id=row["user_id"],
                description=row["description"],
                steps=_json.loads(row["steps"]) if isinstance(row["steps"], str) else row["steps"],
                category=row["category"],
                importance=row["importance"],
                source_conv_id=row["source_conv_id"],
                execution_count=row["execution_count"],
                success_count=row["success_count"],
                access_count=row["access_count"],
                last_accessed=row["last_accessed"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_procedure(self, procedure_id: str) -> ProcedureMemory | None:
        import json as _json

        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, description, steps, category, importance,
                       source_conv_id, execution_count, success_count,
                       access_count, last_accessed, created_at
                FROM procedure_memories
                WHERE id = %s
                """,
                (procedure_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return ProcedureMemory(
            id=row["id"],
            user_id=row["user_id"],
            description=row["description"],
            steps=_json.loads(row["steps"]) if isinstance(row["steps"], str) else row["steps"],
            category=row["category"],
            importance=row["importance"],
            source_conv_id=row["source_conv_id"],
            execution_count=row["execution_count"],
            success_count=row["success_count"],
            access_count=row["access_count"],
            last_accessed=row["last_accessed"],
            created_at=row["created_at"],
        )

    def touch_procedure(self, procedure_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE procedure_memories
                SET access_count = access_count + 1, last_accessed = %s
                WHERE id = %s
                """,
                (datetime.now(timezone.utc), procedure_id),
            )
        self._conn.commit()

    def record_procedure_execution(self, procedure_id: str, success: bool) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE procedure_memories
                SET execution_count = execution_count + 1,
                    success_count = success_count + CASE WHEN %s THEN 1 ELSE 0 END
                WHERE id = %s
                """,
                (success, procedure_id),
            )
        self._conn.commit()

    def count_procedures(self, user_id: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM procedure_memories WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        return row["cnt"] if row else 0

    def prune_old_procedures(self, user_id: str, max_procedures: int) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM procedure_memories
                WHERE id IN (
                    SELECT id FROM procedure_memories
                    WHERE user_id = %s
                    ORDER BY importance ASC, last_accessed ASC
                    OFFSET %s
                )
                """,
                (user_id, max_procedures),
            )
            deleted = cur.rowcount
        self._conn.commit()
        if deleted:
            logger.debug("prune_old_procedures: user=%s deleted=%d", user_id, deleted)
        return deleted

    def decay_procedure_importance(self, days_threshold: int, factor: float) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE procedure_memories
                SET importance = importance * %s
                WHERE last_accessed < now() - make_interval(days => %s)
                  AND importance > 0.1
                """,
                (factor, days_threshold),
            )
            updated = cur.rowcount
        self._conn.commit()
        if updated:
            logger.debug(
                "decay_procedure_importance: updated=%d days_threshold=%d factor=%.2f",
                updated, days_threshold, factor,
            )
        return updated
