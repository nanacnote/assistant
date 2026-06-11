"""Builtin wellbeing tools exposed as a plugin module."""

from __future__ import annotations

from keel.core.registry import ToolRegistry

from assistant.builtin_tools.wellbeing.ports import build_wellbeing_repository
from assistant.builtin_tools.wellbeing.service import WellbeingService
from assistant.builtin_tools.wellbeing.tools import register_tools as register_wellbeing_tools


def register_tools(registry: ToolRegistry) -> None:
    """Register builtin wellbeing tools with the given registry."""
    service = WellbeingService(build_wellbeing_repository())
    register_wellbeing_tools(registry, service)
