"""Tests for the calendar tool boundary and service layer."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

import pytest
from pydantic import ValidationError

from assistant.builtin_tools.calendar import register_tools as register_calendar_tools
from assistant.builtin_tools.calendar.models import (
    EventCreateRequest,
    EventModel,
    EventQuery,
    EventUpdateRequest,
    RecurrenceRuleModel,
    ReminderModel,
)
from assistant.builtin_tools.calendar.ports import UnconfiguredCalendarRepository
from assistant.builtin_tools.calendar.recurrence import expand_recurrence
from assistant.builtin_tools.calendar.repository import PostgresCalendarRepository
from assistant.builtin_tools.calendar.service import CalendarService
from assistant.tools import build_tool_registry


def _event_model(event_id: str = "evt-1", title: str = "Planning") -> EventModel:
    return EventModel(
        id=event_id,
        title=title,
        description="Sprint planning",
        start_time=datetime.fromisoformat("2026-06-12T10:00:00+00:00"),
        end_time=datetime.fromisoformat("2026-06-12T11:00:00+00:00"),
        timezone="UTC",
        category="work",
        attendees=[],
        recurrence=None,
        reminder_minutes_before=30,
        created_at=datetime.fromisoformat("2026-06-11T09:00:00+00:00"),
        updated_at=datetime.fromisoformat("2026-06-11T09:00:00+00:00"),
    )


class FakeCalendarRepository:
    def __init__(self) -> None:
        self.events = {"evt-1": _event_model()}
        self.created_requests: list[EventCreateRequest] = []
        self.list_queries: list[EventQuery] = []
        self.search_queries: list[EventQuery] = []
        self.updated: list[tuple[str, EventUpdateRequest]] = []
        self.deleted: list[str] = []
        self.reminder_requests: list[int] = []

    def create_event(self, request: EventCreateRequest) -> EventModel:
        self.created_requests.append(request)
        event = _event_model(event_id="evt-2", title=request.title)
        event.description = request.description
        event.start_time = request.start_time
        event.end_time = request.end_time
        event.timezone = request.timezone
        event.category = request.category
        event.attendees = request.attendees
        event.recurrence = request.recurrence
        event.reminder_minutes_before = request.reminder_minutes_before
        self.events[event.id] = event
        return event

    def get_event(self, event_id: str) -> EventModel | None:
        return self.events.get(event_id)

    def list_events(self, query: EventQuery) -> list[EventModel]:
        self.list_queries.append(query)
        return list(self.events.values())[: query.limit]

    def list_recurring_events(
        self, user_id: str, before: datetime, category: str | None = None
    ) -> list[EventModel]:
        return [
            e
            for e in self.events.values()
            if e.recurrence is not None
            and e.start_time <= before
            and (category is None or e.category == category)
        ]

    def list_events_with_reminders(self, user_id: str) -> list[EventModel]:
        return [e for e in self.events.values() if e.reminder_minutes_before is not None]

    def search_events(self, query: EventQuery) -> list[EventModel]:
        self.search_queries.append(query)
        needle = (query.query or "").lower()
        matches = [
            event
            for event in self.events.values()
            if needle in event.title.lower()
        ]
        return matches[: query.limit]

    def update_event(self, event_id: str, request: EventUpdateRequest) -> EventModel:
        self.updated.append((event_id, request))
        event = self.events[event_id]
        if request.title is not None:
            event.title = request.title
        if request.description is not None:
            event.description = request.description
        if request.start_time is not None:
            event.start_time = request.start_time
        if request.end_time is not None:
            event.end_time = request.end_time
        if request.timezone is not None:
            event.timezone = request.timezone
        if request.category is not None:
            event.category = request.category
        if request.attendees is not None:
            event.attendees = request.attendees
        if request.recurrence is not None:
            event.recurrence = request.recurrence
        if request.reminder_minutes_before is not None:
            event.reminder_minutes_before = request.reminder_minutes_before
        event.updated_at = datetime.fromisoformat("2026-06-11T10:00:00+00:00")
        return event

    def delete_event(self, event_id: str) -> bool:
        self.deleted.append(event_id)
        self.events.pop(event_id, None)
        return True

    def get_reminders(self, within_minutes: int) -> list[ReminderModel]:
        self.reminder_requests.append(within_minutes)
        return [
            ReminderModel(
                event_id="evt-1",
                title="Planning",
                start_time=datetime.fromisoformat("2026-06-12T10:00:00+00:00"),
                timezone="UTC",
                minutes_until_event=within_minutes,
            )
        ]


class FakeCursor:
    def __init__(self, connection: "FakeConnection", fail_on_execute: bool = False) -> None:
        self.connection = connection
        self.fail_on_execute = fail_on_execute
        self.rowcount = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, *args, **kwargs) -> None:
        if self.fail_on_execute:
            raise RuntimeError("database write failed")
        self.connection.executed.append((args, kwargs))

    def fetchone(self) -> dict[str, object]:
        return {
            "id": "evt-1",
            "title": "Planning",
            "description": "Sprint planning",
            "start_time": datetime.fromisoformat("2026-06-12T10:00:00+00:00"),
            "end_time": datetime.fromisoformat("2026-06-12T11:00:00+00:00"),
            "timezone": "UTC",
            "category": "work",
            "attendees": [],
            "recurrence": None,
            "reminder_minutes_before": 30,
            "created_at": datetime.fromisoformat("2026-06-11T09:00:00+00:00"),
            "updated_at": datetime.fromisoformat("2026-06-11T09:00:00+00:00"),
        }

    def fetchall(self) -> list[dict[str, object]]:
        return [self.fetchone()]


class FakeConnection:
    def __init__(self, fail_on_execute: bool = False) -> None:
        self.fail_on_execute = fail_on_execute
        self.executed: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.rollback_calls = 0
        self.commit_calls = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self, fail_on_execute=self.fail_on_execute)

    def rollback(self) -> None:
        self.rollback_calls += 1

    def commit(self) -> None:
        self.commit_calls += 1


def test_calendar_tools_register_with_builtin_plugin_contract() -> None:
    registry = build_tool_registry()
    register_calendar_tools(registry)

    assert registry.get("CreateEvent") is not None
    assert registry.get("ListEvents") is not None
    assert registry.get("ListEventsForYear") is not None
    assert registry.get("SearchEvents") is not None
    assert registry.get("UpdateEvent") is not None
    assert registry.get("DeleteEvent") is not None
    assert registry.get("CheckReminders") is not None


def test_calendar_service_validates_and_normalizes_create_request() -> None:
    repository = FakeCalendarRepository()
    service = CalendarService(repository)

    event = service.create_event(
        user_id="@test:example.com",
        title="  Demo  ",
        description="  Review roadmap  ",
        start_time="2026-06-13T09:00:00",
        end_time="2026-06-13T10:00:00",
        timezone="UTC",
        category="  work  ",
        attendees_json='[{"name": "Nana", "email": "nana@example.com"}]',
        recurrence_json='{"frequency": "weekly", "interval": 1}',
        reminder_minutes_before=15,
    )

    assert event.id == "evt-2"
    assert repository.created_requests[0].title == "Demo"
    assert repository.created_requests[0].description == "Review roadmap"
    assert repository.created_requests[0].category == "work"
    assert repository.created_requests[0].attendees[0].name == "Nana"
    assert repository.created_requests[0].recurrence is not None


def test_calendar_service_lists_events_for_year() -> None:
    repository = FakeCalendarRepository()
    service = CalendarService(repository)

    events = service.list_events_for_year(
        user_id="@test:example.com",
        year=2026,
        timezone="UTC",
        category="work",
        limit=25,
    )

    assert events[0].id == "evt-1"
    assert repository.list_queries[0].start_time == datetime.fromisoformat(
        "2026-01-01T00:00:00+00:00"
    )
    assert repository.list_queries[0].end_time == datetime.fromisoformat(
        "2027-01-01T00:00:00+00:00"
    )
    assert repository.list_queries[0].category == "work"


def test_calendar_repository_rolls_back_on_query_error() -> None:
    repository = PostgresCalendarRepository(FakeConnection(fail_on_execute=True))

    try:
        repository.list_events(
            EventQuery(
                start_time=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
                end_time=datetime.fromisoformat("2027-01-01T00:00:00+00:00"),
                limit=10,
            )
        )
    except RuntimeError:
        pass

    assert repository._conn.rollback_calls == 1


def test_calendar_tool_execution_uses_injected_service() -> None:
    repository = FakeCalendarRepository()
    service = CalendarService(repository)
    registry = build_tool_registry()

    from assistant.builtin_tools.calendar.tools import (
        register_tools as register_calendar_tool_classes,
    )

    register_calendar_tool_classes(registry, service)
    create_event_tool = cast(Any, registry.get("CreateEvent"))

    result = create_event_tool(
        title="Standup",
        description="Daily sync",
        start_time="2026-06-13T09:00:00",
        end_time="2026-06-13T09:15:00",
        timezone="UTC",
        category="work",
        attendees_json="[]",
        recurrence_json="null",
        reminder_minutes_before=5,
    ).execute()

    assert result["event"]["title"] == "Standup"
    assert repository.created_requests[0].title == "Standup"


def test_calendar_create_tool_rejects_placeholder_titles() -> None:
    repository = FakeCalendarRepository()
    service = CalendarService(repository)
    registry = build_tool_registry()

    from assistant.builtin_tools.calendar.tools import (
        register_tools as register_calendar_tool_classes,
    )

    register_calendar_tool_classes(registry, service)
    create_event_tool = cast(Any, registry.get("CreateEvent"))

    with pytest.raises(ValidationError, match="specific enough"):
        create_event_tool(
            title="New Event",
            description="Daily sync",
            start_time="2026-06-13T09:00:00",
            end_time="2026-06-13T09:15:00",
            timezone="UTC",
            category="work",
            attendees_json="[]",
            recurrence_json="null",
            reminder_minutes_before=5,
        )


def test_calendar_create_tool_rejects_natural_language_datetimes() -> None:
    repository = FakeCalendarRepository()
    service = CalendarService(repository)
    registry = build_tool_registry()

    from assistant.builtin_tools.calendar.tools import (
        register_tools as register_calendar_tool_classes,
    )

    register_calendar_tool_classes(registry, service)
    create_event_tool = cast(Any, registry.get("CreateEvent"))

    with pytest.raises(ValidationError, match="ISO 8601"):
        create_event_tool(
            title="Project planning",
            description="Daily sync",
            start_time="next month",
            end_time="next month",
            timezone="UTC",
            category="work",
            attendees_json="[]",
            recurrence_json="null",
            reminder_minutes_before=5,
        )


def test_calendar_year_tool_execution_uses_injected_service() -> None:
    repository = FakeCalendarRepository()
    service = CalendarService(repository)
    registry = build_tool_registry()

    from assistant.builtin_tools.calendar.tools import (
        register_tools as register_calendar_tool_classes,
    )

    register_calendar_tool_classes(registry, service)
    list_year_events_tool = cast(Any, registry.get("ListEventsForYear"))

    result = list_year_events_tool(
        year=2026,
        timezone="UTC",
        category=None,
        limit=10,
    ).execute()

    assert result["count"] == 1
    assert repository.list_queries[0].start_time == datetime.fromisoformat(
        "2026-01-01T00:00:00+00:00"
    )


def test_calendar_tool_reports_storage_not_configured() -> None:
    service = CalendarService(UnconfiguredCalendarRepository())
    registry = build_tool_registry()

    from assistant.builtin_tools.calendar.tools import (
        register_tools as register_calendar_tool_classes,
    )

    register_calendar_tool_classes(registry, service)
    list_events_tool = cast(Any, registry.get("ListEvents"))

    result = list_events_tool(
        start_time="2026-06-12T00:00:00",
        end_time="2026-06-13T00:00:00",
        timezone="UTC",
        category=None,
        limit=10,
    ).execute()

    assert result == {
        "error": (
            "Calendar storage is not configured yet. Plug in the shared "
            "calendar repository to enable event storage and retrieval."
        )
    }


def test_calendar_service_update_and_delete_use_repository_lookup() -> None:
    repository = FakeCalendarRepository()
    service = CalendarService(repository)

    updated = service.update_event(
        user_id="@test:example.com",
        event_id="evt-1",
        updates_json='{"title": "Updated Planning", "end_time": "2026-06-12T11:30:00+00:00"}',
    )
    deleted = service.delete_event(user_id="@test:example.com", event_id="evt-1")

    assert updated.title == "Updated Planning"
    assert repository.updated[0][0] == "evt-1"
    assert deleted is True
    assert repository.deleted == ["evt-1"]


def _recurring_event(
    event_id: str = "rec-1",
    title: str = "Birthday",
    start: str = "2024-02-01T00:00:00+00:00",
    frequency: str = "yearly",
    interval: int = 1,
    count: int | None = None,
    until: str | None = None,
    reminder_minutes: int | None = None,
    by_day: list[str] | None = None,
) -> EventModel:
    return EventModel(
        id=event_id,
        title=title,
        description="",
        start_time=datetime.fromisoformat(start),
        end_time=datetime.fromisoformat(start) + timedelta(hours=1),
        timezone="UTC",
        category="personal",
        attendees=[],
        recurrence=RecurrenceRuleModel(
            frequency=frequency,  # type: ignore[arg-type]
            interval=interval,
            count=count,
            until=datetime.fromisoformat(until) if until else None,
            by_day=by_day,
        ),
        reminder_minutes_before=reminder_minutes,
        created_at=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
        updated_at=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
    )


def test_expand_yearly_recurrence_across_years() -> None:
    event = _recurring_event(start="2024-02-01T00:00:00+00:00")
    window_start = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2027-01-01T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 1
    assert occurrences[0].start_time.year == 2026
    assert occurrences[0].start_time.month == 2
    assert occurrences[0].start_time.day == 1
    assert occurrences[0].id == "rec-1#occurrence-2"


def test_expand_monthly_recurrence() -> None:
    event = _recurring_event(
        start="2026-01-15T09:00:00+00:00",
        frequency="monthly",
    )
    window_start = datetime.fromisoformat("2026-03-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-06-01T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 3
    assert occurrences[0].start_time.month == 3
    assert occurrences[1].start_time.month == 4
    assert occurrences[2].start_time.month == 5


def test_expand_weekly_recurrence() -> None:
    event = _recurring_event(
        start="2026-06-01T10:00:00+00:00",
        frequency="weekly",
    )
    window_start = datetime.fromisoformat("2026-06-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-06-29T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 4


def test_expand_daily_recurrence() -> None:
    event = _recurring_event(
        start="2026-06-01T08:00:00+00:00",
        frequency="daily",
    )
    window_start = datetime.fromisoformat("2026-06-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-06-04T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 3


def test_expand_recurrence_with_count_limit() -> None:
    event = _recurring_event(
        start="2026-01-01T00:00:00+00:00",
        frequency="monthly",
        count=3,
    )
    window_start = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-12-31T23:59:59+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 3


def test_expand_recurrence_with_until_date() -> None:
    event = _recurring_event(
        start="2026-01-01T00:00:00+00:00",
        frequency="monthly",
        until="2026-04-01T00:00:00+00:00",
    )
    window_start = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-12-31T23:59:59+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 4
    assert occurrences[-1].start_time.month == 4


def test_expand_monthly_recurrence_on_31st_handles_short_months() -> None:
    event = _recurring_event(
        start="2026-01-31T00:00:00+00:00",
        frequency="monthly",
    )
    window_start = datetime.fromisoformat("2026-02-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-05-01T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 1
    assert occurrences[0].start_time.month == 3
    assert occurrences[0].start_time.day == 31


def test_expand_yearly_recurrence_on_feb_29_handles_non_leap_years() -> None:
    event = _recurring_event(
        start="2024-02-29T00:00:00+00:00",
        frequency="yearly",
    )
    window_start = datetime.fromisoformat("2025-01-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2028-12-31T23:59:59+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 1
    assert occurrences[0].start_time.year == 2028
    assert occurrences[0].start_time.month == 2
    assert occurrences[0].start_time.day == 29


def test_expand_recurrence_with_interval() -> None:
    event = _recurring_event(
        start="2026-01-01T00:00:00+00:00",
        frequency="monthly",
        interval=2,
    )
    window_start = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-12-31T23:59:59+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 6
    assert occurrences[0].start_time.month == 1
    assert occurrences[1].start_time.month == 3
    assert occurrences[2].start_time.month == 5


def test_expand_non_recurring_event_returns_as_is() -> None:
    event = _event_model()
    window_start = datetime.fromisoformat("2026-06-12T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-06-13T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 1
    assert occurrences[0].id == "evt-1"


def test_expand_non_recurring_event_outside_window_returns_empty() -> None:
    event = _event_model()
    window_start = datetime.fromisoformat("2026-07-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-07-31T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 0


def test_calendar_service_list_events_expands_recurrence() -> None:
    repository = FakeCalendarRepository()
    repository.events["rec-1"] = _recurring_event(
        start="2024-02-01T00:00:00+00:00",
    )
    service = CalendarService(repository)

    events = service.list_events(
        user_id="@test:example.com",
        start_time="2026-01-01T00:00:00",
        end_time="2026-12-31T23:59:59",
        timezone="UTC",
        category=None,
        limit=50,
    )

    titles = [e.title for e in events]
    assert "Birthday" in titles


def test_calendar_service_list_events_for_year_expands_recurrence() -> None:
    repository = FakeCalendarRepository()
    repository.events["rec-1"] = _recurring_event(
        start="2024-02-01T00:00:00+00:00",
    )
    service = CalendarService(repository)

    events = service.list_events_for_year(
        user_id="@test:example.com",
        year=2026,
        timezone="UTC",
        category=None,
        limit=100,
    )

    birthday_events = [e for e in events if e.title == "Birthday"]
    assert len(birthday_events) == 1
    assert birthday_events[0].start_time.year == 2026
    assert birthday_events[0].start_time.month == 2
    assert birthday_events[0].start_time.day == 1


def test_calendar_service_search_expands_recurrence() -> None:
    repository = FakeCalendarRepository()
    repository.events["rec-1"] = _recurring_event(
        start="2024-02-01T00:00:00+00:00",
    )
    service = CalendarService(repository)

    events = service.search_events(
        user_id="@test:example.com",
        query_text="Birthday",
        timezone="UTC",
        category=None,
        start_time="2026-01-01T00:00:00",
        end_time="2026-12-31T23:59:59",
        limit=50,
    )

    assert len(events) == 1
    assert events[0].start_time.year == 2026


def test_calendar_service_search_expands_recurrence_without_date_range() -> None:
    repository = FakeCalendarRepository()
    repository.events["rec-1"] = _recurring_event(
        start="2024-02-01T00:00:00+00:00",
    )
    service = CalendarService(repository)

    events = service.search_events(
        user_id="@test:example.com",
        query_text="Birthday",
        timezone="UTC",
        category=None,
        start_time=None,
        end_time=None,
        limit=50,
    )

    titles = [e.title for e in events]
    assert "Birthday" in titles


def test_expand_recurrence_preserves_duration() -> None:
    event = _recurring_event(start="2026-01-01T10:00:00+00:00", frequency="daily")
    window_start = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-01-02T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 1
    duration = occurrences[0].end_time - occurrences[0].start_time
    assert duration == timedelta(hours=1)


def test_expand_recurrence_empty_when_entirely_before_window() -> None:
    event = _recurring_event(
        start="2020-01-01T00:00:00+00:00",
        frequency="yearly",
        count=2,
    )
    window_start = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-12-31T23:59:59+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 0


def test_expand_weekly_recurrence_with_by_day() -> None:
    event = _recurring_event(
        start="2026-06-15T13:00:00+00:00",
        frequency="weekly",
        count=6,
        by_day=["MO"],
    )
    window_start = datetime.fromisoformat("2026-06-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-08-01T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 6
    for occ in occurrences:
        assert occ.start_time.weekday() == 0
        assert occ.start_time.hour == 13


def test_expand_weekly_recurrence_with_multiple_by_days() -> None:
    event = _recurring_event(
        start="2026-06-15T09:00:00+00:00",
        frequency="weekly",
        count=6,
        by_day=["MO", "WE", "FR"],
    )
    window_start = datetime.fromisoformat("2026-06-15T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-07-15T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 6
    weekdays = {occ.start_time.weekday() for occ in occurrences}
    assert weekdays <= {0, 2, 4}


def test_expand_monthly_recurrence_with_nth_weekday() -> None:
    event = _recurring_event(
        start="2026-01-13T10:00:00+00:00",
        frequency="monthly",
        count=3,
        by_day=["2TU"],
    )
    window_start = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    window_end = datetime.fromisoformat("2026-06-01T00:00:00+00:00")

    occurrences = expand_recurrence(event, window_start, window_end)

    assert len(occurrences) == 3
    assert occurrences[0].start_time.day == 13
    assert occurrences[0].start_time.month == 1
    assert occurrences[1].start_time.day == 10
    assert occurrences[1].start_time.month == 2
    assert occurrences[2].start_time.day == 10
    assert occurrences[2].start_time.month == 3


def test_recurrence_rule_model_accepts_by_day_string() -> None:
    rule = RecurrenceRuleModel(
        frequency="weekly",
        by_day="MO",
    )
    assert rule.by_day == ["MO"]


def test_recurrence_rule_model_accepts_by_day_list() -> None:
    rule = RecurrenceRuleModel(
        frequency="weekly",
        by_day=["MO", "WE", "FR"],
    )
    assert rule.by_day == ["MO", "WE", "FR"]


def test_calendar_service_create_event_with_by_day_recurrence() -> None:
    repository = FakeCalendarRepository()
    service = CalendarService(repository)

    event = service.create_event(
        user_id="@test:example.com",
        title="Lunch with friend",
        description="",
        start_time="2026-06-15T13:00:00",
        end_time="2026-06-15T14:00:00",
        timezone="UTC",
        category="personal",
        attendees_json="[]",
        recurrence_json='{"frequency": "weekly", "interval": 1, "count": 6, "by_day": ["MO"]}',
        reminder_minutes_before=None,
    )

    assert event.recurrence is not None
    assert event.recurrence.by_day == ["MO"]
    assert event.recurrence.frequency == "weekly"
    assert event.recurrence.count == 6
