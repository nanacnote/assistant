"""Reply tool: return the final assistant response."""

from __future__ import annotations

from keel.core.registry import BaseTool, ToolRegistry, register_tool
from pydantic import Field


def register_tools(registry: ToolRegistry) -> None:
    """Register builtin tools with the given registry."""

    @register_tool(registry=registry)
    class Reply(BaseTool):
        """Return the final assistant reply."""

        tool_name = "Reply"
        tool_role = "meta"
        text: str = Field(description="Final assistant response text")

        def execute(self) -> str:
            return self.text
