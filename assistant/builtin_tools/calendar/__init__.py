"""Builtin calendar tools exposed as a plugin module."""

from __future__ import annotations

from keel.core.registry import ToolRegistry

from assistant.builtin_tools.calendar.ports import build_calendar_repository
from assistant.builtin_tools.calendar.service import CalendarService
from assistant.builtin_tools.calendar.tools import register_tools as register_calendar_tools


def register_tools(registry: ToolRegistry) -> None:
    """Register builtin calendar tools with the given registry."""
    service = CalendarService(build_calendar_repository())
    register_calendar_tools(registry, service)
