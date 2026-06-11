"""History fetcher factory for Beacon's ContextBuilder."""

from __future__ import annotations

import logging
from typing import Any, Callable

from assistant.memory.service import MemoryService

logger = logging.getLogger(__name__)


def build_history_fetcher(
    memory_service: MemoryService,
) -> Callable[[str, str], Any]:
    """Create an async history_fetcher callback for ContextBuilder.

    Returns a callable compatible with ContextBuilder's history_fetcher parameter:
        async (conversation_id, actor_id) -> list[dict]
    """

    async def history_fetcher(conversation_id: str, actor_id: str) -> list[dict[str, str]]:
        try:
            history = await memory_service.get_working_memory(conversation_id)
            logger.debug(
                "history fetch: conversation=%s actor=%s messages=%d",
                conversation_id,
                actor_id,
                len(history),
            )
            return history
        except Exception:
            logger.debug(
                "history fetch failed (continuing without history): conversation=%s actor=%s",
                conversation_id,
                actor_id,
            )
            return []

    return history_fetcher
