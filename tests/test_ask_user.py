"""Tests for the AskUser interaction tool."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from assistant.interaction.ports import PendingQuestion


class FakePendingQuestionRepository:
    """In-memory implementation for testing."""

    def __init__(self) -> None:
        self._questions: dict[str, PendingQuestion] = {}
        self._by_room_thread: dict[tuple[str, str], PendingQuestion] = {}

    def save(self, q: PendingQuestion) -> None:
        self._questions[q["id"]] = q
        self._by_room_thread[(q["room_id"], q["thread_root"])] = q

    def find_by_room_thread(self, room_id: str, thread_root: str) -> PendingQuestion | None:
        return self._by_room_thread.get((room_id, thread_root))

    def delete(self, question_id: str) -> None:
        q = self._questions.pop(question_id, None)
        if q:
            self._by_room_thread.pop((q["room_id"], q["thread_root"]), None)

    def delete_expired(self, ttl_seconds: int) -> int:
        return 0


class TestAskUserTool:
    """Test the AskUser tool registration and behavior."""

    def _make_tool_class(
        self, matrix_client=None, pending_question_repo=None, request_metadata=None
    ):
        """Import and return the AskUser tool class."""
        if matrix_client is None:
            matrix_client = MagicMock()
            matrix_client.send_text = AsyncMock()
        if pending_question_repo is None:
            pending_question_repo = FakePendingQuestionRepository()
        if request_metadata is None:
            request_metadata = {}

        from keel.core.registry import ToolRegistry

        from assistant.builtin_tools.interaction.tools import register_tools

        registry = ToolRegistry()
        register_tools(
            registry, matrix_client, pending_question_repo, request_metadata
        )
        return registry.get("AskUser"), pending_question_repo

    def _set_thread_context(
        self, room_id="!room:test", thread_root="",
        original_prompt="test prompt", tool_history=None
    ):
        """Set the thread-local tool context for the current thread."""
        import assistant.runtime as _runtime

        if not hasattr(_runtime, "_tool_context"):
            _runtime._tool_context = threading.local()
        _runtime._tool_context.room_id = room_id
        _runtime._tool_context.thread_root_event_id = thread_root
        _runtime._tool_context.original_prompt = original_prompt
        _runtime._tool_context.tool_history = tool_history or []

    def test_tool_registered(self) -> None:
        tool_cls, _ = self._make_tool_class()
        assert tool_cls.tool_name == "AskUser"

    def test_missing_question_rejected(self) -> None:
        tool_cls, _ = self._make_tool_class()
        with pytest.raises(Exception):
            tool_cls.model_validate({"room_id": "!room:test"})

    def test_missing_room_id_rejected(self) -> None:
        tool_cls, _ = self._make_tool_class()
        with pytest.raises(Exception):
            tool_cls.model_validate({"question": "where to?"})

    def test_valid_construction(self) -> None:
        tool_cls, _ = self._make_tool_class()
        tool = tool_cls.model_validate({
            "question": "Where to?",
            "room_id": "!room:test",
        })
        assert tool.question == "Where to?"
        assert tool.room_id == "!room:test"

    def test_sends_question_and_returns_sentinel(self) -> None:
        mock_client = MagicMock()
        mock_client.send_text = AsyncMock()
        tool_cls, repo = self._make_tool_class(matrix_client=mock_client)
        tool = tool_cls.model_validate({
            "question": "Where to?",
            "room_id": "!room:test",
        })
        self._set_thread_context()

        result = tool.execute()

        assert result["__ask_user_waiting"] is True
        assert "question_id" in result
        mock_client.send_text.assert_called_once_with("!room:test", "Where to?")

    def test_sends_question_with_thread_context(self) -> None:
        mock_client = MagicMock()
        mock_client.send_text = AsyncMock()
        tool_cls, repo = self._make_tool_class(matrix_client=mock_client)
        tool = tool_cls.model_validate({
            "question": "Where to?",
            "room_id": "!room:test",
        })
        self._set_thread_context(room_id="!room:test", thread_root="$thread_root")

        result = tool.execute()

        assert result["__ask_user_waiting"] is True
        mock_client.send_text.assert_called_once_with(
            "!room:test", "Where to?", thread_root_event_id="$thread_root"
        )

    def test_persists_question_to_database(self) -> None:
        mock_client = MagicMock()
        mock_client.send_text = AsyncMock()
        repo = FakePendingQuestionRepository()
        tool_cls, _ = self._make_tool_class(matrix_client=mock_client, pending_question_repo=repo)
        tool = tool_cls.model_validate({
            "question": "Where to?",
            "room_id": "!room:test",
        })
        self._set_thread_context(
            original_prompt="original prompt",
            tool_history=[(1, "SomeTool", "result")]
        )

        result = tool.execute()

        question_id = result["question_id"]
        assert question_id in repo._questions
        saved = repo._questions[question_id]
        assert saved["room_id"] == "!room:test"
        assert saved["question"] == "Where to?"
        assert saved["original_prompt"] == "original prompt"
        assert saved["tool_history"] == [(1, "SomeTool", "result")]

    def test_send_failure_returns_error(self) -> None:
        mock_client = MagicMock()
        mock_client.send_text = AsyncMock(side_effect=RuntimeError("send failed"))
        repo = FakePendingQuestionRepository()
        tool_cls, _ = self._make_tool_class(matrix_client=mock_client, pending_question_repo=repo)
        tool = tool_cls.model_validate({
            "question": "Where to?",
            "room_id": "!room:test",
        })
        self._set_thread_context()

        result = tool.execute()

        assert result["answer"] is None
        assert "error" in result
        assert "send failed" in result["error"]
        assert len(repo._questions) == 0

    def test_database_save_failure_returns_error(self) -> None:
        mock_client = MagicMock()
        mock_client.send_text = AsyncMock()

        class FailingRepo(FakePendingQuestionRepository):
            def save(self, q):
                raise RuntimeError("db error")

        tool_cls, _ = self._make_tool_class(
            matrix_client=mock_client, pending_question_repo=FailingRepo()
        )
        tool = tool_cls.model_validate({
            "question": "Where to?",
            "room_id": "!room:test",
        })
        self._set_thread_context()

        result = tool.execute()

        assert result["answer"] is None
        assert "error" in result
        assert "db error" in result["error"]


class TestAskUserWaitingSentinel:
    """Test the _AskUserWaiting sentinel detection in _agentic_loop_sync."""

    def test_sentinel_detected(self) -> None:
        from assistant.runtime import _AskUserWaiting

        sentinel = _AskUserWaiting(
            question_id="test-id",
            original_prompt="test prompt",
            tool_history=[],
        )
        assert sentinel.question_id == "test-id"
        assert sentinel.original_prompt == "test prompt"
        assert sentinel.tool_history == []


class TestReconstructPromptWithAnswer:
    """Test the prompt reconstruction logic."""

    def test_basic_reconstruction(self) -> None:
        from assistant.runtime import AssistantRuntime

        runtime = MagicMock(spec=AssistantRuntime)
        runtime._reconstruct_prompt_with_answer = (
            AssistantRuntime._reconstruct_prompt_with_answer.__get__(runtime)
        )

        result = runtime._reconstruct_prompt_with_answer(
            original_prompt="Do something",
            tool_history=[(1, "SearchTool", "found results")],
            question="Where should I search?",
            answer="In the docs folder",
        )

        assert "Do something" in result
        assert "[step 1] SearchTool → found results" in result
        assert "[step 2] AskUser → asked: Where should I search?" in result
        assert "User answered: In the docs folder" in result
        assert "Continue your task using the user's answer" in result

    def test_empty_tool_history(self) -> None:
        from assistant.runtime import AssistantRuntime

        runtime = MagicMock(spec=AssistantRuntime)
        runtime._reconstruct_prompt_with_answer = (
            AssistantRuntime._reconstruct_prompt_with_answer.__get__(runtime)
        )

        result = runtime._reconstruct_prompt_with_answer(
            original_prompt="Do something",
            tool_history=[],
            question="What?",
            answer="Yes",
        )

        assert "Do something" in result
        assert "[step 1] AskUser → asked: What?" in result
        assert "User answered: Yes" in result


class TestPendingQuestionRepositoryInterface:
    """Test the FakePendingQuestionRepository works as expected."""

    def test_save_and_find(self) -> None:
        repo = FakePendingQuestionRepository()
        q = PendingQuestion(
            id="q1",
            room_id="!room:test",
            thread_root="$thread1",
            question="Where?",
            original_prompt="prompt",
            tool_history=[],
            request_metadata={},
            created_at=datetime.now(timezone.utc),
        )
        repo.save(q)
        found = repo.find_by_room_thread("!room:test", "$thread1")
        assert found is not None
        assert found["id"] == "q1"

    def test_find_returns_none_when_not_found(self) -> None:
        repo = FakePendingQuestionRepository()
        assert repo.find_by_room_thread("!room:test", "$thread1") is None

    def test_delete_removes_question(self) -> None:
        repo = FakePendingQuestionRepository()
        q = PendingQuestion(
            id="q1",
            room_id="!room:test",
            thread_root="$thread1",
            question="Where?",
            original_prompt="prompt",
            tool_history=[],
            request_metadata={},
            created_at=datetime.now(timezone.utc),
        )
        repo.save(q)
        repo.delete("q1")
        assert repo.find_by_room_thread("!room:test", "$thread1") is None

    def test_different_threads_stored_separately(self) -> None:
        repo = FakePendingQuestionRepository()
        q1 = PendingQuestion(
            id="q1",
            room_id="!room:test",
            thread_root="$thread1",
            question="Where?",
            original_prompt="prompt",
            tool_history=[],
            request_metadata={},
            created_at=datetime.now(timezone.utc),
        )
        q2 = PendingQuestion(
            id="q2",
            room_id="!room:test",
            thread_root="$thread2",
            question="When?",
            original_prompt="prompt",
            tool_history=[],
            request_metadata={},
            created_at=datetime.now(timezone.utc),
        )
        repo.save(q1)
        repo.save(q2)

        assert repo.find_by_room_thread("!room:test", "$thread1")["id"] == "q1"
        assert repo.find_by_room_thread("!room:test", "$thread2")["id"] == "q2"
