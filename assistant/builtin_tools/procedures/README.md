# procedures

Procedure memory tools for the assistant. Enables the LLM to save and retrieve multi-step procedures for future reference.

## Tools

| Tool | Description |
|---|---|
| `SaveProcedure` | Saves a named multi-step procedure (with triggers and steps) into long-term memory |
| `PlanTask` | Looks up stored procedures matching a task description to guide planning |

## How it works

- `SaveProcedure` stores a procedure via `MemoryService.save_procedure()`, which persists it to the `procedure_memories` PostgreSQL table with full-text search support.
- `PlanTask` queries `MemoryService.get_relevant_procedures()` to find procedures whose name, description, triggers, or steps match the task query.

## Structure

| File | Role |
|---|---|
| `tools.py` | Keel tool registrations for both tools |

## How it fits

Registered by `builtin_tools/__init__.py` only when a `memory_service` is available. The tools bridge the LLM and the `MemoryService` (from `assistant/memory/`), which handles storage and retrieval. Procedures extracted automatically from multi-step tool traces are stored alongside manually saved ones.
