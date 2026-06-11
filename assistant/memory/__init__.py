"""Conversational memory system for the assistant runtime."""

from __future__ import annotations

from assistant.memory.history import build_history_fetcher
from assistant.memory.ports import MemoryRepository, build_memory_repository
from assistant.memory.service import MemoryService

__all__ = [
    "MemoryRepository",
    "MemoryService",
    "build_history_fetcher",
    "build_memory_repository",
]


def build_memory_service(
    llm_complete=None,
    working_memory_limit: int = 20,
    max_facts_per_user: int = 500,
    extraction_enabled: bool = True,
    max_procedures_per_user: int = 200,
    procedure_extraction_enabled: bool = True,
) -> MemoryService:
    """Build a fully wired MemoryService."""
    repo = build_memory_repository()
    return MemoryService(
        repository=repo,
        llm_complete=llm_complete,
        working_memory_limit=working_memory_limit,
        max_facts_per_user=max_facts_per_user,
        extraction_enabled=extraction_enabled,
        max_procedures_per_user=max_procedures_per_user,
        procedure_extraction_enabled=procedure_extraction_enabled,
    )
