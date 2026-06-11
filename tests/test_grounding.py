"""Tests for the grounding context module."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from assistant.grounding import build_grounding_context


def _fixed_now() -> datetime:
    return datetime(2026, 6, 13, 14, 30, 0, tzinfo=timezone.utc)


@patch("assistant.grounding.datetime")
def test_build_grounding_context_includes_timestamp(mock_dt: object) -> None:
    mock_dt.now.return_value = _fixed_now()  # type: ignore[attr-defined]
    result = build_grounding_context()
    assert "2026-06-13T14:30:00Z" in result


@patch("assistant.grounding.datetime")
def test_build_grounding_context_includes_day_of_week(mock_dt: object) -> None:
    mock_dt.now.return_value = _fixed_now()  # type: ignore[attr-defined]
    result = build_grounding_context()
    assert "Saturday" in result


@patch("assistant.grounding.datetime")
def test_build_grounding_context_includes_actor_id(mock_dt: object) -> None:
    mock_dt.now.return_value = _fixed_now()  # type: ignore[attr-defined]
    result = build_grounding_context(actor_id="@alice:matrix.org")
    assert "User: @alice:matrix.org" in result


@patch("assistant.grounding.datetime")
def test_build_grounding_context_includes_model(mock_dt: object) -> None:
    mock_dt.now.return_value = _fixed_now()  # type: ignore[attr-defined]
    result = build_grounding_context(model="gpt-4o")
    assert "Model: gpt-4o" in result


@patch("assistant.grounding.datetime")
def test_build_grounding_context_omits_empty_fields(mock_dt: object) -> None:
    mock_dt.now.return_value = _fixed_now()  # type: ignore[attr-defined]
    result = build_grounding_context()
    assert "User:" not in result
    assert "Model:" not in result


@patch("assistant.grounding.datetime")
def test_build_grounding_context_full(mock_dt: object) -> None:
    mock_dt.now.return_value = _fixed_now()  # type: ignore[attr-defined]
    result = build_grounding_context(model="gpt-4o", actor_id="@alice:matrix.org")
    lines = result.split("\n")
    assert len(lines) == 3
    assert lines[0] == "Current date and time: 2026-06-13T14:30:00Z (Saturday)"
    assert lines[1] == "User: @alice:matrix.org"
    assert lines[2] == "Model: gpt-4o"
