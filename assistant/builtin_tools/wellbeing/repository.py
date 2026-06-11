"""PostgreSQL implementation of WellbeingRepository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from psycopg import Connection

from assistant.builtin_tools.wellbeing.models import (
    CheckInRecord,
    CheckInRequest,
    StateLogRecord,
    StateLogRequest,
    WellbeingPreferences,
    WellbeingStateSnapshot,
)


class PostgresWellbeingRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def record_checkin(self, user_id: str, request: CheckInRequest) -> CheckInRecord:
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO wellbeing_checkins
                    (id, user_id, session_type, answers, reflection,
                     mood, energy, stress, emotions, note, captured_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record_id,
                    user_id,
                    request.session_type,
                    request.answers,
                    request.reflection,
                    request.state.mood,
                    request.state.energy,
                    request.state.stress,
                    request.state.emotions,
                    request.state.note,
                    request.captured_at,
                    now,
                ),
            )
        self._conn.commit()
        return CheckInRecord(
            id=record_id,
            user_id=user_id,
            session_type=request.session_type,
            answers=request.answers,
            reflection=request.reflection,
            state=request.state,
            captured_at=request.captured_at,
            created_at=now,
        )

    def log_state(self, user_id: str, request: StateLogRequest) -> StateLogRecord:
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO wellbeing_state_logs
                    (id, user_id, context, mood, energy, stress,
                     emotions, note, captured_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record_id,
                    user_id,
                    request.context,
                    request.state.mood,
                    request.state.energy,
                    request.state.stress,
                    request.state.emotions,
                    request.state.note,
                    request.captured_at,
                    now,
                ),
            )
        self._conn.commit()
        return StateLogRecord(
            id=record_id,
            user_id=user_id,
            context=request.context,
            state=request.state,
            captured_at=request.captured_at,
            created_at=now,
        )

    def list_checkins(
        self, user_id: str, start_time: datetime, end_time: datetime, limit: int
    ) -> list[CheckInRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM wellbeing_checkins
                WHERE user_id = %s AND captured_at >= %s AND captured_at <= %s
                ORDER BY captured_at DESC LIMIT %s
                """,
                (user_id, start_time, end_time, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_checkin(row) for row in rows]

    def list_state_logs(
        self, user_id: str, start_time: datetime, end_time: datetime, limit: int
    ) -> list[StateLogRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM wellbeing_state_logs
                WHERE user_id = %s AND captured_at >= %s AND captured_at <= %s
                ORDER BY captured_at DESC LIMIT %s
                """,
                (user_id, start_time, end_time, limit),
            )
            rows = cur.fetchall()
        return [self._row_to_state_log(row) for row in rows]

    def set_preferences(
        self,
        user_id: str,
        preferences: WellbeingPreferences,
    ) -> WellbeingPreferences:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO wellbeing_preferences
                    (user_id, checkin_cadence, focus_areas, tone,
                     crisis_guidance_enabled, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(user_id) DO UPDATE SET
                    checkin_cadence = EXCLUDED.checkin_cadence,
                    focus_areas = EXCLUDED.focus_areas,
                    tone = EXCLUDED.tone,
                    crisis_guidance_enabled = EXCLUDED.crisis_guidance_enabled,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    user_id,
                    preferences.checkin_cadence,
                    preferences.focus_areas,
                    preferences.tone,
                    preferences.crisis_guidance_enabled,
                    preferences.updated_at,
                ),
            )
        self._conn.commit()
        return preferences

    def get_preferences(self, user_id: str) -> WellbeingPreferences | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM wellbeing_preferences WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return WellbeingPreferences(
            checkin_cadence=row["checkin_cadence"],
            focus_areas=row["focus_areas"],
            tone=row["tone"],
            crisis_guidance_enabled=bool(row["crisis_guidance_enabled"]),
            updated_at=_to_datetime(row["updated_at"]),
        )

    def _row_to_checkin(self, row: dict[str, object]) -> CheckInRecord:
        return CheckInRecord(
            id=row["id"],
            user_id=row["user_id"],
            session_type=row["session_type"],
            answers=row["answers"],
            reflection=row["reflection"],
            state=WellbeingStateSnapshot(
                mood=row["mood"],
                energy=row["energy"],
                stress=row["stress"],
                emotions=row["emotions"],
                note=row["note"],
            ),
            captured_at=_to_datetime(row["captured_at"]),
            created_at=_to_datetime(row["created_at"]),
        )

    def _row_to_state_log(self, row: dict[str, object]) -> StateLogRecord:
        return StateLogRecord(
            id=row["id"],
            user_id=row["user_id"],
            context=row["context"],
            state=WellbeingStateSnapshot(
                mood=row["mood"],
                energy=row["energy"],
                stress=row["stress"],
                emotions=row["emotions"],
                note=row["note"],
            ),
            captured_at=_to_datetime(row["captured_at"]),
            created_at=_to_datetime(row["created_at"]),
        )


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
