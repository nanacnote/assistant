"""Tests for wellbeing coaching tools and service boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from assistant.builtin_tools.wellbeing import register_tools as register_wellbeing_tools
from assistant.builtin_tools.wellbeing.models import (
    CheckInRecord,
    CheckInRequest,
    StateLogRecord,
    StateLogRequest,
    WellbeingPreferences,
    WellbeingStateSnapshot,
)
from assistant.builtin_tools.wellbeing.ports import UnconfiguredWellbeingRepository
from assistant.builtin_tools.wellbeing.service import WellbeingService
from assistant.builtin_tools.wellbeing.tools import (
    register_tools as register_wellbeing_tool_classes,
)
from assistant.tools import build_tool_registry


class FakeWellbeingRepository:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        snapshot = WellbeingStateSnapshot(mood=6, energy=5, stress=4, emotions=["focused"], note="")
        self.checkins = [
            CheckInRecord(
                id="c1",
                user_id="u1",
                session_type="wake",
                answers={"intent": "stay calm"},
                reflection="steady start",
                state=snapshot,
                captured_at=now,
                created_at=now,
            )
        ]
        self.state_logs = [
            StateLogRecord(
                id="s1",
                user_id="u1",
                context="mid",
                state=snapshot,
                captured_at=now,
                created_at=now,
            )
        ]
        self.preferences = WellbeingPreferences(
            checkin_cadence=["wake", "mid", "sleep"],
            focus_areas=["mood", "stress"],
            tone="reflective",
            crisis_guidance_enabled=True,
            updated_at=now,
        )

    def record_checkin(self, user_id: str, request: CheckInRequest) -> CheckInRecord:
        now = datetime.now(timezone.utc)
        record = CheckInRecord(
            id=f"c{len(self.checkins) + 1}",
            user_id=user_id,
            session_type=request.session_type,
            answers=request.answers,
            reflection=request.reflection,
            state=request.state,
            captured_at=request.captured_at,
            created_at=now,
        )
        self.checkins.append(record)
        return record

    def log_state(self, user_id: str, request: StateLogRequest) -> StateLogRecord:
        now = datetime.now(timezone.utc)
        record = StateLogRecord(
            id=f"s{len(self.state_logs) + 1}",
            user_id=user_id,
            context=request.context,
            state=request.state,
            captured_at=request.captured_at,
            created_at=now,
        )
        self.state_logs.append(record)
        return record

    def list_checkins(
        self, user_id: str, start_time: datetime, end_time: datetime, limit: int
    ) -> list[CheckInRecord]:
        del start_time, end_time
        return [item for item in self.checkins if item.user_id == user_id][:limit]

    def list_state_logs(
        self, user_id: str, start_time: datetime, end_time: datetime, limit: int
    ) -> list[StateLogRecord]:
        del start_time, end_time
        return [item for item in self.state_logs if item.user_id == user_id][:limit]

    def set_preferences(
        self,
        user_id: str,
        preferences: WellbeingPreferences,
    ) -> WellbeingPreferences:
        del user_id
        self.preferences = preferences
        return preferences

    def get_preferences(self, user_id: str) -> WellbeingPreferences | None:
        del user_id
        return self.preferences


def test_wellbeing_tools_register() -> None:
    registry = build_tool_registry()
    register_wellbeing_tools(registry)

    assert registry.get("RecordCheckIn") is not None
    assert registry.get("LogState") is not None
    assert registry.get("GetHistory") is not None
    assert registry.get("GetInsights") is not None
    assert registry.get("SetWellbeingPreferences") is not None


def test_wellbeing_service_record_and_insight_flow() -> None:
    service = WellbeingService(FakeWellbeingRepository())

    recorded = service.record_checkin(
        user_id="u1",
        session_type="sleep",
        answers_json='{"wins":"kept focus"}',
        reflection="good wind down",
        mood=7,
        energy=4,
        stress=3,
        emotions_json='["grateful", "calm"]',
        note="",
        captured_at=None,
    )
    insights = service.get_insights(user_id="u1", window="14d")

    assert recorded["checkin"]["session_type"] == "sleep"
    assert recorded["non_clinical_notice"]
    assert insights["insight"]["entry_count"] >= 1


def test_wellbeing_tool_execution_with_injected_service() -> None:
    service = WellbeingService(FakeWellbeingRepository())
    registry = build_tool_registry()

    register_wellbeing_tool_classes(registry, service)
    tool_cls = cast(Any, registry.get("LogState"))
    result = tool_cls(
        user_id="u1",
        context="mid",
        mood=6,
        energy=5,
        stress=4,
        emotions_json='["focused"]',
        note="keeping balance",
        captured_at=None,
    ).execute()

    assert result["state_log"]["user_id"] == "u1"


def test_wellbeing_unconfigured_storage_error_is_clear() -> None:
    service = WellbeingService(UnconfiguredWellbeingRepository())
    registry = build_tool_registry()

    register_wellbeing_tool_classes(registry, service)
    tool_cls = cast(Any, registry.get("GetInsights"))
    result = tool_cls(user_id="u1", window="14d").execute()

    assert result == {
        "error": (
            "Wellbeing storage is not configured yet. Plug in the shared "
            "wellbeing repository to enable tracking and analysis."
        )
    }
