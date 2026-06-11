"""Assistant runtime that composes Beacon and Keel."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any

from beacon.adapters.inbound.matrix import MatrixAdapter
from beacon.adapters.response.llm_response import ResponseAdapter
from beacon.core import (
    ContextBuilder,
    CoreEngine,
    Dispatcher,
    LLMRequest,
    LLMResponse,
    ReactionEngine,
)
from beacon.infra import EventBus
from keel.core import prompts
from keel.core.dispatcher import Dispatcher as KeelDispatcher
from keel.core.engine import Engine as KeelEngine
from keel.core.engine import FailureReport

from assistant.config import AssistantSettings
from assistant.grounding import build_grounding_context
from assistant.interaction.ports import PendingQuestionRepository
from assistant.llm import OpenAICompatibleLLM
from assistant.matrix import MatrixClient
from assistant.memory import build_history_fetcher, build_memory_service
from assistant.reactions import MatrixMessageToLLMReaction
from assistant.tools import build_tool_registry, load_tool_modules

logger = logging.getLogger(__name__)

_tool_context: threading.local = threading.local()


@dataclass
class _AskUserWaiting:
    """Sentinel returned by _agentic_loop_sync when AskUser is invoked."""

    question_id: str
    original_prompt: str
    tool_history: list[tuple[int, str, str]]

class _ResultCapture:
    """MiddlewareHook that captures the result of each tool.execute() call.

    Uses threading.local so concurrent requests dispatched via
    asyncio.to_thread never share state — each thread has its own slot.
    The entire agentic loop for one request runs in a single thread, so
    last_result always reflects the most recent tool executed in that loop.
    """

    def __init__(self) -> None:
        self._local: threading.local = threading.local()

    def pre_execute(self, tool: Any) -> None:
        tool_name = getattr(tool, "tool_name", tool.__class__.__name__)
        try:
            input_snapshot = json.dumps(tool.model_dump(mode="json"), default=str)[:500]
        except Exception:
            input_snapshot = str(tool)[:500]
        self._local.current_tool_name = tool_name
        self._local.current_input_snapshot = input_snapshot

    def post_execute(self, tool: Any, result: Any) -> None:
        self._local.result = result
        if not hasattr(self._local, "trace_steps"):
            self._local.trace_steps = []
        self._local.trace_steps.append({
            "step": str(len(self._local.trace_steps) + 1),
            "tool": getattr(self._local, "current_tool_name", "unknown"),
            "input": getattr(self._local, "current_input_snapshot", ""),
            "result": (
                json.dumps(result, default=str)[:500]
                if isinstance(result, dict)
                else str(result)[:500]
            ),
        })

    @property
    def last_result(self) -> Any:
        return getattr(self._local, "result", None)

    @property
    def trace(self) -> list[dict[str, str]]:
        return list(getattr(self._local, "trace_steps", []))

    def reset_trace(self) -> None:
        self._local.trace_steps = []


class _ActorStampMiddleware:
    """Middleware that stamps actor_id and request context onto tools.

    Runs in the same thread as the agentic loop (spawned by asyncio.to_thread),
    so thread-local values it sets are visible to tool.execute().

    Tools that declare ``_actor_field`` (e.g. ``"user_id"``) have that field
    overwritten with the authenticated actor_id, preventing the LLM from
    spoofing user identity.
    """

    def __init__(self, request_metadata: dict[str, dict[str, str]]) -> None:
        self._request_metadata = request_metadata

    def pre_execute(self, tool: Any) -> None:
        active_request_id = getattr(_tool_context, "active_request_id", "")
        meta = self._request_metadata.get(active_request_id, {})
        if not meta:
            for meta in self._request_metadata.values():
                break
        _tool_context.room_id = meta.get("room_id", "")
        _tool_context.thread_root_event_id = meta.get("thread_root_event_id", "")
        _tool_context.actor_id = meta.get("actor_id", "")

        actor_field = getattr(tool.__class__, "_actor_field", None)
        if actor_field is not None:
            if hasattr(actor_field, "default"):
                actor_field = actor_field.default
            if not isinstance(actor_field, str):
                return
            actor_id = getattr(_tool_context, "actor_id", "")
            if actor_id and hasattr(tool, actor_field):
                object.__setattr__(tool, actor_field, actor_id)

    def post_execute(self, tool: Any, result: Any) -> None:
        pass


class AssistantRuntime:
    """Compose Beacon ingress/egress with Keel tool-calling."""

    def __init__(self, settings: AssistantSettings):
        self.settings = settings
        self._sync_task: asyncio.Task[None] | None = None
        self.event_bus = EventBus(
            max_workers=settings.event_workers,
            queue_size=settings.queue_size,
        )
        self.matrix_adapter = MatrixAdapter(self.event_bus)
        self.matrix_client = MatrixClient(settings.matrix)
        self.response_adapter = ResponseAdapter(self.event_bus)
        self.reaction_engine = ReactionEngine([MatrixMessageToLLMReaction()])

        self.llm = OpenAICompatibleLLM(settings.llm)
        try:
            self.memory_service = build_memory_service(
                llm_complete=self.llm.complete,
                working_memory_limit=settings.memory.working_memory_limit,
                max_facts_per_user=settings.memory.max_facts_per_user,
                extraction_enabled=settings.memory.extraction_enabled,
                max_procedures_per_user=settings.memory.max_procedures_per_user,
                procedure_extraction_enabled=settings.memory.procedure_extraction_enabled,
            )
        except Exception as exc:
            logger.warning("Memory service unavailable, continuing without memory: %s", exc)
            from assistant.memory.ports import UnconfiguredMemoryRepository
            from assistant.memory.service import MemoryService

            self.memory_service = MemoryService(
                repository=UnconfiguredMemoryRepository(),
                llm_complete=self.llm.complete,
                working_memory_limit=settings.memory.working_memory_limit,
                max_facts_per_user=settings.memory.max_facts_per_user,
                extraction_enabled=False,
                max_procedures_per_user=settings.memory.max_procedures_per_user,
                procedure_extraction_enabled=False,
            )
        history_fetcher = build_history_fetcher(self.memory_service)
        self.context_builder = ContextBuilder(history_fetcher=history_fetcher)

        self._pending_user_messages: dict[str, tuple[str, str, str, list[dict[str, str]]]] = {}
        self._request_metadata: dict[str, dict[str, str]] = {}

        from assistant.interaction import build_pending_question_repository

        self._pending_question_repo: PendingQuestionRepository = build_pending_question_repository()

        self.registry = build_tool_registry()
        if settings.tool_modules:
            load_tool_modules(
                self.registry,
                settings.tool_modules,
                memory_service=self.memory_service,
                matrix_client=self.matrix_client,
                pending_question_repo=self._pending_question_repo,
                request_metadata=self._request_metadata,
            )
        self.system_prompt = self._build_system_prompt()
        self._result_capture = _ResultCapture()
        self._actor_stamp = _ActorStampMiddleware(self._request_metadata)
        self.keel_engine = KeelEngine(
            llm=self.llm,
            registry=self.registry,
            dispatcher=KeelDispatcher(self.registry),
            middleware=[self._actor_stamp, self._result_capture],
        )
        self.dispatcher = Dispatcher(send_handler=self._dispatch_via_keel)
        self.core_engine = CoreEngine(self.reaction_engine, self.context_builder, self.dispatcher)

        self.event_bus.subscribe("message", self._handle_message_event)
        self.event_bus.subscribe("llm_response", self._handle_llm_response_event)

    async def start(self) -> None:
        """Start the Beacon event loop."""
        await self.event_bus.start()
        await self.matrix_client.start()
        self._sync_task = asyncio.create_task(
            self.matrix_client.sync_forever(self._ingest_matrix_event)
        )

    async def stop(self) -> None:
        """Stop the Beacon event loop."""
        if self._sync_task is not None:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None
        await self.event_bus.stop()

    async def _ingest_matrix_event(self, raw_event: dict[str, Any]) -> None:
        await self.matrix_adapter.ingest_raw_event(raw_event)

    async def _handle_message_event(self, event) -> None:
        room_id = str(event.payload.get("room", ""))
        raw_event = event.payload.get("raw", {})
        if not isinstance(raw_event, dict):
            raw_event = {}
        content = raw_event.get("content", {})
        if not isinstance(content, dict):
            content = {}
        relates_to = content.get("m.relates_to", {})
        if not isinstance(relates_to, dict):
            relates_to = {}
        incoming_thread_root = ""
        if str(relates_to.get("rel_type", "")) == "m.thread":
            incoming_thread_root = str(relates_to.get("event_id", "")).strip()

        sender = str(event.payload.get("sender", ""))
        answer = str(event.payload.get("text", "")).strip()

        if answer:
            try:
                pending = await asyncio.to_thread(
                    self._pending_question_repo.find_by_room_thread,
                    room_id,
                    incoming_thread_root,
                )
            except Exception as exc:
                logger.error("AskUser: failed to query pending questions: %s", exc)
                pending = None

            if pending is not None:
                logger.info(
                    "AskUser: found pending question %s in room %s thread %s, re-dispatching",
                    pending["id"], room_id, incoming_thread_root or "(none)",
                )
                try:
                    await asyncio.to_thread(self._pending_question_repo.delete, pending["id"])
                except Exception as exc:
                    logger.error("AskUser: failed to delete pending question: %s", exc)

                reconstructed = self._reconstruct_prompt_with_answer(
                    original_prompt=pending["original_prompt"],
                    tool_history=pending["tool_history"],
                    question=pending["question"],
                    answer=answer,
                )

                ctx = await self.context_builder.build(event)
                if ctx.actor_id:
                    try:
                        relevant = await self.memory_service.get_relevant_memories(
                            ctx.actor_id, answer
                        )
                        ctx.memory["relevant_facts"] = relevant
                    except Exception:
                        ctx.memory["relevant_facts"] = []
                    try:
                        procedures = await self.memory_service.get_relevant_procedures(
                            ctx.actor_id, answer
                        )
                        ctx.memory["relevant_procedures"] = procedures
                    except Exception:
                        ctx.memory["relevant_procedures"] = []

                request_metadata = pending["request_metadata"]
                request = LLMRequest(
                    id=f"resume-{pending['id']}",
                    conversation_id=request_metadata.get("room_id", room_id),
                    actor_id=request_metadata.get("actor_id", sender),
                    messages=[{"role": "user", "content": reconstructed}],
                    metadata={
                        "room_id": room_id,
                        "thread_root_event_id": incoming_thread_root,
                        "actor_id": request_metadata.get("actor_id", sender),
                    },
                )
                await self.dispatcher.dispatch(request)
                return

        ctx = await self.context_builder.build(event)
        user_msg = str(event.payload.get("text", "")).strip()
        if ctx.actor_id and user_msg:
            try:
                relevant = await self.memory_service.get_relevant_memories(ctx.actor_id, user_msg)
                ctx.memory["relevant_facts"] = relevant
            except Exception:
                ctx.memory["relevant_facts"] = []
            try:
                procedures = await self.memory_service.get_relevant_procedures(
                    ctx.actor_id, user_msg
                )
                ctx.memory["relevant_procedures"] = procedures
            except Exception:
                ctx.memory["relevant_procedures"] = []
        requests = await self.reaction_engine.process(event, ctx)
        for request in requests:
            await self.dispatcher.dispatch(request)

    async def _handle_llm_response_event(self, event) -> None:
        request_id = event.payload.get("request_id", "")
        output = event.payload.get("output", {})
        text = self._extract_response_text(output)
        room_id, reply_to_event_id, thread_root_event_id = self._extract_reply_route(output)
        if not room_id:
            logger.warning("dropping response without room mapping for request_id=%s", request_id)
            return
        if not text:
            logger.warning("dropping empty response for request_id=%s", request_id)
            return
        logger.info("sending assistant response to room %s", room_id)
        await self.matrix_client.send_text(
            room_id,
            text,
            reply_to_event_id=reply_to_event_id,
            thread_root_event_id=thread_root_event_id,
        )

        pending = self._pending_user_messages.pop(request_id, None)
        if pending:
            user_id, conv_id, user_msg, trace_steps = pending
            try:
                await self.memory_service.store_turn(conv_id, user_id, user_msg, text)
                asyncio.create_task(
                    self.memory_service.extract_and_store_facts(user_id, conv_id, user_msg, text)
                )
                if len(trace_steps) >= 2:
                    asyncio.create_task(
                        self.memory_service.extract_and_store_procedure(
                            user_id, conv_id, trace_steps
                        )
                    )
            except Exception:
                logger.debug("memory persistence skipped for request_id=%s", request_id)

    async def _dispatch_via_keel(self, request: LLMRequest) -> None:
        prompt = self._render_request(request)
        user_msgs = [m for m in request.messages if m.get("role") == "user"]
        current_user_msg = user_msgs[-1].get("content", "") if user_msgs else ""

        if request.id.startswith("resume-"):
            for line in current_user_msg.split("\n"):
                if line.startswith("User answered:"):
                    current_user_msg = line[len("User answered:"):].strip()
                    break
        self._request_metadata[request.id] = {
            "room_id": request.metadata.get("room_id", request.conversation_id),
            "thread_root_event_id": request.metadata.get("thread_root_event_id", ""),
            "actor_id": request.actor_id,
        }
        _tool_context.active_request_id = request.id
        self._result_capture.reset_trace()
        result = await asyncio.to_thread(self._agentic_loop_sync, prompt)

        if isinstance(result, _AskUserWaiting):
            logger.info(
                "AskUser: question %s waiting for reply, freeing thread",
                result.question_id,
            )
            self._request_metadata.pop(request.id, None)
            return

        text = result
        trace_steps = self._result_capture.trace
        self._pending_user_messages[request.id] = (
            request.actor_id,
            request.conversation_id,
            current_user_msg,
            trace_steps,
        )
        output: dict[str, Any] = {
            "content": text,
            "reply_route": self._reply_route_from_request(request),
        }
        response = LLMResponse(
            request_id=request.id,
            output=output,
            metadata={
                "source": "keel",
                "hop_count": request.metadata.get("hop_count", 0),
                "correlation_id": request.metadata.get("correlation_id", request.id),
            },
        )
        await self.response_adapter.handle_response(response)
        self._request_metadata.pop(request.id, None)

    def _agentic_loop_sync(self, prompt: str) -> str | _AskUserWaiting:
        """Run the tool-calling loop synchronously (intended for asyncio.to_thread).

        Calls keel_engine.run() repeatedly, feeding each tool's result back
        as context until the LLM calls the Reply tool or max_steps is reached.

        Returns a string (the final reply) or an _AskUserWaiting sentinel if
        the AskUser tool was invoked and the thread should be freed.
        """
        tool_results: list[tuple[int, str, str]] = []

        for step in range(self.settings.agent_max_steps):
            current_prompt = self._build_step_prompt(prompt, tool_results)
            result = self.keel_engine.run(current_prompt, self.system_prompt)

            if isinstance(result, FailureReport):
                logger.error(
                    "keel failed after %s attempts at step %d: %s",
                    result.attempts,
                    step,
                    result.errors,
                )
                return self.settings.error_reply

            captured = self._result_capture.last_result
            tool_name = result.tool_name

            if tool_name == "Reply":
                if isinstance(captured, str):
                    return captured
                return str(captured) if captured is not None else self.settings.error_reply

            if (
                tool_name == "AskUser"
                and isinstance(captured, dict)
                and captured.get("__ask_user_waiting")
            ):
                return _AskUserWaiting(
                    question_id=captured["question_id"],
                    original_prompt=prompt,
                    tool_history=list(tool_results),
                )

            serialized = json.dumps(captured) if isinstance(captured, dict) else str(captured)
            tool_results.append((step + 1, tool_name, serialized))
            logger.info(
                "agentic step %d: tool=%r result_len=%d",
                step + 1,
                tool_name,
                len(serialized),
            )

        logger.error(
            "agentic loop exhausted %d steps without Reply for prompt=%r",
            self.settings.agent_max_steps,
            prompt[:120],
        )
        return self.settings.error_reply

    def _build_step_prompt(
        self,
        original: str,
        tool_results: list[tuple[int, str, str]],
    ) -> str:
        """Compose the prompt for the next agentic step.

        On the first step (no prior results) the original prompt is returned
        unchanged.  On subsequent steps the tool result history is appended so
        the LLM has full context before choosing its next action.
        """
        if not tool_results:
            return original

        lines: list[str] = [original, "", "Tool results so far:"]
        for step_num, name, serialized in tool_results:
            lines.append(f"  [step {step_num}] {name} → {serialized}")
        lines += [
            "",
            "You have the results above. Respond to the user now using the Reply tool.",
        ]
        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        base_prompt = prompts.system_prompt(self.registry)
        if not self.settings.llm.system_prompt:
            return base_prompt
        return f"{self.settings.llm.system_prompt.strip()}\n\n{base_prompt}"

    def _reconstruct_prompt_with_answer(
        self,
        original_prompt: str,
        tool_history: list[tuple[int, str, str]],
        question: str,
        answer: str,
    ) -> str:
        """Reconstruct a prompt with the original context, tool history, and user's answer.

        This is used to resume an agentic loop after an AskUser question has been answered.
        """
        lines = [original_prompt, "", "Tool results so far:"]
        for step_num, name, result in tool_history:
            lines.append(f"  [step {step_num}] {name} → {result}")
        lines += [
            f"  [step {len(tool_history) + 1}] AskUser → asked: {question}",
            "",
            f"User answered: {answer}",
            "",
            "Continue your task using the user's answer. Respond with the Reply tool.",
        ]
        return "\n".join(lines)

    def _render_request(self, request: LLMRequest) -> str:
        """Flatten a Beacon request into a prompt Keel can process."""
        lines: list[str] = [
            f"conversation_id: {request.conversation_id}",
            f"actor_id: {request.actor_id}",
        ]

        grounding = build_grounding_context(
            model=self.settings.llm.model,
            actor_id=request.actor_id,
        )
        lines.append("")
        lines.append(grounding)

        memory_system_msgs = [
            m for m in request.messages if m.get("role") == "system"
        ]
        history_msgs = [
            m for m in request.messages
            if m.get("role") != "system" and m.get("role") != "user"
        ]
        user_msgs = [
            m for m in request.messages if m.get("role") == "user"
        ]

        for msg in memory_system_msgs:
            content = msg.get("content", "")
            lines.append("")
            lines.append(content)

        if history_msgs:
            lines.append("")
            lines.append("Previous conversation:")
            for msg in history_msgs:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                lines.append(f"{role}: {content}")

        for msg in user_msgs:
            lines.append(f"\nuser: {msg.get('content', '')}")

        if request.hints:
            lines.append(f"hints: {json.dumps(request.hints)}")
        if request.tools:
            lines.append(f"tools: {json.dumps(request.tools)}")

        return "\n".join(lines)

    def _extract_response_text(self, output: dict[str, Any]) -> str:
        content = output.get("content", "")
        if isinstance(content, str):
            return content.strip()
        return self.settings.error_reply

    def _reply_route_from_request(self, request: LLMRequest) -> dict[str, str]:
        metadata = request.metadata
        route: dict[str, str] = {}

        room_id = str(metadata.get("room_id", request.conversation_id)).strip()
        if room_id:
            route["room_id"] = room_id

        reply_to_event_id = str(metadata.get("reply_to_event_id", "")).strip()
        if reply_to_event_id:
            route["reply_to_event_id"] = reply_to_event_id

        thread_root_event_id = str(metadata.get("thread_root_event_id", "")).strip()
        if thread_root_event_id:
            route["thread_root_event_id"] = thread_root_event_id

        return route

    def _extract_reply_route(self, output: dict[str, Any]) -> tuple[str, str | None, str | None]:
        route = output.get("reply_route", {})
        if not isinstance(route, dict):
            return "", None, None

        room_id = str(route.get("room_id", "")).strip()
        if not room_id:
            return "", None, None

        reply_to_event_id = str(route.get("reply_to_event_id", "")).strip() or None
        thread_root_event_id = str(route.get("thread_root_event_id", "")).strip() or None
        return room_id, reply_to_event_id, thread_root_event_id
