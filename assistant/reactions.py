"""Assistant-specific reactions with Matrix routing metadata."""

from __future__ import annotations

import logging

from beacon.core.context import Context
from beacon.core.event import Event
from beacon.core.llm_request import LLMRequest
from beacon.core.reaction import Reaction

logger = logging.getLogger(__name__)


class MatrixMessageToLLMReaction(Reaction):
    """Convert Matrix message events to LLM requests with reply routing metadata."""

    @property
    def triggers_on(self) -> list[str]:
        return ["message"]

    def match(self, event: Event) -> bool:
        return "text" in event.payload and event.payload.get("text", "").strip()

    async def produce(self, event: Event, ctx: Context) -> list[LLMRequest]:
        text = str(event.payload.get("text", "")).strip()
        logger.debug(
            "producing LLM request: conversation=%s actor=%s text_len=%d",
            ctx.conversation_id,
            ctx.actor_id,
            len(text),
        )

        messages: list[dict[str, str]] = []

        relevant_facts = ctx.memory.get("relevant_facts", [])
        if relevant_facts:
            memory_block = "\n".join(f"- {fact}" for fact in relevant_facts)
            messages.append({
                "role": "system",
                "content": f"Relevant memories about this user:\n{memory_block}",
            })
            logger.debug("injected %d memory facts into context", len(relevant_facts))

        relevant_procedures = ctx.memory.get("relevant_procedures", [])
        if relevant_procedures:
            proc_lines = []
            for proc in relevant_procedures:
                steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(proc["steps"]))
                proc_lines.append(f"- {proc['description']}:\n{steps_text}")
            messages.append({
                "role": "system",
                "content": f"Known procedures for similar tasks:\n" + "\n".join(proc_lines),
            })
            logger.debug("injected %d procedures into context", len(relevant_procedures))

        if ctx.history:
            recent_history = ctx.history[-10:]
            messages.extend(recent_history)
            logger.debug("injected %d history messages into context", len(recent_history))

        messages.append({"role": "user", "content": text})

        request = LLMRequest(
            conversation_id=ctx.conversation_id,
            actor_id=ctx.actor_id,
            messages=messages,
            metadata=self._build_metadata(event, ctx),
            hints={"be_concise": True},
        )

        return [request]

    def _build_metadata(self, event: Event, ctx: Context) -> dict[str, str]:
        payload = event.payload if isinstance(event.payload, dict) else {}
        raw_event = payload.get("raw", {})
        if not isinstance(raw_event, dict):
            raw_event = {}

        room_id = str(payload.get("room", ctx.conversation_id)).strip()
        reply_to_event_id = str(raw_event.get("event_id", "")).strip()

        metadata: dict[str, str] = {
            "source_event_id": event.id,
            "room_id": room_id,
        }
        if reply_to_event_id:
            metadata["reply_to_event_id"] = reply_to_event_id

        thread_root_event_id = self._resolve_thread_root_event_id(raw_event, reply_to_event_id)
        if thread_root_event_id:
            metadata["thread_root_event_id"] = thread_root_event_id

        return metadata

    def _resolve_thread_root_event_id(
        self,
        raw_event: dict[str, object],
        reply_to_event_id: str,
    ) -> str:
        content = raw_event.get("content", {})
        if not isinstance(content, dict):
            return reply_to_event_id

        relates_to = content.get("m.relates_to", {})
        if not isinstance(relates_to, dict):
            return reply_to_event_id

        rel_type = str(relates_to.get("rel_type", "")).strip()
        if rel_type != "m.thread":
            return reply_to_event_id

        thread_event_id = str(relates_to.get("event_id", "")).strip()
        if thread_event_id:
            return thread_event_id
        return reply_to_event_id
