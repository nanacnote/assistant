# builtin_tools

Default tool plugin module for the assistant runtime. Provides all out-of-the-box tools the LLM can call during the agentic loop.

## What it does

`register_tools()` is the plugin entrypoint called by `AssistantRuntime` at startup. It wires each tool domain into Keel's `ToolRegistry`:

- **Reply** (`reply.py`) -- The terminal tool. When the LLM calls `Reply`, the agentic loop stops and the text is sent back to Matrix.
- **Calendar** (`calendar/`) -- CRUD operations for calendar events stored in PostgreSQL.
- **Wellbeing** (`wellbeing/`) -- Check-in recording, state logging, history, and insights for user wellbeing tracking.
- **Interaction** (`interaction/`) -- `AskUser` tool that sends a clarifying question to Matrix and blocks for the user's reply.
- **Procedures** (`procedures/`) -- `SaveProcedure` and `PlanTask` tools for storing and retrieving multi-step procedures from memory.

## How it fits

This module is loaded by `AssistantRuntime` via `tools.load_tool_modules()`. The runtime passes context objects (memory service, Matrix client, pending questions, request metadata) which the individual tool domains use to interact with external systems.

## Tool pattern

Each domain follows the same structure:
- `models.py` -- Pydantic domain objects
- `ports.py` -- Repository protocol + stub + factory
- `repository.py` -- PostgreSQL implementation
- `service.py` -- Validation and orchestration
- `tools.py` -- Keel tool registrations (all tools that need identity declare `_actor_field`)

## Tool metadata

Tools can declare two optional ClassVars:

- **`tool_role`** -- `"action"` (default) or `"meta"`. Classifies the tool's purpose. Meta tools are conversational or control-flow tools (e.g. Reply, AskUser). Action tools perform side-effects (e.g. LogState, CreateEvent).
- **`usage_hint`** -- A one-line string describing when the tool is typically used (e.g. "Use when the user provides numerical ratings").

These are declared on the tool class and available to the prompt generation layer for grouping and contextual guidance.
