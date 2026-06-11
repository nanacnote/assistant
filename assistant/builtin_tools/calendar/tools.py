"""Calendar tool registrations."""

from __future__ import annotations

import re
from datetime import datetime

from keel.core.registry import BaseTool, ToolRegistry, register_tool
from pydantic import Field, field_validator

from assistant.builtin_tools.calendar.service import CalendarService


def register_tools(registry: ToolRegistry, service: CalendarService) -> None:
    """Register calendar tools against the given registry."""

    @register_tool(registry=registry)
    class CreateEvent(BaseTool):
        """Create a calendar event."""

        tool_name = "CreateEvent"
        _actor_field = "user_id"
        user_id: str = Field(default="", description="Owner user ID (injected automatically)")
        title: str = Field(description="Event title")
        description: str = Field(default="", description="Event description")
        start_time: str = Field(description="Event start time in ISO 8601 format")
        end_time: str = Field(description="Event end time in ISO 8601 format")
        timezone: str = Field(
            default="UTC",
            description="IANA timezone name, for example UTC or Europe/London",
        )
        category: str = Field(
            default="general",
            description="Event category such as work, personal, or travel",
        )
        attendees_json: str = Field(
            default="[]",
            description=(
                "JSON array of attendees with name, optional email, and optional "
                "status"
            ),
        )
        recurrence_json: str = Field(
            default="null",
            description=(
                "JSON object describing recurrence (RFC 5545 RRULE), or null when "
                "the event does not repeat. Fields: frequency (daily|weekly|monthly|"
                "yearly, required), interval (int, default 1), count (int), until "
                "(ISO 8601 datetime), by_day (list of day abbreviations: MO, TU, WE, "
                "TH, FR, SA, SU; prefix with int for nth weekday e.g. 2TU), "
                "by_month (list of ints 1-12), by_month_day (list of ints 1-31), "
                "by_year_day (list of ints 1-366)."
            ),
        )
        reminder_minutes_before: int | None = Field(
            default=None,
            description="Minutes before the event when a reminder should appear",
        )

        @field_validator("title")
        @classmethod
        def _validate_title(cls, value: str) -> str:
            normalized = value.strip()
            if not normalized:
                raise ValueError("title must not be empty.")

            words = re.findall(r"[A-Za-z0-9']+", normalized)
            content_chars = len(re.sub(r"[^A-Za-z0-9]", "", normalized))
            if len(words) == 1 and content_chars < 6:
                raise ValueError(
                    "title must be specific enough to identify the event; ask the user "
                    "for a clearer title before creating it."
                )
            if len(words) >= 2 and content_chars < 10:
                raise ValueError(
                    "title must be specific enough to identify the event; ask the user "
                    "for a clearer title before creating it."
                )
            return normalized

        @field_validator("start_time", "end_time")
        @classmethod
        def _validate_iso_datetime(cls, value: str, info) -> str:
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{info.field_name} must not be empty.")
            try:
                datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise ValueError(
                    f"{info.field_name} must be an ISO 8601 datetime string."
                ) from exc
            return normalized

        def execute(self) -> dict[str, object]:
            try:
                event = service.create_event(
                    user_id=self.user_id,
                    title=self.title,
                    description=self.description,
                    start_time=self.start_time,
                    end_time=self.end_time,
                    timezone=self.timezone,
                    category=self.category,
                    attendees_json=self.attendees_json,
                    recurrence_json=self.recurrence_json,
                    reminder_minutes_before=self.reminder_minutes_before,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}
            return service.summarize_event(event)

    @register_tool(registry=registry)
    class ListEvents(BaseTool):
        """List calendar events in a time range."""

        tool_name = "ListEvents"
        _actor_field = "user_id"
        user_id: str = Field(default="", description="Owner user ID (injected automatically)")
        start_time: str = Field(description="Range start time in ISO 8601 format")
        end_time: str = Field(description="Range end time in ISO 8601 format")
        timezone: str = Field(
            default="UTC",
            description="IANA timezone name for interpreting range inputs",
        )
        category: str | None = Field(default=None, description="Optional category filter")
        limit: int = Field(default=50, description="Maximum number of events to return")

        def execute(self) -> dict[str, object]:
            try:
                events = service.list_events(
                    user_id=self.user_id,
                    start_time=self.start_time,
                    end_time=self.end_time,
                    timezone=self.timezone,
                    category=self.category,
                    limit=self.limit,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}
            return service.summarize_events(events)

    @register_tool(registry=registry)
    class ListEventsForYear(BaseTool):
        """List calendar events across a whole year."""

        tool_name = "ListEventsForYear"
        _actor_field = "user_id"
        user_id: str = Field(default="", description="Owner user ID (injected automatically)")
        year: int = Field(description="Calendar year to inspect, for example 2026")
        timezone: str = Field(
            default="UTC",
            description="IANA timezone name for interpreting the yearly window",
        )
        category: str | None = Field(default=None, description="Optional category filter")
        limit: int = Field(default=100, description="Maximum number of events to return")

        def execute(self) -> dict[str, object]:
            try:
                events = service.list_events_for_year(
                    user_id=self.user_id,
                    year=self.year,
                    timezone=self.timezone,
                    category=self.category,
                    limit=self.limit,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}
            return service.summarize_events(events)

    @register_tool(registry=registry)
    class SearchEvents(BaseTool):
        """Search calendar events by text and optional filters."""

        tool_name = "SearchEvents"
        _actor_field = "user_id"
        user_id: str = Field(default="", description="Owner user ID (injected automatically)")
        query_text: str = Field(description="Free text search over titles and descriptions")
        timezone: str = Field(
            default="UTC",
            description="IANA timezone name for interpreting optional date filters",
        )
        category: str | None = Field(default=None, description="Optional category filter")
        start_time: str | None = Field(
            default=None,
            description="Optional earliest event start time in ISO 8601 format",
        )
        end_time: str | None = Field(
            default=None,
            description="Optional latest event end time in ISO 8601 format",
        )
        limit: int = Field(default=50, description="Maximum number of events to return")

        def execute(self) -> dict[str, object]:
            try:
                events = service.search_events(
                    user_id=self.user_id,
                    query_text=self.query_text,
                    timezone=self.timezone,
                    category=self.category,
                    start_time=self.start_time,
                    end_time=self.end_time,
                    limit=self.limit,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}
            return service.summarize_events(events)

    @register_tool(registry=registry)
    class UpdateEvent(BaseTool):
        """Update an existing calendar event."""

        tool_name = "UpdateEvent"
        _actor_field = "user_id"
        user_id: str = Field(default="", description="Owner user ID (injected automatically)")
        event_id: str = Field(description="Event identifier")
        updates_json: str = Field(description="JSON object with the fields to update")

        def execute(self) -> dict[str, object]:
            try:
                event = service.update_event(
                    user_id=self.user_id,
                    event_id=self.event_id,
                    updates_json=self.updates_json,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}
            return service.summarize_event(event)

    @register_tool(registry=registry)
    class DeleteEvent(BaseTool):
        """Delete a calendar event."""

        tool_name = "DeleteEvent"
        _actor_field = "user_id"
        user_id: str = Field(default="", description="Owner user ID (injected automatically)")
        event_id: str = Field(description="Event identifier")

        def execute(self) -> dict[str, object]:
            try:
                service.delete_event(user_id=self.user_id, event_id=self.event_id)
            except Exception as exc:
                return {"error": service.describe_error(exc)}
            return service.summarize_delete(self.event_id)

    @register_tool(registry=registry)
    class CheckReminders(BaseTool):
        """Retrieve reminders due within a time window."""

        tool_name = "CheckReminders"
        _actor_field = "user_id"
        user_id: str = Field(default="", description="Owner user ID (injected automatically)")
        within_minutes: int = Field(
            default=60,
            description="Return reminders due within this many minutes",
        )

        def execute(self) -> dict[str, object]:
            try:
                reminders = service.check_reminders(
                    user_id=self.user_id,
                    within_minutes=self.within_minutes,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}
            return service.summarize_reminders(reminders)
