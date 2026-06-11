"""Procedure memory tool registrations."""

from __future__ import annotations

import json
import logging

from keel.core.registry import BaseTool, ToolRegistry, register_tool
from pydantic import Field

from assistant.memory.service import MemoryService

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from synchronous tool.execute()."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def register_tools(registry: ToolRegistry, memory_service: object) -> None:
    """Register procedure tools against the given registry."""

    svc: MemoryService = memory_service  # type: ignore[assignment]

    @register_tool(registry=registry)
    class SaveProcedure(BaseTool):
        """Save a procedure for future reference. Use when you discover a useful multi-step process."""

        tool_name = "SaveProcedure"
        _actor_field = "user_id"
        user_id: str = Field(default="", description="Owner user ID (injected automatically)")
        description: str = Field(
            description="Short task description, e.g. 'How to delete a calendar event'"
        )
        steps_json: str = Field(
            description='JSON array of step descriptions, e.g. ["Search for events", "Extract event_id", "Call DeleteEvent"]'
        )
        category: str = Field(
            default="general",
            description="Category: calendar, wellbeing, or general",
        )
        importance: float = Field(
            default=0.5,
            description="Importance 0.0-1.0",
        )

        def execute(self) -> dict[str, object]:
            try:
                steps = json.loads(self.steps_json)
            except json.JSONDecodeError:
                return {"error": "steps_json is not valid JSON"}
            if not isinstance(steps, list) or len(steps) < 1:
                return {"error": "steps_json must be a non-empty JSON array"}
            steps = [str(s).strip() for s in steps if str(s).strip()]
            if len(steps) < 1:
                return {"error": "steps must contain at least one non-empty string"}

            proc = _run_async(svc.store_procedure(
                user_id=self.user_id,
                conversation_id="",
                description=self.description,
                steps=steps,
                category=self.category,
                importance=self.importance,
            ))
            return {
                "status": "saved",
                "procedure_id": proc.id,
                "description": proc.description,
            }

    @register_tool(registry=registry)
    class PlanTask(BaseTool):
        """Look up a stored procedure to plan how to accomplish a task. Use before complex multi-step operations."""

        tool_name = "PlanTask"
        _actor_field = "user_id"
        user_id: str = Field(default="", description="Owner user ID (injected automatically)")
        task_description: str = Field(
            description="Description of the task to plan"
        )

        def execute(self) -> dict[str, object]:
            procs = _run_async(svc.get_relevant_procedures(self.user_id, self.task_description))
            if not procs:
                return {
                    "procedures": [],
                    "message": "No matching procedures found. Plan the task yourself.",
                }
            return {"procedures": procs}
