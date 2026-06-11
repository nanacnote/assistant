"""Pluggable interfaces for calendar persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from assistant.builtin_tools.calendar.models import (
    EventCreateRequest,
    EventModel,
    EventQuery,
    EventUpdateRequest,
    ReminderModel,
)


class CalendarStorageNotConfiguredError(RuntimeError):
    """Raised when calendar tools are used without a storage backend."""


class CalendarRepository(Protocol):
    """Persistence boundary for calendar operations."""

    def create_event(self, request: EventCreateRequest) -> EventModel: ...

    def get_event(self, event_id: str) -> EventModel | None: ...

    def list_events(self, query: EventQuery) -> list[EventModel]: ...

    def list_recurring_events(
        self, user_id: str, before: datetime, category: str | None = None
    ) -> list[EventModel]: ...

    def list_events_with_reminders(self, user_id: str) -> list[EventModel]: ...

    def search_events(self, query: EventQuery) -> list[EventModel]: ...

    def update_event(self, event_id: str, request: EventUpdateRequest) -> EventModel: ...

    def delete_event(self, event_id: str) -> bool: ...

    def get_reminders(self, within_minutes: int, user_id: str) -> list[ReminderModel]: ...


class UnconfiguredCalendarRepository:
    """Placeholder repository until a shared storage backend is supplied."""

    def _raise(self) -> None:
        raise CalendarStorageNotConfiguredError(
            "Calendar storage is not configured yet. Plug in the shared "
            "calendar repository to enable event storage and retrieval."
        )

    def create_event(self, request: EventCreateRequest) -> EventModel:
        self._raise()

    def get_event(self, event_id: str) -> EventModel | None:
        self._raise()

    def list_events(self, query: EventQuery) -> list[EventModel]:
        self._raise()

    def list_recurring_events(
        self, user_id: str, before: datetime, category: str | None = None
    ) -> list[EventModel]:
        self._raise()

    def list_events_with_reminders(self, user_id: str) -> list[EventModel]:
        self._raise()

    def search_events(self, query: EventQuery) -> list[EventModel]:
        self._raise()

    def update_event(self, event_id: str, request: EventUpdateRequest) -> EventModel:
        self._raise()

    def delete_event(self, event_id: str) -> bool:
        self._raise()

    def get_reminders(self, within_minutes: int, user_id: str) -> list[ReminderModel]:
        self._raise()


def build_calendar_repository() -> CalendarRepository:
    """Build the calendar repository backed by the assistant PostgreSQL database."""
    from assistant.builtin_tools.calendar.repository import PostgresCalendarRepository
    from assistant.storage import get_db_dsn, get_shared_connection, run_migrations

    if not get_db_dsn():
        return UnconfiguredCalendarRepository()

    conn = get_shared_connection()
    run_migrations(conn)
    return PostgresCalendarRepository(conn)
