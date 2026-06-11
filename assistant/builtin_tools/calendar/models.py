"""Domain models for calendar tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AttendeeModel(BaseModel):
    """A person associated with a calendar event."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    email: str | None = None
    status: Literal["pending", "accepted", "declined"] = "pending"


class RecurrenceRuleModel(BaseModel):
    """Structured recurrence settings aligned with RFC 5545 (RRULE)."""

    model_config = ConfigDict(extra="forbid")

    frequency: Literal["daily", "weekly", "monthly", "yearly"]
    interval: int = Field(default=1, ge=1)
    count: int | None = Field(default=None, ge=1)
    until: datetime | None = None
    by_day: list[str] | None = Field(
        default=None,
        description=(
            "Day abbreviations: MO, TU, WE, TH, FR, SA, SU. "
            "Prefix with an integer for nth weekday (e.g. 2TU = second Tuesday)."
        ),
    )
    by_month: list[int] | None = Field(default=None, description="Months 1-12.")
    by_month_day: list[int] | None = Field(
        default=None, description="Day of month 1-31 (negative from end)."
    )
    by_year_day: list[int] | None = Field(
        default=None, description="Day of year 1-366 (negative from end)."
    )

    @field_validator("by_day", mode="before")
    @classmethod
    def _normalize_by_day(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, str):
            return [value.strip()]
        if isinstance(value, list):
            return [str(v).strip() for v in value]
        return value


class EventModel(BaseModel):
    """Persisted calendar event."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str = ""
    title: str = Field(min_length=1)
    description: str = ""
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    category: str = "general"
    attendees: list[AttendeeModel] = Field(default_factory=list)
    recurrence: RecurrenceRuleModel | None = None
    reminder_minutes_before: int | None = Field(default=None, ge=1)
    created_at: datetime
    updated_at: datetime


class EventCreateRequest(BaseModel):
    """Validated request for creating an event."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = ""
    title: str = Field(min_length=1)
    description: str = ""
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    category: str = "general"
    attendees: list[AttendeeModel] = Field(default_factory=list)
    recurrence: RecurrenceRuleModel | None = None
    reminder_minutes_before: int | None = Field(default=None, ge=1)


class EventUpdateRequest(BaseModel):
    """Validated partial update for an event."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: str | None = None
    category: str | None = None
    attendees: list[AttendeeModel] | None = None
    recurrence: RecurrenceRuleModel | None = None
    reminder_minutes_before: int | None = Field(default=None, ge=1)


class EventQuery(BaseModel):
    """Query parameters for listing and searching events."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    query: str | None = None
    category: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class ReminderModel(BaseModel):
    """Reminder payload returned by the calendar service."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    title: str
    start_time: datetime
    timezone: str = "UTC"
    minutes_until_event: int = Field(ge=0)
