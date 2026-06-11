"""Builtin interaction tools exposed as a plugin module."""

from __future__ import annotations

from keel.core.registry import ToolRegistry

from assistant.builtin_tools.interaction.tools import register_tools as register_interaction_tools
from assistant.interaction.ports import PendingQuestionRepository


def register_tools(
    registry: ToolRegistry,
    *,
    matrix_client: object = None,
    pending_question_repo: PendingQuestionRepository = None,
    request_metadata: object = None,
    **_kwargs: object,
) -> None:
    """Register builtin interaction tools with the given registry."""
    if (
        matrix_client is not None
        and pending_question_repo is not None
        and request_metadata is not None
    ):
        register_interaction_tools(
            registry, matrix_client, pending_question_repo, request_metadata
        )
