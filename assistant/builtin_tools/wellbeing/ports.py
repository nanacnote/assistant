"""Pluggable interfaces for wellbeing persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from assistant.builtin_tools.wellbeing.models import (
    CheckInRecord,
    CheckInRequest,
    StateLogRecord,
    StateLogRequest,
    WellbeingPreferences,
)


class WellbeingStorageNotConfiguredError(RuntimeError):
    """Raised when wellbeing tools run without a configured storage backend."""


class WellbeingRepository(Protocol):
    """Persistence boundary for wellbeing coaching data."""

    def record_checkin(self, user_id: str, request: CheckInRequest) -> CheckInRecord: ...

    def log_state(self, user_id: str, request: StateLogRequest) -> StateLogRecord: ...

    def list_checkins(
        self, user_id: str, start_time: datetime, end_time: datetime, limit: int
    ) -> list[CheckInRecord]: ...

    def list_state_logs(
        self, user_id: str, start_time: datetime, end_time: datetime, limit: int
    ) -> list[StateLogRecord]: ...

    def set_preferences(
        self,
        user_id: str,
        preferences: WellbeingPreferences,
    ) -> WellbeingPreferences: ...

    def get_preferences(self, user_id: str) -> WellbeingPreferences | None: ...


class UnconfiguredWellbeingRepository:
    """Placeholder repository until a shared storage backend is supplied."""

    def _raise(self) -> None:
        raise WellbeingStorageNotConfiguredError(
            "Wellbeing storage is not configured yet. Plug in the shared "
            "wellbeing repository to enable tracking and analysis."
        )

    def record_checkin(self, user_id: str, request: CheckInRequest) -> CheckInRecord:
        self._raise()

    def log_state(self, user_id: str, request: StateLogRequest) -> StateLogRecord:
        self._raise()

    def list_checkins(
        self, user_id: str, start_time: datetime, end_time: datetime, limit: int
    ) -> list[CheckInRecord]:
        self._raise()

    def list_state_logs(
        self, user_id: str, start_time: datetime, end_time: datetime, limit: int
    ) -> list[StateLogRecord]:
        self._raise()

    def set_preferences(
        self,
        user_id: str,
        preferences: WellbeingPreferences,
    ) -> WellbeingPreferences:
        self._raise()

    def get_preferences(self, user_id: str) -> WellbeingPreferences | None:
        self._raise()


def build_wellbeing_repository() -> WellbeingRepository:
    """Build the wellbeing repository backed by the assistant PostgreSQL database."""
    from assistant.builtin_tools.wellbeing.repository import PostgresWellbeingRepository
    from assistant.storage import get_db_dsn, get_shared_connection, run_migrations

    if not get_db_dsn():
        return UnconfiguredWellbeingRepository()

    conn = get_shared_connection()
    run_migrations(conn)
    return PostgresWellbeingRepository(conn)
