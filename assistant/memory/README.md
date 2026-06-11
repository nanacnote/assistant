# memory

Conversational memory system for the assistant runtime. Manages working memory (recent turns), long-term facts, and procedure memory.

## What it does

- **Working memory** -- Stores recent conversation turns per user. Retrieved by Beacon's `ContextBuilder` to provide conversation history to the LLM.
- **Fact extraction** -- After each turn, the LLM extracts structured facts (with category and importance) from the conversation and stores them for future retrieval. Duplicate facts (>=70% word overlap with an existing fact) are skipped.
- **History capping** -- Working memory injected into LLM prompts is capped at the 10 most recent messages to control token growth.
- **Procedure extraction** -- When a multi-step tool trace is detected (2+ tools called), the LLM extracts a reusable procedure and stores it.
- **Relevant memory retrieval** -- Before each request, the system searches for facts and procedures relevant to the user's message using PostgreSQL full-text search.

## Structure

| File | Role |
|---|---|
| `models.py` | Pydantic domain models: `ConversationMessage`, `MemoryFact`, `ExtractedFact`, `ProcedureMemory`, `ExtractedProcedure` |
| `ports.py` | `MemoryRepository` protocol (16 methods), `UnconfiguredMemoryRepository` stub, factory with retry logic |
| `repository.py` | `PostgresMemoryRepository` -- CRUD for `conversation_messages`, `memory_facts` (with `tsvector`/`ts_rank` FTS), `procedure_memories` (also FTS). Includes importance decay, pruning, and access tracking |
| `service.py` | `MemoryService` -- orchestrates working memory, fact storage/retrieval, procedure storage/retrieval, importance decay |
| `extraction.py` | `extract_facts()` / `extract_procedure()` -- LLM-based extraction with specialized prompts. Includes fallback JSON parsing that finds arrays/objects embedded in prose. |
| `history.py` | `build_history_fetcher()` -- async callback compatible with Beacon's `ContextBuilder.history_fetcher` |

## How it fits

`AssistantRuntime` creates the `MemoryService` on startup and uses it to:
1. Fetch working memory for conversation context (via `build_history_fetcher`)
2. Retrieve relevant facts and procedures before each request (in `_handle_message_event`)
3. Store conversation turns after each response (in `_handle_llm_response_event`)
4. Extract and store facts/procedures asynchronously after each turn
