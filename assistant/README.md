# assistant

The top-level package for the assistant runtime. It composes **Beacon** (event-driven framework) and **Keel** (tool-calling engine) to build an LLM-powered chatbot that listens on a Matrix homeserver, processes messages through an agentic tool-calling loop, and replies back to Matrix rooms.

## Architecture

```
Matrix homeserver
  --> MatrixClient (sync polling)
  --> MatrixAdapter --> EventBus
  --> ReactionEngine (MatrixMessageToLLMReaction)
  --> Dispatcher --> KeelEngine (agentic loop)
  --> ResponseAdapter --> MatrixClient.send_text
```

## Key modules

| File | Role |
|---|---|
| `main.py` | CLI entrypoint. Loads `.env`, validates settings, starts the runtime |
| `config.py` | `AssistantSettings`, `MatrixSettings`, `LLMSettings`, `MemorySettings` -- all built from env vars |
| `runtime.py` | `AssistantRuntime` -- central orchestrator wiring Beacon, Keel, Matrix, LLM, and memory |
| `matrix.py` | `MatrixClient` -- login, sync polling, sending messages (with thread support) |
| `llm.py` | `OpenAICompatibleLLM` -- adapter for any OpenAI-compatible `/v1/chat/completions` endpoint |
| `grounding.py` | `build_grounding_context()` -- injects date/time and identity into LLM prompts for temporal awareness |
| `reactions.py` | `MatrixMessageToLLMReaction` -- converts Matrix message events into LLM requests |
| `tools.py` | `build_tool_registry()` / `load_tool_modules()` -- dynamic tool plugin loader |
| `http_client.py` | `JsonHttpClient` -- stdlib-only JSON HTTP client shared by matrix and llm modules |

## Sub-packages

- **`builtin_tools/`** -- Default tool plugins (reply, calendar, wellbeing, interaction, procedures)
- **`memory/`** -- Conversational memory system (working memory, long-term facts, procedure extraction)
- **`storage/`** -- PostgreSQL connection and schema migrations

## How it fits together

`AssistantRuntime` is the hub. On startup it:
1. Creates the Beacon event bus and adapters
2. Connects to Matrix via `MatrixClient`
3. Builds the `MemoryService` (backed by PostgreSQL)
4. Loads tool modules into Keel's `ToolRegistry`
5. Starts sync polling -- each incoming Matrix message flows through the event bus, reaction engine, and into the Keel agentic loop where the LLM decides which tools to call
6. After each turn, the runtime stores the conversation and optionally extracts facts/procedures into long-term memory
