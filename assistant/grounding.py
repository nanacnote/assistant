"""Grounding context for LLM prompts.

Provides temporal and environmental awareness so the LLM can reason about
relative time references ("tomorrow", "next Monday") and know its own identity.
"""

from __future__ import annotations

from datetime import datetime, timezone


def build_grounding_context(*, model: str = "", actor_id: str = "") -> str:
    """Build a grounding block for injection into LLM prompts.

    Args:
        model: The LLM model name (e.g. "gpt-4o").
        actor_id: The Matrix user ID (e.g. "@alice:matrix.org").

    Returns:
        A multi-line grounding block with current date/time, optional user,
        and optional model identity.
    """
    now = datetime.now(timezone.utc)
    day_of_week = now.strftime("%A")
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [f"Current date and time: {timestamp} ({day_of_week})"]
    if actor_id:
        lines.append(f"User: {actor_id}")
    if model:
        lines.append(f"Model: {model}")
    return "\n".join(lines)
