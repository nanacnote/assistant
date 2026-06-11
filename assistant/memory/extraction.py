"""LLM-based fact extraction from conversation turns."""

from __future__ import annotations

import json
import logging
from typing import Callable

from assistant.memory.models import ExtractedFact, ExtractedProcedure

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = (
    "You are a memory extraction assistant. Given a short conversation "
    "exchange between a user and an assistant, extract key facts, "
    "preferences, instructions, or events that would be useful to "
    "remember for future conversations.\n\n"
    'Return a JSON array of objects, each with:\n'
    '- "text": a concise fact (1-2 sentences)\n'
    '- "category": one of "preference", "fact", "event", "relationship", '
    '"instruction", "general"\n'
    '- "importance": float 0.0-1.0 (1.0 = critical, 0.1 = trivial)\n\n'
    "Rules:\n"
    "- Only extract facts worth remembering.\n"
    "- Return an empty array [] if nothing notable was said.\n"
    "- Be concise — each fact should be one short sentence.\n"
    '- Do NOT extract generic phrases like "how are you" or "thanks".\n'
    "- Prefer concrete, specific facts over vague observations."
)

MIN_MESSAGE_LENGTH = 10


def should_extract(user_msg: str, assistant_msg: str) -> bool:
    """Decide whether a conversation turn is worth extracting facts from."""
    if len(user_msg.strip()) < MIN_MESSAGE_LENGTH:
        return False
    if len(assistant_msg.strip()) < MIN_MESSAGE_LENGTH:
        return False
    return True


def extract_facts(
    llm_complete: Callable[[list[dict[str, str]]], str],
    user_msg: str,
    assistant_msg: str,
    *,
    grounding: str = "",
) -> list[ExtractedFact]:
    """Call the LLM to extract facts from a conversation turn.

    Args:
        llm_complete: A callable that takes OpenAI-format messages and returns
            the raw LLM response string.
        user_msg: The user's message.
        assistant_msg: The assistant's response.
        grounding: Optional temporal/environmental context to prepend to the
            system prompt so extracted facts are time-aware.

    Returns:
        List of ExtractedFact objects, or empty list on failure.
    """
    if not should_extract(user_msg, assistant_msg):
        return []

    system_content = EXTRACTION_SYSTEM_PROMPT
    if grounding:
        system_content = f"{grounding}\n\n{system_content}"

    prompt = f"User: {user_msg}\nAssistant: {assistant_msg}"
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = llm_complete(messages)
    except Exception:
        logger.exception("fact extraction LLM call failed")
        return []

    return _parse_extraction_response(raw)


def _parse_extraction_response(raw: str) -> list[ExtractedFact]:
    """Parse the LLM response into ExtractedFact objects."""
    text = raw.strip()

    # Try to extract JSON from markdown fences
    if "```" in text:
        start = text.find("```")
        end = text.find("```", start + 3)
        if end > start:
            text = text[start + 3:end].strip()
            # Strip optional language tag
            if text.startswith("json"):
                text = text[4:].strip()

    if not text.startswith(("[", "{")):
        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start >= 0 and end > start:
                text = text[start:end + 1]
                break

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("failed to parse fact extraction response as JSON")
        return []

    if not isinstance(data, list):
        return []

    facts: list[ExtractedFact] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text_val = str(item.get("text", "")).strip()
        if not text_val:
            continue
        category = str(item.get("category", "general")).strip()
        importance = float(item.get("importance", 0.5))
        importance = max(0.0, min(1.0, importance))
        facts.append(ExtractedFact(text=text_val, category=category, importance=importance))

    return facts


PROCEDURE_EXTRACTION_SYSTEM_PROMPT = (
    "You are a procedure extraction assistant. Given an execution trace "
    "showing the tools an assistant used to complete a user's request, "
    "extract a reusable procedure.\n\n"
    "Return a JSON object with:\n"
    '- "description": a short task description (e.g. "How to delete a calendar event")\n'
    '- "steps": an array of 2-6 natural language step descriptions\n'
    '- "category": one of "calendar", "wellbeing", "general"\n'
    '- "importance": float 0.0-1.0\n\n'
    "Rules:\n"
    "- Steps should be natural language, not tool-specific JSON schemas.\n"
    "- Each step should describe what to do, not how to call a specific API.\n"
    "- Keep steps general enough to be reusable.\n"
    '- Return null if the trace is too simple or not worth remembering.\n'
    "- Return ONLY a JSON object or null. No other text."
)


def extract_procedure(
    llm_complete: Callable[[list[dict[str, str]]], str],
    execution_trace: list[dict[str, str]],
    *,
    grounding: str = "",
) -> ExtractedProcedure | None:
    """Call the LLM to extract a procedure from an execution trace.

    Args:
        llm_complete: A callable that takes OpenAI-format messages and returns
            the raw LLM response string.
        execution_trace: List of dicts with keys "step", "tool", "input", "result".
        grounding: Optional temporal/environmental context to prepend to the
            system prompt.

    Returns:
        An ExtractedProcedure, or None if extraction fails or trace is not worth saving.
    """
    if len(execution_trace) < 2:
        return None

    trace_lines = []
    for entry in execution_trace:
        trace_lines.append(
            f"Step {entry.get('step', '?')}: called {entry.get('tool', '?')}\n"
            f"  Input: {entry.get('input', '')[:200]}\n"
            f"  Result: {entry.get('result', '')[:200]}"
        )
    trace_block = "\n".join(trace_lines)

    system_content = PROCEDURE_EXTRACTION_SYSTEM_PROMPT
    if grounding:
        system_content = f"{grounding}\n\n{system_content}"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"Execution trace:\n{trace_block}"},
    ]

    try:
        raw = llm_complete(messages)
    except Exception:
        logger.exception("procedure extraction LLM call failed")
        return None

    return _parse_procedure_response(raw)


def _parse_procedure_response(raw: str) -> ExtractedProcedure | None:
    """Parse the LLM response into an ExtractedProcedure."""
    text = raw.strip()

    if text.lower() == "null":
        return None

    if "```" in text:
        start = text.find("```")
        end = text.find("```", start + 3)
        if end > start:
            text = text[start + 3:end].strip()
            if text.startswith("json"):
                text = text[4:].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("failed to parse procedure extraction response as JSON")
        return None

    if not isinstance(data, dict):
        return None

    description = str(data.get("description", "")).strip()
    steps_raw = data.get("steps", [])
    if not description or not isinstance(steps_raw, list) or len(steps_raw) < 1:
        return None

    steps = [str(s).strip() for s in steps_raw if str(s).strip()]
    if len(steps) < 1:
        return None

    category = str(data.get("category", "general")).strip()
    importance = float(data.get("importance", 0.5))
    importance = max(0.0, min(1.0, importance))

    return ExtractedProcedure(
        description=description,
        steps=steps,
        category=category,
        importance=importance,
    )
