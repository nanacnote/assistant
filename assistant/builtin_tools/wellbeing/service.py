"""Validation and analysis service for wellbeing tools."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from assistant.builtin_tools.wellbeing.models import (
    CheckInRecord,
    CheckInRequest,
    StateLogRecord,
    StateLogRequest,
    WellbeingInsight,
    WellbeingPreferences,
    WellbeingStateSnapshot,
)
from assistant.builtin_tools.wellbeing.ports import (
    WellbeingRepository,
    WellbeingStorageNotConfiguredError,
)


class WellbeingService:
    """Application service for wellbeing tracking and trends."""

    def __init__(self, repository: WellbeingRepository):
        self.repository = repository

    def record_checkin(
        self,
        *,
        user_id: str,
        session_type: str,
        answers_json: str,
        reflection: str,
        mood: int,
        energy: int,
        stress: int,
        emotions_json: str,
        note: str,
        captured_at: str | None,
    ) -> dict[str, object]:
        normalized_user_id = self._normalize_user_id(user_id)
        request = CheckInRequest(
            session_type=self._normalize_session_type(session_type),
            answers=self._parse_answers(answers_json),
            reflection=reflection.strip(),
            state=WellbeingStateSnapshot(
                mood=mood,
                energy=energy,
                stress=stress,
                emotions=self._parse_emotions(emotions_json),
                note=note.strip(),
            ),
            captured_at=self._parse_optional_datetime(captured_at),
        )
        record = self.repository.record_checkin(normalized_user_id, request)
        return {
            "checkin": record.model_dump(mode="json"),
            "distress_detected": self._is_distress_pattern(record.state),
            "guidance": self._distress_guidance(record.state),
            "non_clinical_notice": (
                "This assistant provides reflective support and does not provide "
                "medical diagnosis or treatment."
            ),
        }

    def log_state(
        self,
        *,
        user_id: str,
        context: str,
        mood: int,
        energy: int,
        stress: int,
        emotions_json: str,
        note: str,
        captured_at: str | None,
    ) -> dict[str, object]:
        normalized_user_id = self._normalize_user_id(user_id)
        request = StateLogRequest(
            context=self._normalize_context(context),
            state=WellbeingStateSnapshot(
                mood=mood,
                energy=energy,
                stress=stress,
                emotions=self._parse_emotions(emotions_json),
                note=note.strip(),
            ),
            captured_at=self._parse_optional_datetime(captured_at),
        )
        record = self.repository.log_state(normalized_user_id, request)
        return {
            "state_log": record.model_dump(mode="json"),
            "distress_detected": self._is_distress_pattern(record.state),
            "guidance": self._distress_guidance(record.state),
        }

    def get_history(
        self,
        *,
        user_id: str,
        window: str,
        limit: int,
    ) -> dict[str, object]:
        normalized_user_id = self._normalize_user_id(user_id)
        start_time, end_time = self._window_to_range(window)
        checkins = self.repository.list_checkins(normalized_user_id, start_time, end_time, limit)
        states = self.repository.list_state_logs(normalized_user_id, start_time, end_time, limit)
        items = self._merge_history_items(checkins, states)
        return {
            "window": window,
            "count": len(items),
            "items": items[:limit],
        }

    def get_insights(self, *, user_id: str, window: str) -> dict[str, object]:
        normalized_user_id = self._normalize_user_id(user_id)
        start_time, end_time = self._window_to_range(window)
        limit = 500
        checkins = self.repository.list_checkins(normalized_user_id, start_time, end_time, limit)
        states = self.repository.list_state_logs(normalized_user_id, start_time, end_time, limit)
        insight = self._build_insight(window, checkins, states)
        return {"insight": insight.model_dump(mode="json")}

    def set_preferences(
        self,
        *,
        user_id: str,
        preferences_json: str,
    ) -> dict[str, object]:
        normalized_user_id = self._normalize_user_id(user_id)
        payload = self._parse_json_object(preferences_json, field_name="preferences_json")
        cadence = payload.get("checkin_cadence", ["wake", "mid", "sleep"])
        focus_areas = payload.get("focus_areas", [])
        tone = payload.get("tone", "reflective")
        crisis_guidance_enabled = payload.get("crisis_guidance_enabled", True)
        preferences = WellbeingPreferences(
            checkin_cadence=cadence,
            focus_areas=focus_areas,
            tone=tone,
            crisis_guidance_enabled=crisis_guidance_enabled,
            updated_at=datetime.now(timezone.utc),
        )
        saved = self.repository.set_preferences(normalized_user_id, preferences)
        return {"preferences": saved.model_dump(mode="json")}

    def describe_error(self, error: Exception) -> str:
        """Return a stable user-facing error message."""
        if isinstance(error, WellbeingStorageNotConfiguredError):
            return str(error)
        if isinstance(error, ValidationError):
            return error.errors()[0].get("msg", "Wellbeing request is invalid.")
        return str(error) or "Wellbeing request failed."

    def _normalize_user_id(self, user_id: str) -> str:
        value = user_id.strip()
        if not value:
            raise ValueError("user_id must not be empty.")
        return value

    def _normalize_session_type(self, session_type: str) -> str:
        value = session_type.strip().lower()
        if value not in {"wake", "mid", "sleep"}:
            raise ValueError("session_type must be one of: wake, mid, sleep.")
        return value

    def _normalize_context(self, context: str) -> str:
        value = context.strip().lower()
        if not value:
            return "mid"
        return value

    def _parse_optional_datetime(self, value: str | None) -> datetime:
        if value is None or not value.strip():
            return datetime.now(timezone.utc)
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError("captured_at must be ISO 8601 datetime.") from exc
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

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

    def _parse_answers(self, raw: str) -> dict[str, str]:
        value = self._parse_json_object(raw, field_name="answers_json")
        normalized: dict[str, str] = {}
        for key, answer in value.items():
            if not isinstance(key, str) or not isinstance(answer, str):
                raise ValueError("answers_json must map string keys to string values.")
            normalized[key.strip()] = answer.strip()
        return normalized

    def _parse_emotions(self, raw: str) -> list[str]:
        value = self._parse_json_value(raw, field_name="emotions_json")
        if not isinstance(value, list):
            raise ValueError("emotions_json must be a JSON array.")
        emotions: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("emotions_json items must be strings.")
            text = item.strip().lower()
            if text:
                emotions.append(text)
        return emotions

    def _window_to_range(self, window: str) -> tuple[datetime, datetime]:
        normalized = window.strip().lower()
        mapping = {
            "7d": 7,
            "14d": 14,
            "30d": 30,
            "90d": 90,
        }
        if normalized not in mapping:
            raise ValueError("window must be one of: 7d, 14d, 30d, 90d.")
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=mapping[normalized])
        return start_time, end_time

    def _merge_history_items(
        self,
        checkins: list[CheckInRecord],
        states: list[StateLogRecord],
    ) -> list[dict[str, object]]:
        checkin_items = [
            {
                "type": "checkin",
                "created_at": item.created_at.isoformat(),
                "session_type": item.session_type,
                "state": item.state.model_dump(mode="json"),
                "reflection": item.reflection,
            }
            for item in checkins
        ]
        state_items = [
            {
                "type": "state",
                "created_at": item.created_at.isoformat(),
                "context": item.context,
                "state": item.state.model_dump(mode="json"),
            }
            for item in states
        ]
        combined = checkin_items + state_items
        combined.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return combined

    def _build_insight(
        self,
        window: str,
        checkins: list[CheckInRecord],
        states: list[StateLogRecord],
    ) -> WellbeingInsight:
        snapshots = [item.state for item in checkins] + [item.state for item in states]
        if not snapshots:
            return WellbeingInsight(
                window=window,
                entry_count=0,
                trend="No entries captured in this window yet.",
                distress_detected=False,
                guidance=None,
            )

        mood_values = [item.mood for item in snapshots]
        energy_values = [item.energy for item in snapshots]
        stress_values = [item.stress for item in snapshots]

        mood_avg = sum(mood_values) / len(mood_values)
        energy_avg = sum(energy_values) / len(energy_values)
        stress_avg = sum(stress_values) / len(stress_values)

        midpoint = len(mood_values) // 2
        early = mood_values[:midpoint] or mood_values
        late = mood_values[midpoint:] or mood_values
        early_avg = sum(early) / len(early)
        late_avg = sum(late) / len(late)
        trend_delta = late_avg - early_avg

        if trend_delta > 0.5:
            trend = "Mood trend improved over the selected window."
        elif trend_delta < -0.5:
            trend = "Mood trend declined over the selected window."
        else:
            trend = "Mood trend remained fairly stable over the selected window."

        distress_detected = any(self._is_distress_pattern(snapshot) for snapshot in snapshots)
        guidance = self._distress_guidance(snapshots[-1]) if distress_detected else None

        return WellbeingInsight(
            window=window,
            entry_count=len(snapshots),
            average_mood=round(mood_avg, 2),
            average_energy=round(energy_avg, 2),
            average_stress=round(stress_avg, 2),
            trend=trend,
            distress_detected=distress_detected,
            guidance=guidance,
        )

    def _is_distress_pattern(self, state: WellbeingStateSnapshot) -> bool:
        low_mood = state.mood <= 3
        high_stress = state.stress >= 8
        flagged_emotions = {"hopeless", "panic", "despair", "overwhelmed", "numb"}
        has_flagged_emotion = any(item in flagged_emotions for item in state.emotions)
        return low_mood or high_stress or has_flagged_emotion

    def _distress_guidance(self, state: WellbeingStateSnapshot) -> str | None:
        if not self._is_distress_pattern(state):
            return None
        return (
            "You may be carrying a heavy emotional load right now. If you feel "
            "unsafe or at risk, contact local emergency services or a trusted "
            "person immediately."
        )
