# wellbeing

Wellbeing coaching tools for the assistant. Tracks user check-ins, mood/energy/stress state logs, and provides trend insights.

## Tools

| Tool | Description |
|---|---|
| `RecordCheckIn` | Record a wellbeing check-in (mood, energy, stress ratings + optional notes) |
| `LogState` | Log a point-in-time wellbeing state snapshot |
| `GetHistory` | Retrieve recent check-in and state log history |
| `GetInsights` | Compute wellbeing trends (averages, trend direction, distress detection with guidance) |
| `SetWellbeingPreferences` | Set user preferences for wellbeing tracking |

All tools stamp the authenticated `user_id` via `_actor_field = "user_id"`.

### Usage hints

Several tools declare a `usage_hint` ClassVar describing their intended use case:

| Tool | `usage_hint` |
|---|---|
| `RecordCheckIn` | Use when starting or ending a structured wellness session |
| `LogState` | Use when the user provides numerical ratings or describes their emotional state |
| `GetInsights` | Use before giving advice to ground recommendations in actual data |

## Structure

| File | Role |
|---|---|
| `models.py` | Pydantic domain models: `WellbeingStateSnapshot`, `CheckInRequest`, `StateLogRequest`, `WellbeingPreferences`, `WellbeingInsight`, etc. |
| `ports.py` | `WellbeingRepository` protocol, `UnconfiguredWellbeingRepository` stub, factory |
| `repository.py` | `PostgresWellbeingRepository` -- CRUD against `wellbeing_checkins`, `wellbeing_state_logs`, `wellbeing_preferences` tables |
| `service.py` | `WellbeingService` -- check-in recording, state logging, history retrieval, trend insight computation |
| `tools.py` | Keel tool registrations |

## How it fits

Registered by `builtin_tools/__init__.py` at startup. The `WellbeingService` is instantiated with a `PostgresWellbeingRepository` backed by the shared PostgreSQL connection from `storage/`. Tools are dispatched by Keel during the agentic loop when the LLM determines wellbeing tracking is needed.
