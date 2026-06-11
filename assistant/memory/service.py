"""Orchestration layer for conversational memory."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from assistant.grounding import build_grounding_context
from assistant.memory.extraction import extract_facts, extract_procedure, should_extract
from assistant.memory.models import ConversationMessage, MemoryFact, ProcedureMemory
from assistant.memory.ports import MemoryRepository

logger = logging.getLogger(__name__)


def _is_duplicate(new_text: str, existing_facts: list[MemoryFact]) -> bool:
    """Check if new_text is substantially similar to any existing fact."""
    new_words = set(new_text.lower().split())
    if not new_words:
        return False
    for fact in existing_facts:
        existing_words = set(fact.fact_text.lower().split())
        if not existing_words:
            continue
        overlap = len(new_words & existing_words) / min(len(new_words), len(existing_words))
        if overlap >= 0.7:
            return True
    return False


class MemoryService:
    """Orchestrates working memory, fact storage, and retrieval."""

    def __init__(
        self,
        repository: MemoryRepository,
        llm_complete: Callable[[list[dict[str, str]]], str] | None = None,
        working_memory_limit: int = 20,
        max_facts_per_user: int = 500,
        extraction_enabled: bool = True,
        max_procedures_per_user: int = 200,
        procedure_extraction_enabled: bool = True,
    ) -> None:
        self._repo = repository
        self._llm_complete = llm_complete
        self._working_memory_limit = working_memory_limit
        self._max_facts_per_user = max_facts_per_user
        self._extraction_enabled = extraction_enabled
        self._max_procedures_per_user = max_procedures_per_user
        self._procedure_extraction_enabled = procedure_extraction_enabled

    async def get_working_memory(self, conversation_id: str) -> list[dict[str, str]]:
        """Fetch recent messages formatted for the LLM context.

        Returns a list of {"role": ..., "content": ...} dicts in chronological order.
        """
        messages = await asyncio.to_thread(
            self._repo.get_history, conversation_id, self._working_memory_limit
        )
        return [{"role": m.role, "content": m.content} for m in messages]

    async def store_turn(
        self,
        conversation_id: str,
        actor_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Store both sides of a conversation turn and prune working memory."""
        now = datetime.now(timezone.utc)

        def _store() -> int:
            self._repo.store_message(
                ConversationMessage(
                    id=str(uuid4()),
                    conversation_id=conversation_id,
                    actor_id=actor_id,
                    role="user",
                    content=user_msg,
                    created_at=now,
                )
            )
            self._repo.store_message(
                ConversationMessage(
                    id=str(uuid4()),
                    conversation_id=conversation_id,
                    actor_id=actor_id,
                    role="assistant",
                    content=assistant_msg,
                    created_at=now,
                )
            )
            return self._repo.prune_conversation(conversation_id, self._working_memory_limit)

        deleted = await asyncio.to_thread(_store)
        if deleted:
            logger.debug("pruned %d old messages from conversation %s", deleted, conversation_id)

    async def get_relevant_memories(
        self, user_id: str, current_message: str, limit: int = 10
    ) -> list[str]:
        """Retrieve relevant long-term memories for the current message."""

        def _search() -> list[MemoryFact]:
            facts = self._repo.search_facts(user_id, current_message, limit)
            for f in facts:
                self._repo.touch_fact(f.id)
            return facts

        facts = await asyncio.to_thread(_search)
        return [f.fact_text for f in facts]

    async def extract_and_store_facts(
        self,
        user_id: str,
        conversation_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Extract facts from a conversation turn and store them.

        This is best-effort — failures are logged but not raised.
        """
        if not self._extraction_enabled or self._llm_complete is None:
            return
        if not should_extract(user_msg, assistant_msg):
            return

        extracted = extract_facts(
            self._llm_complete, user_msg, assistant_msg,
            grounding=build_grounding_context(actor_id=user_id),
        )
        if not extracted:
            return

        now = datetime.now(timezone.utc)

        def _store() -> int:
            for ef in extracted:
                existing = self._repo.search_facts(user_id, ef.text, limit=3)
                if _is_duplicate(ef.text, existing):
                    logger.debug("skipping duplicate fact: %s", ef.text)
                    continue
                self._repo.store_fact(
                    MemoryFact(
                        id=str(uuid4()),
                        user_id=user_id,
                        fact_text=ef.text,
                        category=ef.category,
                        importance=ef.importance,
                        source_conv_id=conversation_id,
                        access_count=0,
                        last_accessed=now,
                        created_at=now,
                    )
                )
                logger.info(
                    "stored memory fact: %s (category=%s, importance=%.2f)",
                    ef.text, ef.category, ef.importance,
                )
            return self._repo.prune_old_facts(user_id, self._max_facts_per_user)

        deleted = await asyncio.to_thread(_store)
        if deleted:
            logger.debug("pruned %d old facts for user %s", deleted, user_id)

    async def decay_stale_memories(self, days_threshold: int = 30, factor: float = 0.5) -> int:
        """Reduce importance of facts not accessed recently. Returns count updated."""
        return await asyncio.to_thread(self._repo.decay_importance, days_threshold, factor)

    async def get_relevant_procedures(
        self, user_id: str, current_message: str, limit: int = 5
    ) -> list[dict[str, object]]:
        """Retrieve relevant procedures for the current message.

        Returns a list of dicts with 'id', 'description', and 'steps' keys.
        Touches each retrieved procedure.
        """

        def _search() -> list[ProcedureMemory]:
            procs = self._repo.search_procedures(user_id, current_message, limit)
            for p in procs:
                self._repo.touch_procedure(p.id)
            return procs

        procs = await asyncio.to_thread(_search)
        return [
            {"id": p.id, "description": p.description, "steps": p.steps}
            for p in procs
        ]

    async def store_procedure(
        self,
        user_id: str,
        conversation_id: str,
        description: str,
        steps: list[str],
        category: str = "general",
        importance: float = 0.5,
    ) -> ProcedureMemory:
        """Store a procedure and prune if over the per-user limit."""
        now = datetime.now(timezone.utc)
        procedure = ProcedureMemory(
            id=str(uuid4()),
            user_id=user_id,
            description=description,
            steps=steps,
            category=category,
            importance=importance,
            source_conv_id=conversation_id,
            last_accessed=now,
            created_at=now,
        )

        def _store() -> int:
            self._repo.store_procedure(procedure)
            return self._repo.prune_old_procedures(user_id, self._max_procedures_per_user)

        deleted = await asyncio.to_thread(_store)
        if deleted:
            logger.debug("pruned %d old procedures for user %s", deleted, user_id)
        logger.info(
            "stored procedure: %s (category=%s, steps=%d)",
            description, category, len(steps),
        )
        return procedure

    async def extract_and_store_procedure(
        self,
        user_id: str,
        conversation_id: str,
        execution_trace: list[dict[str, str]],
    ) -> ProcedureMemory | None:
        """Extract a procedure from an execution trace and store it.

        Best-effort — failures are logged but not raised.
        """
        if not self._procedure_extraction_enabled or self._llm_complete is None:
            return None

        extracted = extract_procedure(
            self._llm_complete, execution_trace,
            grounding=build_grounding_context(actor_id=user_id),
        )
        if not extracted:
            return None

        try:
            return await self.store_procedure(
                user_id=user_id,
                conversation_id=conversation_id,
                description=extracted.description,
                steps=extracted.steps,
                category=extracted.category,
                importance=extracted.importance,
            )
        except Exception:
            logger.exception("failed to store extracted procedure")
            return None

    async def record_procedure_execution(
        self, procedure_id: str, success: bool
    ) -> None:
        """Record that a procedure was executed."""
        await asyncio.to_thread(self._repo.record_procedure_execution, procedure_id, success)

    async def decay_stale_procedures(
        self, days_threshold: int = 30, factor: float = 0.5
    ) -> int:
        """Reduce importance of procedures not accessed recently."""
        return await asyncio.to_thread(
            self._repo.decay_procedure_importance, days_threshold, factor
        )
