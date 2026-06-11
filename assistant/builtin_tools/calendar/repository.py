"""PostgreSQL implementation of CalendarRepository."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from psycopg import Connection

from assistant.builtin_tools.calendar.models import (
    AttendeeModel,
    EventCreateRequest,
    EventModel,
    EventQuery,
    EventUpdateRequest,
    RecurrenceRuleModel,
    ReminderModel,
)


class PostgresCalendarRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def _rollback_on_error(self) -> None:
        try:
            self._conn.rollback()
        except Exception:
            pass

    def create_event(self, request: EventCreateRequest) -> EventModel:
        try:
            now = datetime.now(timezone.utc)
            event_id = str(uuid.uuid4())
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO calendar_events
                        (id, user_id, title, description, start_time, end_time, timezone,
                         category, attendees, recurrence, reminder_minutes_before,
                         created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event_id,
                        request.user_id,
                        request.title,
                        request.description,
                        request.start_time,
                        request.end_time,
                        request.timezone,
                        request.category,
                        [a.model_dump(mode="json") for a in request.attendees],
                        json.dumps(request.recurrence.model_dump(mode="json"))
                        if request.recurrence
                        else None,
                        request.reminder_minutes_before,
                        now,
                        now,
                    ),
                )
                cur.execute("SELECT * FROM calendar_events WHERE id = %s", (event_id,))
                row = cur.fetchone()
            self._conn.commit()
            return self._row_to_model(row)
        except Exception:
            self._rollback_on_error()
            raise

    def get_event(self, event_id: str) -> EventModel | None:
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT * FROM calendar_events WHERE id = %s", (event_id,))
                row = cur.fetchone()
            return self._row_to_model(row) if row else None
        except Exception:
            self._rollback_on_error()
            raise

    def list_events(self, query: EventQuery) -> list[EventModel]:
        clauses: list[str] = ["user_id = %s"]
        params: list[object] = [query.user_id]
        if query.start_time:
            clauses.append("end_time >= %s")
            params.append(query.start_time)
        if query.end_time:
            clauses.append("start_time <= %s")
            params.append(query.end_time)
        if query.category:
            clauses.append("category = %s")
            params.append(query.category)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(query.limit)

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM calendar_events {where} ORDER BY start_time ASC LIMIT %s",
                    params,
                )
                rows = cur.fetchall()
            return [self._row_to_model(r) for r in rows]
        except Exception:
            self._rollback_on_error()
            raise

    def search_events(self, query: EventQuery) -> list[EventModel]:
        clauses: list[str] = ["user_id = %s"]
        params: list[object] = [query.user_id]
        if query.query:
            clauses.append("(title ILIKE %s OR description ILIKE %s)")
            like = f"%{query.query}%"
            params.extend([like, like])
        if query.start_time:
            clauses.append("end_time >= %s")
            params.append(query.start_time)
        if query.end_time:
            clauses.append("start_time <= %s")
            params.append(query.end_time)
        if query.category:
            clauses.append("category = %s")
            params.append(query.category)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(query.limit)

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM calendar_events {where} ORDER BY start_time ASC LIMIT %s",
                    params,
                )
                rows = cur.fetchall()
            return [self._row_to_model(r) for r in rows]
        except Exception:
            self._rollback_on_error()
            raise

    def update_event(self, event_id: str, request: EventUpdateRequest) -> EventModel:
        existing = self.get_event(event_id)
        if existing is None:
            raise ValueError(f"No event found for id '{event_id}'.")

        updates = {
            k: v for k, v in request.model_dump(exclude_unset=True).items() if v is not None
        }
        updated = existing.model_copy(update=updates)
        now = datetime.now(timezone.utc)

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE calendar_events SET
                        title = %s,
                        description = %s,
                        start_time = %s,
                        end_time = %s,
                        timezone = %s,
                        category = %s,
                        attendees = %s,
                        recurrence = %s,
                        reminder_minutes_before = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        updated.title,
                        updated.description,
                        updated.start_time,
                        updated.end_time,
                        updated.timezone,
                        updated.category,
                        [a.model_dump(mode="json") for a in updated.attendees],
                        json.dumps(updated.recurrence.model_dump(mode="json"))
                        if updated.recurrence
                        else None,
                        updated.reminder_minutes_before,
                        now,
                        event_id,
                    ),
                )
                cur.execute("SELECT * FROM calendar_events WHERE id = %s", (event_id,))
                row = cur.fetchone()
            self._conn.commit()
            return self._row_to_model(row)
        except Exception:
            self._rollback_on_error()
            raise

    def delete_event(self, event_id: str) -> bool:
        try:
            with self._conn.cursor() as cur:
                cur.execute("DELETE FROM calendar_events WHERE id = %s", (event_id,))
                deleted = cur.rowcount > 0
            self._conn.commit()
            return deleted
        except Exception:
            self._rollback_on_error()
            raise

    def get_reminders(self, within_minutes: int, user_id: str) -> list[ReminderModel]:
        try:
            now = datetime.now(timezone.utc)
            window_end = now + timedelta(minutes=within_minutes)
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, start_time, timezone
                    FROM calendar_events
                    WHERE user_id = %s
                      AND reminder_minutes_before IS NOT NULL
                      AND start_time >= %s
                      AND start_time <= %s
                    ORDER BY start_time ASC
                    """,
                    (user_id, now, window_end),
                )
                rows = cur.fetchall()

            result: list[ReminderModel] = []
            for row in rows:
                start = _to_datetime(row["start_time"])
                delta = int((start - now).total_seconds() / 60)
                result.append(
                    ReminderModel(
                        event_id=row["id"],
                        title=row["title"],
                        start_time=start,
                        timezone=row["timezone"],
                        minutes_until_event=max(0, delta),
                    )
                )
            return result
        except Exception:
            self._rollback_on_error()
            raise

    def list_recurring_events(
        self, user_id: str, before: datetime, category: str | None = None
    ) -> list[EventModel]:
        try:
            clauses = ["user_id = %s", "recurrence IS NOT NULL", "start_time <= %s"]
            params: list[object] = [user_id, before]
            if category:
                clauses.append("category = %s")
                params.append(category)
            where = f"WHERE {' AND '.join(clauses)}"
            with self._conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM calendar_events {where} ORDER BY start_time ASC",
                    params,
                )
                rows = cur.fetchall()
            return [self._row_to_model(r) for r in rows]
        except Exception:
            self._rollback_on_error()
            raise

    def list_events_with_reminders(self, user_id: str) -> list[EventModel]:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM calendar_events
                    WHERE user_id = %s AND reminder_minutes_before IS NOT NULL
                    ORDER BY start_time ASC
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
            return [self._row_to_model(r) for r in rows]
        except Exception:
            self._rollback_on_error()
            raise

    def _row_to_model(self, row: dict[str, object]) -> EventModel:
        attendees = [AttendeeModel(**item) for item in row["attendees"]]
        recurrence_raw = row["recurrence"]
        recurrence = RecurrenceRuleModel(**recurrence_raw) if recurrence_raw else None
        return EventModel(
            id=row["id"],
            user_id=row.get("user_id", ""),
            title=row["title"],
            description=row["description"],
            start_time=_to_datetime(row["start_time"]),
            end_time=_to_datetime(row["end_time"]),
            timezone=row["timezone"],
            category=row["category"],
            attendees=attendees,
            recurrence=recurrence,
            reminder_minutes_before=row["reminder_minutes_before"],
            created_at=_to_datetime(row["created_at"]),
            updated_at=_to_datetime(row["updated_at"]),
        )


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
