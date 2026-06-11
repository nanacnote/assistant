"""Domain models for wellbeing coaching tools."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WellbeingStateSnapshot(BaseModel):
    """A normalized emotional state snapshot."""

    model_config = ConfigDict(extra="forbid")

    mood: int = Field(ge=1, le=10)
    energy: int = Field(ge=1, le=10)
    stress: int = Field(ge=1, le=10)
    emotions: list[str] = Field(default_factory=list)
    note: str = ""


class CheckInRequest(BaseModel):
    """Validated request for a check-in session."""

    model_config = ConfigDict(extra="forbid")

    session_type: Literal["wake", "mid", "sleep"]
    answers: dict[str, str] = Field(default_factory=dict)
    reflection: str = ""
    state: WellbeingStateSnapshot
    captured_at: datetime


class StateLogRequest(BaseModel):
    """Validated request for a quick wellbeing state log."""

    model_config = ConfigDict(extra="forbid")

    context: str = "mid"
    state: WellbeingStateSnapshot
    captured_at: datetime


class CheckInRecord(BaseModel):
    """Persisted check-in record."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    session_type: Literal["wake", "mid", "sleep"]
    answers: dict[str, str] = Field(default_factory=dict)
    reflection: str = ""
    state: WellbeingStateSnapshot
    captured_at: datetime
    created_at: datetime


class StateLogRecord(BaseModel):
    """Persisted state log record."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    context: str
    state: WellbeingStateSnapshot
    captured_at: datetime
    created_at: datetime


class WellbeingPreferences(BaseModel):
    """User preferences for wellbeing coaching behavior."""

    model_config = ConfigDict(extra="forbid")

    checkin_cadence: list[Literal["wake", "mid", "sleep"]] = Field(
        default_factory=lambda: ["wake", "mid", "sleep"]
    )
    focus_areas: list[str] = Field(default_factory=list)
    tone: Literal["reflective", "supportive", "balanced"] = "reflective"
    crisis_guidance_enabled: bool = True
    updated_at: datetime


class WellbeingInsight(BaseModel):
    """Computed wellbeing trend insight."""

    model_config = ConfigDict(extra="forbid")

    window: str
    entry_count: int
    average_mood: float | None = None
    average_energy: float | None = None
    average_stress: float | None = None
    trend: str
    distress_detected: bool = False
    guidance: str | None = None
