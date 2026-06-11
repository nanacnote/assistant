"""Tests for assistant-specific reaction metadata."""

from __future__ import annotations

import asyncio

from beacon.core.context import Context
from beacon.core.event import Event

from assistant.reactions import MatrixMessageToLLMReaction


def test_matrix_message_reaction_carries_thread_metadata() -> None:
    async def _run() -> None:
        reaction = MatrixMessageToLLMReaction()
        event = Event(
            id="evt-internal-1",
            type="message",
            source="matrix",
            payload={
                "text": "hello",
                "sender": "@user:example.com",
                "room": "!room:example.com",
                "raw": {
                    "event_id": "$event-123",
                    "content": {
                        "body": "hello",
                        "m.relates_to": {
                            "rel_type": "m.thread",
                            "event_id": "$thread-root-1",
                        },
                    },
                },
            },
        )
        ctx = Context(conversation_id="!room:example.com", actor_id="@user:example.com")

        requests = await reaction.produce(event, ctx)

        assert len(requests) == 1
        metadata = requests[0].metadata
        assert metadata["source_event_id"] == "evt-internal-1"
        assert metadata["room_id"] == "!room:example.com"
        assert metadata["reply_to_event_id"] == "$event-123"
        assert metadata["thread_root_event_id"] == "$thread-root-1"

    asyncio.run(_run())


def test_matrix_message_reaction_defaults_thread_root_to_message_event() -> None:
    async def _run() -> None:
        reaction = MatrixMessageToLLMReaction()
        event = Event(
            id="evt-internal-2",
            type="message",
            source="matrix",
            payload={
                "text": "hello",
                "sender": "@user:example.com",
                "room": "!room:example.com",
                "raw": {
                    "event_id": "$event-456",
                    "content": {
                        "body": "hello",
                    },
                },
            },
        )
        ctx = Context(conversation_id="!room:example.com", actor_id="@user:example.com")

        requests = await reaction.produce(event, ctx)

        assert len(requests) == 1
        metadata = requests[0].metadata
        assert metadata["reply_to_event_id"] == "$event-456"
        assert metadata["thread_root_event_id"] == "$event-456"

    asyncio.run(_run())
