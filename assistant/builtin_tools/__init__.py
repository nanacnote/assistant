"""Builtin assistant tools provided as a default plugin module."""

from __future__ import annotations

from keel.core.registry import ToolRegistry

from assistant.builtin_tools.calendar import register_tools as register_calendar_tools
from assistant.builtin_tools.reply import register_tools as register_reply_tools
from assistant.builtin_tools.wellbeing import register_tools as register_wellbeing_tools


def register_tools(registry: ToolRegistry, *, memory_service: object = None, **kwargs: object) -> None:
    """Register all builtin tools with the given registry."""
    register_reply_tools(registry)
    register_calendar_tools(registry)
    register_wellbeing_tools(registry)
    if memory_service is not None:
        from assistant.builtin_tools.procedures import register_tools as register_procedure_tools

        register_procedure_tools(registry, memory_service)
    from assistant.builtin_tools.interaction import register_tools as register_interaction_tools

    register_interaction_tools(registry, **kwargs)


__all__ = ["register_tools"]
