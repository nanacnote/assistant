# interaction

User interaction tools for the assistant. Enables the LLM to ask clarifying questions mid-conversation.

## Tools

| Tool | Description | Role |
|---|---|---|
| `AskUser` | Sends a clarifying question to a Matrix room and blocks (up to 60s) for the user's reply in the same thread | `meta` |

## How it works

1. The LLM calls `AskUser` with a question text
2. The tool sends the question to the Matrix room via `MatrixClient`
3. It blocks on a `threading.Event` waiting for the user's reply
4. When the `AssistantRuntime` receives a message in the same thread, it matches it to the pending question and unblocks the tool
5. The user's reply is returned to the LLM as the tool result

## Structure

| File | Role |
|---|---|
| `tools.py` | `AskUser` tool registration -- requires `matrix_client`, `pending_questions` dict, and `request_metadata` |

## How it fits

Registered by `builtin_tools/__init__.py` at startup. The runtime passes its `MatrixClient`, the `_pending_questions` dict, and `_request_metadata` so the tool can send messages and coordinate blocking with the message handler in `runtime.py`.
