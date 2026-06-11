"""Interaction tool registrations."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from keel.core.registry import BaseTool, ToolRegistry, register_tool
from pydantic import Field

from assistant.interaction.ports import PendingQuestion, PendingQuestionRepository

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


def _get_request_context() -> tuple[str, str, str, list[tuple[int, str, str]]]:
    """Read the current request's context from thread-local context."""
    import assistant.runtime as _runtime

    ctx = getattr(_runtime, "_tool_context", None)
    if ctx is None:
        return "", "", "", []
    room_id = getattr(ctx, "room_id", "")
    thread_root = getattr(ctx, "thread_root_event_id", "")
    original_prompt = getattr(ctx, "original_prompt", "")
    tool_history = getattr(ctx, "tool_history", [])
    return str(room_id), str(thread_root), str(original_prompt), list(tool_history)


def _get_active_request_id() -> str:
    """Read the active request ID from thread-local context."""
    import assistant.runtime as _runtime

    ctx = getattr(_runtime, "_tool_context", None)
    if ctx is None:
        return ""
    return getattr(ctx, "active_request_id", "")


def register_tools(
    registry: ToolRegistry,
    matrix_client: object,
    pending_question_repo: PendingQuestionRepository,
    request_metadata: dict[str, dict[str, str]],
) -> None:
    """Register interaction tools against the given registry."""

    @register_tool(registry=registry)
    class AskUser(BaseTool):
        """Ask the user a clarifying question before proceeding.

        Use when you need more information to complete a task.
        """

        tool_name = "AskUser"
        tool_role = "meta"
        question: str = Field(
            description="The clarifying question to ask the user"
        )
        room_id: str = Field(
            description="The Matrix room ID to send the question to (e.g. '!abc:example.com')"
        )

        def execute(self) -> dict[str, object]:
            room = self.room_id.strip()
            _, thread_root, original_prompt, tool_history = _get_request_context()

            question_id = str(uuid.uuid4())

            try:
                send_kwargs: dict[str, object] = {}
                if thread_root:
                    send_kwargs["thread_root_event_id"] = thread_root
                _run_async(matrix_client.send_text(room, self.question, **send_kwargs))
                logger.info(
                    "AskUser: sent question to room %s thread=%s, question_id=%s",
                    room, thread_root or "(none)", question_id,
                )
            except Exception as exc:
                logger.error("AskUser: failed to send question: %s", exc)
                return {"answer": None, "error": str(exc)}

            pending = PendingQuestion(
                id=question_id,
                room_id=room,
                thread_root=thread_root,
                question=self.question,
                original_prompt=original_prompt,
                tool_history=tool_history,
                request_metadata=request_metadata.get(_get_active_request_id(), {}),
                created_at=datetime.now(timezone.utc),
            )

            try:
                pending_question_repo.save(pending)
                logger.info("AskUser: persisted question %s to database", question_id)
            except Exception as exc:
                logger.error("AskUser: failed to persist question: %s", exc)
                return {"answer": None, "error": f"Failed to persist question: {exc}"}

            return {"__ask_user_waiting": True, "question_id": question_id}
