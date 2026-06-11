"""Keel tools used by the assistant runtime."""

from __future__ import annotations

import logging
from importlib import import_module

from keel.core.registry import ToolRegistry

logger = logging.getLogger(__name__)


def build_tool_registry() -> ToolRegistry:
    """Create an empty registry for module-driven tool registration."""
    return ToolRegistry()


def load_tool_modules(registry: ToolRegistry, modules: tuple[str, ...], **kwargs: object) -> None:
    """Load external tool modules and let them register against the registry.

    Each module must expose a callable `register_tools(registry: ToolRegistry, **kwargs) -> None`.
    """
    for module_path in modules:
        logger.debug("loading tool module: %s", module_path)
        module = import_module(module_path)
        register = getattr(module, "register_tools", None)
        if register is None or not callable(register):
            raise ValueError(
                f"Tool module '{module_path}' must expose callable register_tools(registry)"
            )
        register(registry, **kwargs)
        logger.debug("tool module loaded: %s", module_path)
