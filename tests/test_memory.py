"""Tests for the conversational memory system."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from assistant.memory.extraction import (
    _parse_extraction_response,
    extract_facts,
    should_extract,
)
from assistant.memory.models import ConversationMessage, ExtractedFact, MemoryFact
from assistant.memory.service import MemoryService

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestConversationMessage:
    def test_valid_message(self) -> None:
        msg = ConversationMessage(
            id="m1",
            conversation_id="!room:example.com",
            actor_id="@user:example.com",
            role="user",
            content="hello",
            created_at=datetime.now(timezone.utc),
        )
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(Exception):
            ConversationMessage(
                id="m1",
                conversation_id="!room:example.com",
                actor_id="@user:example.com",
                role="system",
                content="hello",
                created_at=datetime.now(timezone.utc),
            )


class TestMemoryFact:
    def test_valid_fact(self) -> None:
        now = datetime.now(timezone.utc)
        fact = MemoryFact(
            id="f1",
            user_id="@user:example.com",
            fact_text="User prefers mornings",
            category="preference",
            importance=0.7,
            last_accessed=now,
            created_at=now,
        )
        assert fact.importance == 0.7
        assert fact.category == "preference"

    def test_importance_bounds(self) -> None:
        now = datetime.now(timezone.utc)
        with pytest.raises(Exception):
            MemoryFact(
                id="f1",
                user_id="@user:example.com",
                fact_text="test",
                importance=1.5,
                last_accessed=now,
                created_at=now,
            )


class TestExtractedFact:
    def test_valid(self) -> None:
        fact = ExtractedFact(
            text="User likes hiking",
            category="preference",
            importance=0.6,
        )
        assert fact.text == "User likes hiking"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


class TestShouldExtract:
    def test_short_messages_skipped(self) -> None:
        assert should_extract("hi", "hello") is False

    def test_long_messages_accepted(self) -> None:
        user = "What time is my meeting tomorrow?"
        asst = "You have a meeting at 10am tomorrow."
        assert should_extract(user, asst) is True

    def test_empty_messages_skipped(self) -> None:
        assert should_extract("", "") is False


class TestParseExtractionResponse:
    def test_valid_json_array(self) -> None:
        raw = json.dumps([
            {"text": "User prefers dark mode", "category": "preference", "importance": 0.6},
            {"text": "User works at Acme", "category": "fact", "importance": 0.8},
        ])
        facts = _parse_extraction_response(raw)
        assert len(facts) == 2
        assert facts[0].text == "User prefers dark mode"
        assert facts[1].category == "fact"

    def test_empty_array(self) -> None:
        facts = _parse_extraction_response("[]")
        assert facts == []

    def test_markdown_fenced_json(self) -> None:
        raw = '```json\n[{"text": "User lives in Berlin", "category": "fact"}]\n```'
        facts = _parse_extraction_response(raw)
        assert len(facts) == 1
        assert facts[0].text == "User lives in Berlin"

    def test_invalid_json(self) -> None:
        facts = _parse_extraction_response("not json at all")
        assert facts == []

    def test_importance_clamped(self) -> None:
        raw = json.dumps([{"text": "test", "importance": 5.0}])
        facts = _parse_extraction_response(raw)
        assert facts[0].importance == 1.0

    def test_empty_text_skipped(self) -> None:
        raw = json.dumps([{"text": "", "category": "fact"}])
        facts = _parse_extraction_response(raw)
        assert facts == []


class TestExtractFacts:
    def test_calls_llm_and_parses(self) -> None:
        llm_response = json.dumps([
            {"text": "User prefers mornings", "category": "preference", "importance": 0.7},
        ])
        mock_llm = MagicMock(return_value=llm_response)

        facts = extract_facts(
            mock_llm,
            "I prefer mornings actually",
            "Noted, I'll schedule things in the morning.",
        )

        assert len(facts) == 1
        assert facts[0].text == "User prefers mornings"
        mock_llm.assert_called_once()

    def test_skips_short_messages(self) -> None:
        mock_llm = MagicMock()
        facts = extract_facts(mock_llm, "hi", "hello")
        assert facts == []
        mock_llm.assert_not_called()

    def test_handles_llm_error(self) -> None:
        mock_llm = MagicMock(side_effect=RuntimeError("API down"))
        facts = extract_facts(mock_llm, "I work at Google", "That's great!")
        assert facts == []


# ---------------------------------------------------------------------------
# MemoryService (unit tests with mock repository)
# ---------------------------------------------------------------------------


class TestMemoryService:
    def _make_service(self, **kwargs) -> MemoryService:
        mock_repo = MagicMock()
        return MemoryService(repository=mock_repo, **kwargs)

    def test_get_working_memory(self) -> None:
        service = self._make_service()
        now = datetime.now(timezone.utc)
        service._repo.get_history.return_value = [
            ConversationMessage(
                id="1", conversation_id="c1", actor_id="u1",
                role="user", content="hi", created_at=now,
            ),
            ConversationMessage(
                id="2", conversation_id="c1", actor_id="u1",
                role="assistant", content="hello", created_at=now,
            ),
        ]

        result = asyncio.run(service.get_working_memory("c1"))

        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "hi"}
        assert result[1] == {"role": "assistant", "content": "hello"}

    def test_store_turn(self) -> None:
        service = self._make_service()
        service._repo.prune_conversation.return_value = 0

        asyncio.run(service.store_turn("c1", "u1", "hello", "hi there"))

        assert service._repo.store_message.call_count == 2
        service._repo.prune_conversation.assert_called_once_with("c1", 20)

    def test_get_relevant_memories(self) -> None:
        service = self._make_service()
        now = datetime.now(timezone.utc)
        service._repo.search_facts.return_value = [
            MemoryFact(
                id="f1", user_id="u1", fact_text="Prefers mornings",
                category="preference", importance=0.7,
                last_accessed=now, created_at=now,
            ),
        ]

        result = asyncio.run(
            service.get_relevant_memories("u1", "what about tomorrow?")
        )

        assert result == ["Prefers mornings"]
        service._repo.touch_fact.assert_called_once_with("f1")

    def test_extract_and_store_facts(self) -> None:
        mock_llm = MagicMock(return_value=json.dumps([
            {"text": "User likes hiking", "category": "preference", "importance": 0.6},
        ]))
        service = self._make_service(llm_complete=mock_llm)
        service._repo.prune_old_facts.return_value = 0

        asyncio.run(
            service.extract_and_store_facts(
                "u1", "c1", "I love hiking", "Hiking is great!"
            )
        )

        service._repo.store_fact.assert_called_once()
        service._repo.prune_old_facts.assert_called_once_with("u1", 500)

    def test_extraction_disabled(self) -> None:
        mock_llm = MagicMock()
        service = self._make_service(
            llm_complete=mock_llm, extraction_enabled=False
        )

        asyncio.run(
            service.extract_and_store_facts(
                "u1", "c1", "I love hiking", "Hiking is great!"
            )
        )

        mock_llm.assert_not_called()
        service._repo.store_fact.assert_not_called()
