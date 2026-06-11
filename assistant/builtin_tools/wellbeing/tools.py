"""Wellbeing coaching tool registrations."""

from __future__ import annotations

from keel.core.registry import BaseTool, ToolRegistry, register_tool
from pydantic import Field

from assistant.builtin_tools.wellbeing.service import WellbeingService


def register_tools(registry: ToolRegistry, service: WellbeingService) -> None:
    """Register wellbeing tools against the given registry."""

    @register_tool(registry=registry)
    class RecordCheckIn(BaseTool):
        """Record a short structured check-in for wake, mid, or sleep sessions."""

        tool_name = "RecordCheckIn"
        usage_hint = "Use when starting or ending a structured wellness session"
        _actor_field = "user_id"
        user_id: str = Field(description="User identifier, typically the Matrix actor_id")
        session_type: str = Field(description="One of: wake, mid, sleep")
        answers_json: str = Field(
            default="{}",
            description="JSON object containing question/answer pairs from the check-in",
        )
        reflection: str = Field(default="", description="Optional free reflection text")
        mood: int = Field(description="Mood score from 1 to 10")
        energy: int = Field(description="Energy score from 1 to 10")
        stress: int = Field(description="Stress score from 1 to 10")
        emotions_json: str = Field(
            default="[]",
            description="JSON array of emotion tags like calm, anxious, grateful",
        )
        note: str = Field(default="", description="Optional short note")
        captured_at: str | None = Field(
            default=None,
            description="Optional capture timestamp in ISO 8601 format",
        )

        def execute(self) -> dict[str, object]:
            try:
                return service.record_checkin(
                    user_id=self.user_id,
                    session_type=self.session_type,
                    answers_json=self.answers_json,
                    reflection=self.reflection,
                    mood=self.mood,
                    energy=self.energy,
                    stress=self.stress,
                    emotions_json=self.emotions_json,
                    note=self.note,
                    captured_at=self.captured_at,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}

    @register_tool(registry=registry)
    class LogState(BaseTool):
        """Log a quick mental-emotional state snapshot."""

        tool_name = "LogState"
        usage_hint = "Use when the user provides numerical ratings or describes their emotional state"
        _actor_field = "user_id"
        user_id: str = Field(description="User identifier, typically the Matrix actor_id")
        context: str = Field(
            default="mid",
            description="Short context label such as wake, mid, sleep, or work",
        )
        mood: int = Field(description="Mood score from 1 to 10")
        energy: int = Field(description="Energy score from 1 to 10")
        stress: int = Field(description="Stress score from 1 to 10")
        emotions_json: str = Field(
            default="[]",
            description="JSON array of emotion tags like focused, drained, hopeful",
        )
        note: str = Field(default="", description="Optional short note")
        captured_at: str | None = Field(
            default=None,
            description="Optional capture timestamp in ISO 8601 format",
        )

        def execute(self) -> dict[str, object]:
            try:
                return service.log_state(
                    user_id=self.user_id,
                    context=self.context,
                    mood=self.mood,
                    energy=self.energy,
                    stress=self.stress,
                    emotions_json=self.emotions_json,
                    note=self.note,
                    captured_at=self.captured_at,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}

    @register_tool(registry=registry)
    class GetHistory(BaseTool):
        """Retrieve recent check-ins and state logs for a user."""

        tool_name = "GetHistory"
        _actor_field = "user_id"
        user_id: str = Field(description="User identifier, typically the Matrix actor_id")
        window: str = Field(default="14d", description="One of: 7d, 14d, 30d, 90d")
        limit: int = Field(default=50, description="Maximum number of entries to return")

        def execute(self) -> dict[str, object]:
            try:
                return service.get_history(
                    user_id=self.user_id,
                    window=self.window,
                    limit=self.limit,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}

    @register_tool(registry=registry)
    class GetInsights(BaseTool):
        """Summarize wellbeing trends from recent entries."""

        tool_name = "GetInsights"
        usage_hint = "Use before giving advice to ground recommendations in actual data"
        _actor_field = "user_id"
        user_id: str = Field(description="User identifier, typically the Matrix actor_id")
        window: str = Field(default="30d", description="One of: 7d, 14d, 30d, 90d")

        def execute(self) -> dict[str, object]:
            try:
                return service.get_insights(user_id=self.user_id, window=self.window)
            except Exception as exc:
                return {"error": service.describe_error(exc)}

    @register_tool(registry=registry)
    class SetWellbeingPreferences(BaseTool):
        """Save user preferences for wellbeing coaching."""

        tool_name = "SetWellbeingPreferences"
        _actor_field = "user_id"
        user_id: str = Field(description="User identifier, typically the Matrix actor_id")
        preferences_json: str = Field(
            description=(
                "JSON object with checkin_cadence, focus_areas, tone, and "
                "crisis_guidance_enabled"
            ),
        )

        def execute(self) -> dict[str, object]:
            try:
                return service.set_preferences(
                    user_id=self.user_id,
                    preferences_json=self.preferences_json,
                )
            except Exception as exc:
                return {"error": service.describe_error(exc)}
