"""Validation and orchestration for calendar tools."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from assistant.builtin_tools.calendar.models import (
    AttendeeModel,
    EventCreateRequest,
    EventModel,
    EventQuery,
    EventUpdateRequest,
    RecurrenceRuleModel,
    ReminderModel,
)
from assistant.builtin_tools.calendar.ports import (
    CalendarRepository,
    CalendarStorageNotConfiguredError,
)
from assistant.builtin_tools.calendar.recurrence import expand_recurrence


class CalendarService:
    """Application service for calendar operations."""

    def __init__(self, repository: CalendarRepository):
        self.repository = repository

    def create_event(
        self,
        *,
        user_id: str,
        title: str,
        description: str,
        start_time: str,
        end_time: str,
        timezone: str,
        category: str,
        attendees_json: str | None,
        recurrence_json: str | None,
        reminder_minutes_before: int | None,
    ) -> EventModel:
        request = EventCreateRequest(
            user_id=user_id,
            title=title.strip(),
            description=description.strip(),
            start_time=self._parse_datetime(start_time, timezone),
            end_time=self._parse_datetime(end_time, timezone),
            timezone=self._normalize_timezone(timezone),
            category=self._normalize_category(category),
            attendees=self._parse_attendees(attendees_json),
            recurrence=self._parse_recurrence(recurrence_json),
            reminder_minutes_before=reminder_minutes_before,
        )
        self._validate_event_window(request.start_time, request.end_time)
        return self.repository.create_event(request)

    def list_events(
        self,
        *,
        user_id: str,
        start_time: str,
        end_time: str,
        timezone: str,
        category: str | None,
        limit: int,
    ) -> list[EventModel]:
        normalized_timezone = self._normalize_timezone(timezone)
        window_start = self._parse_datetime(start_time, normalized_timezone)
        window_end = self._parse_datetime(end_time, normalized_timezone)
        normalized_category = self._normalize_optional_category(category)
        self._validate_event_window(window_start, window_end)

        query = EventQuery(
            user_id=user_id,
            start_time=window_start,
            end_time=window_end,
            category=normalized_category,
            limit=limit,
        )
        raw_events = self.repository.list_events(query)
        non_recurring = [e for e in raw_events if e.recurrence is None]
        recurring = self.repository.list_recurring_events(
            user_id, window_end, normalized_category
        )
        expanded: list[EventModel] = []
        for event in recurring:
            expanded.extend(expand_recurrence(event, window_start, window_end))
        seen: set[str] = set()
        merged: list[EventModel] = []
        for event in non_recurring + expanded:
            if event.id not in seen:
                seen.add(event.id)
                merged.append(event)
        merged.sort(key=lambda e: e.start_time)
        return merged[:limit]

    def list_events_for_year(
        self,
        *,
        user_id: str,
        year: int,
        timezone: str,
        category: str | None,
        limit: int,
    ) -> list[EventModel]:
        if year < 1 or year > 9998:
            raise ValueError("year must be between 1 and 9998.")

        normalized_timezone = self._normalize_timezone(timezone)
        normalized_category = self._normalize_optional_category(category)
        window_start = datetime(year, 1, 1, tzinfo=ZoneInfo(normalized_timezone))
        window_end = datetime(year + 1, 1, 1, tzinfo=ZoneInfo(normalized_timezone))
        query = EventQuery(
            user_id=user_id,
            start_time=window_start,
            end_time=window_end,
            category=normalized_category,
            limit=limit,
        )
        raw_events = self.repository.list_events(query)
        non_recurring = [e for e in raw_events if e.recurrence is None]
        recurring = self.repository.list_recurring_events(
            user_id, window_end, normalized_category
        )
        expanded: list[EventModel] = []
        for event in recurring:
            expanded.extend(expand_recurrence(event, window_start, window_end))
        seen: set[str] = set()
        merged: list[EventModel] = []
        for event in non_recurring + expanded:
            if event.id not in seen:
                seen.add(event.id)
                merged.append(event)
        merged.sort(key=lambda e: e.start_time)
        return merged[:limit]

    def search_events(
        self,
        *,
        user_id: str,
        query_text: str,
        timezone: str,
        category: str | None,
        start_time: str | None,
        end_time: str | None,
        limit: int,
    ) -> list[EventModel]:
        normalized_timezone = self._normalize_timezone(timezone)
        normalized_category = self._normalize_optional_category(category)
        window_start = self._parse_optional_datetime(start_time, normalized_timezone)
        window_end = self._parse_optional_datetime(end_time, normalized_timezone)
        query = EventQuery(
            user_id=user_id,
            query=query_text.strip(),
            start_time=window_start,
            end_time=window_end,
            category=normalized_category,
            limit=limit,
        )
        if not query.query:
            raise ValueError("Search query must not be empty.")
        if window_start and window_end:
            self._validate_event_window(window_start, window_end)
        raw_results = self.repository.search_events(query)
        non_recurring = [e for e in raw_results if e.recurrence is None]

        expanded: list[EventModel] = []
        needle = (query_text.strip()).lower()
        effective_end = window_end or datetime.now(ZoneInfo("UTC")) + timedelta(days=365)
        effective_start = window_start or datetime.min.replace(tzinfo=ZoneInfo("UTC"))
        recurring = self.repository.list_recurring_events(
            user_id, effective_end, normalized_category
        )
        for event in recurring:
            if needle in event.title.lower() or needle in event.description.lower():
                expanded.extend(
                    expand_recurrence(event, effective_start, effective_end)
                )
        seen: set[str] = set()
        merged: list[EventModel] = []
        for event in non_recurring + expanded:
            if event.id not in seen:
                seen.add(event.id)
                merged.append(event)
        merged.sort(key=lambda e: e.start_time)
        return merged[:limit]

    def update_event(self, *, user_id: str, event_id: str, updates_json: str) -> EventModel:
        if not event_id.strip():
            raise ValueError("event_id must not be empty.")
        payload = self._parse_json_object(updates_json, field_name="updates_json")
        request = EventUpdateRequest(
            title=self._normalize_optional_title(payload.get("title")),
            description=self._normalize_optional_text(payload.get("description")),
            start_time=self._parse_optional_datetime_value(
                payload.get("start_time"),
                payload.get("timezone"),
            ),
            end_time=self._parse_optional_datetime_value(
                payload.get("end_time"),
                payload.get("timezone"),
            ),
            timezone=self._normalize_optional_timezone(payload.get("timezone")),
            category=self._normalize_optional_category(payload.get("category")),
            attendees=self._parse_attendees_object(payload.get("attendees")),
            recurrence=self._parse_recurrence_object(payload.get("recurrence")),
            reminder_minutes_before=payload.get("reminder_minutes_before"),
        )
        existing = self.repository.get_event(event_id.strip())
        if existing is None:
            raise ValueError(f"No event found for id '{event_id}'.")
        next_start = request.start_time or existing.start_time
        next_end = request.end_time or existing.end_time
        self._validate_event_window(next_start, next_end)
        return self.repository.update_event(event_id.strip(), request)

    def delete_event(self, *, user_id: str, event_id: str) -> bool:
        if not event_id.strip():
            raise ValueError("event_id must not be empty.")
        existing = self.repository.get_event(event_id.strip())
        if existing is None:
            raise ValueError(f"No event found for id '{event_id}'.")
        return self.repository.delete_event(event_id.strip())

    def check_reminders(self, *, user_id: str, within_minutes: int) -> list[ReminderModel]:
        if within_minutes <= 0:
            raise ValueError("within_minutes must be greater than zero.")

        now = datetime.now(ZoneInfo("UTC"))
        window_end = now + timedelta(minutes=within_minutes)

        non_recurring_reminders = self.repository.get_reminders(within_minutes, user_id)

        recurring_events = self.repository.list_events_with_reminders(user_id)
        recurring_reminders: list[ReminderModel] = []
        for event in recurring_events:
            if event.reminder_minutes_before is None:
                continue
            occurrences = expand_recurrence(event, now, window_end)
            for occ in occurrences:
                reminder_time = occ.start_time - timedelta(
                    minutes=event.reminder_minutes_before
                )
                if reminder_time <= now and occ.start_time >= now:
                    delta = int((occ.start_time - now).total_seconds() / 60)
                    recurring_reminders.append(
                        ReminderModel(
                            event_id=occ.id,
                            title=occ.title,
                            start_time=occ.start_time,
                            timezone=occ.timezone,
                            minutes_until_event=max(0, delta),
                        )
                    )
                elif reminder_time > now and reminder_time <= window_end:
                    delta = int((occ.start_time - now).total_seconds() / 60)
                    recurring_reminders.append(
                        ReminderModel(
                            event_id=occ.id,
                            title=occ.title,
                            start_time=occ.start_time,
                            timezone=occ.timezone,
                            minutes_until_event=max(0, delta),
                        )
                    )

        seen: set[str] = set()
        merged: list[ReminderModel] = []
        for reminder in non_recurring_reminders + recurring_reminders:
            if reminder.event_id not in seen:
                seen.add(reminder.event_id)
                merged.append(reminder)
        merged.sort(key=lambda r: r.minutes_until_event)
        return merged

    def describe_error(self, error: Exception) -> str:
        """Return a stable user-facing error message."""
        if isinstance(error, CalendarStorageNotConfiguredError):
            return str(error)
        if isinstance(error, ValidationError):
            return error.errors()[0].get("msg", "Calendar request is invalid.")
        return str(error) or "Calendar request failed."

    def summarize_event(self, event: EventModel) -> dict[str, object]:
        return {
            "event": event.model_dump(mode="json"),
            "message": (
                f"Scheduled '{event.title}' from {event.start_time.isoformat()} "
                f"to {event.end_time.isoformat()} ({event.timezone})."
            ),
        }

    def summarize_events(self, events: list[EventModel]) -> dict[str, object]:
        return {
            "events": [event.model_dump(mode="json") for event in events],
            "count": len(events),
        }

    def summarize_delete(self, event_id: str) -> dict[str, object]:
        return {
            "deleted_event_id": event_id,
            "message": f"Deleted event '{event_id}'.",
        }

    def summarize_reminders(self, reminders: list[ReminderModel]) -> dict[str, object]:
        return {
            "reminders": [reminder.model_dump(mode="json") for reminder in reminders],
            "count": len(reminders),
        }

    def _normalize_timezone(self, timezone: str | None) -> str:
        value = (timezone or "UTC").strip()
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone '{value}'.") from exc
        return value

    def _normalize_optional_timezone(self, timezone: object) -> str | None:
        if timezone is None:
            return None
        if not isinstance(timezone, str):
            raise ValueError("timezone must be a string.")
        return self._normalize_timezone(timezone)

    def _normalize_category(self, category: str | None) -> str:
        value = (category or "general").strip()
        if not value:
            return "general"
        return value

    def _normalize_optional_category(self, category: object) -> str | None:
        if category is None:
            return None
        if not isinstance(category, str):
            raise ValueError("category must be a string.")
        value = category.strip()
        return value or None

    def _normalize_optional_title(self, title: object) -> str | None:
        if title is None:
            return None
        if not isinstance(title, str):
            raise ValueError("title must be a string.")
        value = title.strip()
        if not value:
            raise ValueError("title must not be empty.")
        return value

    def _normalize_optional_text(self, text: object) -> str | None:
        if text is None:
            return None
        if not isinstance(text, str):
            raise ValueError("description must be a string.")
        return text.strip()

    def _parse_datetime(self, value: str, timezone: str) -> datetime:
        parsed = self._coerce_datetime(value)
        if parsed.tzinfo is not None:
            return parsed
        return parsed.replace(tzinfo=ZoneInfo(timezone))

    def _parse_optional_datetime(self, value: str | None, timezone: str) -> datetime | None:
        if value is None:
            return None
        return self._parse_datetime(value, timezone)

    def _parse_optional_datetime_value(self, value: object, timezone: object) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("datetime fields must be strings.")
        timezone_name = timezone if isinstance(timezone, str) else "UTC"
        normalized_timezone = self._normalize_timezone(timezone_name)
        return self._parse_datetime(value, normalized_timezone)

    def _coerce_datetime(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid datetime '{value}'. Use ISO 8601 format.") from exc

    def _validate_event_window(self, start_time: datetime, end_time: datetime) -> None:
        if end_time <= start_time:
            raise ValueError("end_time must be after start_time.")
        if end_time - start_time > timedelta(days=3660):
            raise ValueError("event duration is too large.")

    def _parse_attendees(self, attendees_json: str | None) -> list[AttendeeModel]:
        if not attendees_json:
            return []
        parsed = self._parse_json_value(attendees_json, field_name="attendees_json")
        return self._parse_attendees_object(parsed)

    def _parse_attendees_object(self, attendees: object) -> list[AttendeeModel] | None:
        if attendees is None:
            return None
        if not isinstance(attendees, list):
            raise ValueError("attendees must be a JSON array.")
        return [AttendeeModel.model_validate(item) for item in attendees]

    def _parse_recurrence(self, recurrence_json: str | None) -> RecurrenceRuleModel | None:
        if not recurrence_json:
            return None
        parsed = self._parse_json_value(recurrence_json, field_name="recurrence_json")
        return self._parse_recurrence_object(parsed)

    def _parse_recurrence_object(self, recurrence: object) -> RecurrenceRuleModel | None:
        if recurrence is None:
            return None
        if not isinstance(recurrence, dict):
            raise ValueError("recurrence must be a JSON object.")
        return RecurrenceRuleModel.model_validate(recurrence)

    def _parse_json_value(self, raw: str, *, field_name: str) -> object:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be valid JSON.") from exc

    def _parse_json_object(self, raw: str, *, field_name: str) -> dict[str, object]:
        value = self._parse_json_value(raw, field_name=field_name)
        if not isinstance(value, dict):
            raise ValueError(f"{field_name} must be a JSON object.")
        return value
