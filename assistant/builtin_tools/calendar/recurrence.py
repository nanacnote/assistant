"""RFC 5545 recurrence expansion using dateutil.rrule."""

from __future__ import annotations

from datetime import datetime

from dateutil.rrule import (
    FR,
    MO,
    SA,
    SU,
    TH,
    TU,
    WE,
    WEEKLY,
    YEARLY,
    rrule,
    weekday,
)

from assistant.builtin_tools.calendar.models import EventModel

_DAY_ABBREVIATIONS: dict[str, weekday] = {
    "MO": MO,
    "TU": TU,
    "WE": WE,
    "TH": TH,
    "FR": FR,
    "SA": SA,
    "SU": SU,
}

_FREQ_MAP: dict[str, int] = {
    "daily": 3,  # dateutil.rrule.DAILY
    "weekly": WEEKLY,
    "monthly": 1,  # dateutil.rrule.MONTHLY
    "yearly": YEARLY,
}

_MAX_OCCURRENCES = 1000


def expand_recurrence(
    event: EventModel,
    window_start: datetime,
    window_end: datetime,
) -> list[EventModel]:
    """Return virtual EventModel instances for a recurring event within the window.

    Non-recurring events that overlap the window are returned as-is.
    Recurring events generate occurrences based on their RFC 5545 recurrence rule.
    Returns an empty list if the event doesn't overlap the window at all.
    """
    if event.recurrence is None:
        if event.end_time > window_start and event.start_time < window_end:
            return [event]
        return []

    duration = event.end_time - event.start_time
    rule = event.recurrence

    rrule_kwargs: dict[str, object] = {
        "freq": _FREQ_MAP[rule.frequency],
        "dtstart": event.start_time,
        "interval": rule.interval,
    }

    by_weekday = _build_by_weekday(rule.by_day)
    if by_weekday is not None:
        rrule_kwargs["byweekday"] = by_weekday
    if rule.by_month:
        rrule_kwargs["bymonth"] = rule.by_month
    if rule.by_month_day:
        rrule_kwargs["bymonthday"] = rule.by_month_day
    if rule.by_year_day:
        rrule_kwargs["byyearday"] = rule.by_year_day
    if rule.count is not None:
        rrule_kwargs["count"] = min(rule.count, _MAX_OCCURRENCES)
    if rule.until is not None:
        rrule_kwargs["until"] = rule.until

    # Always cap iteration to avoid unbounded expansion.
    if rule.count is None and rule.until is None:
        rrule_kwargs["count"] = _MAX_OCCURRENCES

    recurrences = rrule(**rrule_kwargs)

    occurrences: list[EventModel] = []
    for index, dt in enumerate(recurrences):
        current_start = dt
        current_end = current_start + duration

        if rule.until and current_start > rule.until:
            break
        if rule.count is not None and index >= rule.count:
            break

        if current_end > window_start and current_start < window_end:
            occurrences.append(
                _make_occurrence(event, current_start, current_end, index)
            )

        if current_start >= window_end:
            break

    return occurrences


def _build_by_weekday(by_day: list[str] | None) -> list[weekday] | None:
    if not by_day:
        return None
    result: list[weekday] = []
    for day_str in by_day:
        day_str = day_str.strip().upper()
        if not day_str:
            continue
        if len(day_str) > 2 and day_str[0].isdigit():
            n = int(day_str[0])
            abbrev = day_str[1:]
            if abbrev in _DAY_ABBREVIATIONS:
                result.append(weekday(_DAY_ABBREVIATIONS[abbrev].weekday, n))
        elif day_str in _DAY_ABBREVIATIONS:
            result.append(_DAY_ABBREVIATIONS[day_str])
    return result or None


def _make_occurrence(
    base: EventModel,
    start: datetime,
    end: datetime,
    index: int,
) -> EventModel:
    return EventModel(
        id=f"{base.id}#occurrence-{index}",
        user_id=base.user_id,
        title=base.title,
        description=base.description,
        start_time=start,
        end_time=end,
        timezone=base.timezone,
        category=base.category,
        attendees=base.attendees,
        recurrence=base.recurrence,
        reminder_minutes_before=base.reminder_minutes_before,
        created_at=base.created_at,
        updated_at=base.updated_at,
    )
