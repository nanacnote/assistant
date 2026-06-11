"""Tests for the assistant runtime scaffolding."""

import asyncio
import types
from unittest.mock import DEFAULT, AsyncMock, MagicMock, patch

import pytest

from assistant.config import AssistantSettings, SettingsError
from assistant.matrix import MatrixClient
from assistant.runtime import AssistantRuntime, _ResultCapture
from assistant.tools import build_tool_registry, load_tool_modules


def test_settings_defaults() -> None:
    settings = AssistantSettings()
    assert settings.event_workers == 2
    assert settings.queue_size == 1000
    assert settings.log_level == "INFO"
    assert settings.agent_max_steps == 10


def test_tool_registry_has_reply_tool() -> None:
    registry = build_tool_registry()
    load_tool_modules(registry, ("assistant.builtin_tools",))
    assert registry.get("Reply") is not None


def test_settings_from_env_reads_matrix_and_llm_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSISTANT_MATRIX_HOMESERVER_URL", "https://matrix.example.com")
    monkeypatch.setenv("ASSISTANT_MATRIX_USER_ID", "@assistant:example.com")
    monkeypatch.setenv("ASSISTANT_MATRIX_ACCESS_TOKEN", "token")
    monkeypatch.setenv("ASSISTANT_LLM_API_URL", "https://api.example.com/v1/chat/completions")
    monkeypatch.setenv("ASSISTANT_LLM_API_KEY", "secret")
    monkeypatch.setenv("ASSISTANT_LLM_MODEL", "gpt-4.1-mini")

    settings = AssistantSettings.from_env()

    assert settings.matrix.homeserver_url == "https://matrix.example.com"
    assert settings.matrix.user_id == "@assistant:example.com"
    assert settings.llm.api_url == "https://api.example.com/v1/chat/completions"
    assert settings.llm.model == "gpt-4.1-mini"


def test_validate_requires_matrix_and_llm_configuration() -> None:
    with pytest.raises(SettingsError):
        AssistantSettings().validate()


def test_settings_parses_tool_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSISTANT_TOOL_MODULES", "a.tools, b.tools ,c.tools")
    settings = AssistantSettings.from_env()
    assert settings.tool_modules == ("a.tools", "b.tools", "c.tools")


def test_load_tool_modules_requires_register_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("fake_tools_without_register")

    def fake_import(_name: str):
        return module

    monkeypatch.setattr("assistant.tools.import_module", fake_import)

    with pytest.raises(ValueError):
        load_tool_modules(build_tool_registry(), ("fake_tools_without_register",))


# ---------------------------------------------------------------------------
# agent_max_steps config
# ---------------------------------------------------------------------------


def test_settings_from_env_reads_agent_max_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSISTANT_AGENT_MAX_STEPS", "5")
    settings = AssistantSettings.from_env()
    assert settings.agent_max_steps == 5


# ---------------------------------------------------------------------------
# _ResultCapture middleware
# ---------------------------------------------------------------------------


def test_result_capture_starts_empty() -> None:
    capture = _ResultCapture()
    assert capture.last_result is None


def test_result_capture_stores_and_retrieves_result() -> None:
    capture = _ResultCapture()
    capture.post_execute(MagicMock(), "hello")
    assert capture.last_result == "hello"
    capture.post_execute(MagicMock(), {"key": "value"})
    assert capture.last_result == {"key": "value"}


def test_result_capture_pre_execute_is_noop() -> None:
    capture = _ResultCapture()
    capture.pre_execute(MagicMock())  # must not raise
    assert capture.last_result is None


# ---------------------------------------------------------------------------
# AssistantRuntime._agentic_loop_sync helpers
# ---------------------------------------------------------------------------

_IO_PATCHES = {
    "MatrixAdapter": DEFAULT,
    "ResponseAdapter": DEFAULT,
    "EventBus": DEFAULT,
    "MatrixClient": DEFAULT,
    "ReactionEngine": DEFAULT,
    "ContextBuilder": DEFAULT,
    "Dispatcher": DEFAULT,
    "CoreEngine": DEFAULT,
    "KeelEngine": DEFAULT,
    "OpenAICompatibleLLM": DEFAULT,
    "build_memory_service": DEFAULT,
    "build_history_fetcher": DEFAULT,
}


def _make_runtime(settings: AssistantSettings | None = None) -> AssistantRuntime:
    """Build an AssistantRuntime with all I/O dependencies mocked out."""
    if settings is None:
        settings = AssistantSettings(agent_max_steps=10)
    with patch.multiple("assistant.runtime", **_IO_PATCHES):
        runtime = AssistantRuntime(settings)
        runtime.memory_service = MagicMock()
        runtime.memory_service.get_relevant_memories = AsyncMock(return_value=[])
        runtime.memory_service.store_turn = AsyncMock()
        runtime.memory_service.extract_and_store_facts = AsyncMock()
        return runtime


# ---------------------------------------------------------------------------
# _agentic_loop_sync behaviour
# ---------------------------------------------------------------------------


def test_agentic_loop_returns_reply_text() -> None:
    runtime = _make_runtime()
    reply_tool = MagicMock()
    reply_tool.tool_name = "Reply"

    def fake_run(prompt: str, system_prompt: str) -> MagicMock:
        runtime._result_capture._local.result = "Your son's birthday is June 6th, 2025."
        return reply_tool

    runtime.keel_engine.run.side_effect = fake_run

    result = runtime._agentic_loop_sync("when is my son's birthday?")

    assert result == "Your son's birthday is June 6th, 2025."
    assert runtime.keel_engine.run.call_count == 1


def test_agentic_loop_feeds_tool_result_back() -> None:
    runtime = _make_runtime()
    search_tool = MagicMock()
    search_tool.tool_name = "SearchEvents"
    reply_tool = MagicMock()
    reply_tool.tool_name = "Reply"

    call_count = 0

    def fake_run(prompt: str, system_prompt: str) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            runtime._result_capture._local.result = {
                "events": [{"title": "Son's Birthday"}],
                "count": 1,
            }
            return search_tool
        runtime._result_capture._local.result = "Your son's birthday is June 6th, 2025."
        return reply_tool

    runtime.keel_engine.run.side_effect = fake_run

    result = runtime._agentic_loop_sync("when is my son's birthday?")

    assert result == "Your son's birthday is June 6th, 2025."
    assert runtime.keel_engine.run.call_count == 2
    second_prompt = runtime.keel_engine.run.call_args_list[1][0][0]
    assert "SearchEvents" in second_prompt
    assert "Son's Birthday" in second_prompt
    assert "Reply tool" in second_prompt


def test_agentic_loop_returns_error_on_failure_report() -> None:
    from keel.core.engine import FailureReport

    runtime = _make_runtime()
    failure = FailureReport(attempts=3, error_levels=["SYNTAX"], last_raw_output="bad", errors=[])
    runtime.keel_engine.run.return_value = failure

    result = runtime._agentic_loop_sync("do something")

    assert result == runtime.settings.error_reply
    assert runtime.keel_engine.run.call_count == 1


def test_agentic_loop_returns_error_when_max_steps_exhausted() -> None:
    runtime = _make_runtime(AssistantSettings(agent_max_steps=3))
    non_reply_tool = MagicMock()
    non_reply_tool.tool_name = "SearchEvents"

    def fake_run(prompt: str, system_prompt: str) -> MagicMock:
        runtime._result_capture._local.result = {"events": [], "count": 0}
        return non_reply_tool

    runtime.keel_engine.run.side_effect = fake_run

    result = runtime._agentic_loop_sync("keep looping")

    assert result == runtime.settings.error_reply
    assert runtime.keel_engine.run.call_count == 3


def test_matrix_client_builds_thread_reply_payload() -> None:
    client = MatrixClient(AssistantSettings().matrix)

    payload = client._build_text_payload(
        "hello",
        reply_to_event_id="$reply",
        thread_root_event_id="$root",
    )

    assert payload["msgtype"] == "m.text"
    assert payload["body"] == "hello"
    assert payload["m.relates_to"]["rel_type"] == "m.thread"
    assert payload["m.relates_to"]["event_id"] == "$root"
    assert payload["m.relates_to"]["m.in_reply_to"]["event_id"] == "$reply"


def test_runtime_routes_reply_to_source_matrix_thread() -> None:
    async def _run() -> None:
        runtime = _make_runtime()
        runtime.response_adapter.handle_response = AsyncMock()
        runtime.matrix_client.send_text = AsyncMock()
        runtime._agentic_loop_sync = MagicMock(return_value="threaded reply")

        request = MagicMock()
        request.id = "req-1"
        request.conversation_id = "!room:example.com"
        request.metadata = {
            "source_event_id": "evt-internal-1",
            "room_id": "!room:example.com",
            "reply_to_event_id": "$event-123",
            "thread_root_event_id": "$thread-root-1",
            "hop_count": 0,
        }
        request.messages = [{"role": "user", "content": "hello"}]
        request.hints = {}
        request.tools = {}
        request.actor_id = "@user:example.com"
        await runtime._dispatch_via_keel(request)

        response_event = types.SimpleNamespace(
            payload={
                "request_id": "req-1",
                "output": {
                    "content": "threaded reply",
                    "reply_route": {
                        "room_id": "!room:example.com",
                        "reply_to_event_id": "$event-123",
                        "thread_root_event_id": "$thread-root-1",
                    },
                },
            }
        )
        await runtime._handle_llm_response_event(response_event)

        runtime.matrix_client.send_text.assert_awaited_once_with(
            "!room:example.com",
            "threaded reply",
            reply_to_event_id="$event-123",
            thread_root_event_id="$thread-root-1",
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Memory service graceful fallback
# ---------------------------------------------------------------------------


def test_runtime_starts_when_memory_service_fails() -> None:
    """Runtime must start and respond even if the memory DB is unreachable."""
    settings = AssistantSettings(agent_max_steps=10)
    patches = {**_IO_PATCHES}
    patches.pop("build_memory_service")

    with patch.multiple("assistant.runtime", **patches):
        with patch("assistant.runtime.build_memory_service") as mock_build_mem:
            mock_build_mem.side_effect = ConnectionError("database unreachable")
            runtime = AssistantRuntime(settings)

    assert runtime.memory_service is not None
    assert runtime.keel_engine is not None
    assert runtime.context_builder is not None


