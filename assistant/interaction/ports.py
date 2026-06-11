"""Pluggable interfaces for pending question persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, TypedDict


class PendingQuestion(TypedDict):
    id: str
    room_id: str
    thread_root: str
    question: str
    original_prompt: str
    tool_history: list[tuple[int, str, str]]
    request_metadata: dict[str, str]
    created_at: datetime


class PendingQuestionRepository(Protocol):
    """Persistence boundary for pending questions."""

    def save(self, q: PendingQuestion) -> None: ...

    def find_by_room_thread(self, room_id: str, thread_root: str) -> PendingQuestion | None: ...

    def delete(self, question_id: str) -> None: ...

    def delete_expired(self, ttl_seconds: int) -> int: ...
