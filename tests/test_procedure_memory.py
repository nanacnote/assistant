"""Tests for the procedure memory system."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from assistant.memory.extraction import _parse_procedure_response, extract_procedure
from assistant.memory.models import ExtractedProcedure, ProcedureMemory
from assistant.memory.service import MemoryService


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestProcedureMemory:
    def test_valid_procedure(self) -> None:
        now = datetime.now(timezone.utc)
        proc = ProcedureMemory(
            id="p1",
            user_id="@user:example.com",
            description="How to delete a calendar event",
            steps=["Search for events", "Extract event_id", "Call DeleteEvent"],
            category="calendar",
            importance=0.7,
            last_accessed=now,
            created_at=now,
        )
        assert proc.description == "How to delete a calendar event"
        assert len(proc.steps) == 3
        assert proc.importance == 0.7

    def test_importance_bounds(self) -> None:
        now = datetime.now(timezone.utc)
        with pytest.raises(Exception):
            ProcedureMemory(
                id="p1",
                user_id="@user:example.com",
                description="test",
                steps=["step one"],
                importance=1.5,
                last_accessed=now,
                created_at=now,
            )

    def test_empty_steps_allowed(self) -> None:
        now = datetime.now(timezone.utc)
        proc = ProcedureMemory(
            id="p1",
            user_id="@user:example.com",
            description="test",
            steps=[],
            last_accessed=now,
            created_at=now,
        )
        assert proc.steps == []


class TestExtractedProcedure:
    def test_valid(self) -> None:
        proc = ExtractedProcedure(
            description="How to delete an event",
            steps=["Search for events", "Delete the event"],
            category="calendar",
            importance=0.6,
        )
        assert proc.description == "How to delete an event"
        assert len(proc.steps) == 2

    def test_empty_steps_rejected(self) -> None:
        with pytest.raises(Exception):
            ExtractedProcedure(
                description="test",
                steps=[],
            )

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(Exception):
            ExtractedProcedure(
                description="",
                steps=["step one"],
            )


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


class TestParseProcedureResponse:
    def test_valid_json_object(self) -> None:
        raw = json.dumps({
            "description": "How to delete a calendar event",
            "steps": ["Search for events", "Extract event_id", "Call DeleteEvent"],
            "category": "calendar",
            "importance": 0.7,
        })
        proc = _parse_procedure_response(raw)
        assert proc is not None
        assert proc.description == "How to delete a calendar event"
        assert len(proc.steps) == 3
        assert proc.category == "calendar"

    def test_null_return(self) -> None:
        assert _parse_procedure_response("null") is None

    def test_markdown_fenced_json(self) -> None:
        raw = '```json\n{"description": "test", "steps": ["step one"]}\n```'
        proc = _parse_procedure_response(raw)
        assert proc is not None
        assert proc.description == "test"

    def test_invalid_json(self) -> None:
        assert _parse_procedure_response("not json") is None

    def test_missing_description(self) -> None:
        raw = json.dumps({"steps": ["step one"]})
        assert _parse_procedure_response(raw) is None

    def test_missing_steps(self) -> None:
        raw = json.dumps({"description": "test"})
        assert _parse_procedure_response(raw) is None

    def test_empty_steps_list(self) -> None:
        raw = json.dumps({"description": "test", "steps": []})
        assert _parse_procedure_response(raw) is None

    def test_importance_clamped(self) -> None:
        raw = json.dumps({"description": "test", "steps": ["step"], "importance": 5.0})
        proc = _parse_procedure_response(raw)
        assert proc is not None
        assert proc.importance == 1.0

    def test_non_dict_returns_none(self) -> None:
        assert _parse_procedure_response('"hello"') is None
        assert _parse_procedure_response("42") is None


class TestExtractProcedure:
    def test_calls_llm_and_parses(self) -> None:
        llm_response = json.dumps({
            "description": "How to delete a calendar event",
            "steps": ["Search for events", "Extract event_id", "Call DeleteEvent"],
            "category": "calendar",
            "importance": 0.7,
        })
        mock_llm = MagicMock(return_value=llm_response)
        trace = [
            {"step": "1", "tool": "SearchEvents", "input": '{"query_text": "meeting"}', "result": '{"events": []}'},
            {"step": "2", "tool": "DeleteEvent", "input": '{"event_id": "e1"}', "result": '{"status": "deleted"}'},
        ]

        proc = extract_procedure(mock_llm, trace)

        assert proc is not None
        assert proc.description == "How to delete a calendar event"
        assert len(proc.steps) == 3
        mock_llm.assert_called_once()

    def test_skips_short_traces(self) -> None:
        mock_llm = MagicMock()
        trace = [{"step": "1", "tool": "Reply", "input": "", "result": "done"}]
        assert extract_procedure(mock_llm, trace) is None
        mock_llm.assert_not_called()

    def test_handles_llm_error(self) -> None:
        mock_llm = MagicMock(side_effect=RuntimeError("API down"))
        trace = [
            {"step": "1", "tool": "A", "input": "", "result": ""},
            {"step": "2", "tool": "B", "input": "", "result": ""},
        ]
        assert extract_procedure(mock_llm, trace) is None

    def test_handles_llm_returning_null(self) -> None:
        mock_llm = MagicMock(return_value="null")
        trace = [
            {"step": "1", "tool": "A", "input": "", "result": ""},
            {"step": "2", "tool": "B", "input": "", "result": ""},
        ]
        assert extract_procedure(mock_llm, trace) is None


# ---------------------------------------------------------------------------
# MemoryService (procedure methods)
# ---------------------------------------------------------------------------


class TestMemoryServiceProcedures:
    def _make_service(self, **kwargs) -> MemoryService:
        mock_repo = MagicMock()
        return MemoryService(repository=mock_repo, **kwargs)

    def test_get_relevant_procedures(self) -> None:
        service = self._make_service()
        now = datetime.now(timezone.utc)
        service._repo.search_procedures.return_value = [
            ProcedureMemory(
                id="p1",
                user_id="u1",
                description="How to delete an event",
                steps=["Search", "Delete"],
                category="calendar",
                importance=0.7,
                last_accessed=now,
                created_at=now,
            ),
        ]

        result = asyncio.run(
            service.get_relevant_procedures("u1", "delete my meeting")
        )

        assert len(result) == 1
        assert result[0]["description"] == "How to delete an event"
        assert result[0]["steps"] == ["Search", "Delete"]
        service._repo.touch_procedure.assert_called_once_with("p1")

    def test_get_relevant_procedures_empty(self) -> None:
        service = self._make_service()
        service._repo.search_procedures.return_value = []

        result = asyncio.run(
            service.get_relevant_procedures("u1", "random query")
        )

        assert result == []

    def test_store_procedure(self) -> None:
        service = self._make_service()
        service._repo.prune_old_procedures.return_value = 0

        proc = asyncio.run(
            service.store_procedure("u1", "c1", "How to do X", ["step 1", "step 2"])
        )

        assert proc.description == "How to do X"
        assert proc.steps == ["step 1", "step 2"]
        service._repo.store_procedure.assert_called_once()
        service._repo.prune_old_procedures.assert_called_once_with("u1", 200)

    def test_extract_and_store_procedure(self) -> None:
        mock_llm = MagicMock(return_value=json.dumps({
            "description": "How to do X",
            "steps": ["step 1", "step 2"],
            "category": "general",
            "importance": 0.5,
        }))
        service = self._make_service(
            llm_complete=mock_llm,
            procedure_extraction_enabled=True,
        )
        service._repo.prune_old_procedures.return_value = 0

        trace = [
            {"step": "1", "tool": "A", "input": "", "result": ""},
            {"step": "2", "tool": "B", "input": "", "result": ""},
        ]
        result = asyncio.run(
            service.extract_and_store_procedure("u1", "c1", trace)
        )

        assert result is not None
        assert result.description == "How to do X"
        service._repo.store_procedure.assert_called_once()

    def test_extract_skips_short_trace(self) -> None:
        mock_llm = MagicMock()
        service = self._make_service(llm_complete=mock_llm)

        trace = [{"step": "1", "tool": "A", "input": "", "result": ""}]
        result = asyncio.run(
            service.extract_and_store_procedure("u1", "c1", trace)
        )

        assert result is None
        mock_llm.assert_not_called()

    def test_procedure_extraction_disabled(self) -> None:
        mock_llm = MagicMock()
        service = self._make_service(
            llm_complete=mock_llm, procedure_extraction_enabled=False
        )

        trace = [
            {"step": "1", "tool": "A", "input": "", "result": ""},
            {"step": "2", "tool": "B", "input": "", "result": ""},
        ]
        result = asyncio.run(
            service.extract_and_store_procedure("u1", "c1", trace)
        )

        assert result is None
        mock_llm.assert_not_called()
        service._repo.store_procedure.assert_not_called()

    def test_record_procedure_execution(self) -> None:
        service = self._make_service()
        asyncio.run(service.record_procedure_execution("p1", True))
        service._repo.record_procedure_execution.assert_called_once_with("p1", True)

    def test_decay_stale_procedures(self) -> None:
        service = self._make_service()
        service._repo.decay_procedure_importance.return_value = 3
        result = asyncio.run(service.decay_stale_procedures(30, 0.5))
        assert result == 3
        service._repo.decay_procedure_importance.assert_called_once_with(30, 0.5)
