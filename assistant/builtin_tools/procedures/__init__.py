"""Builtin procedure memory tools exposed as a plugin module."""

from __future__ import annotations

from keel.core.registry import ToolRegistry

from assistant.builtin_tools.procedures.tools import register_tools as register_procedure_tools


def register_tools(registry: ToolRegistry, memory_service: object) -> None:
    """Register builtin procedure tools with the given registry."""
    register_procedure_tools(registry, memory_service)
