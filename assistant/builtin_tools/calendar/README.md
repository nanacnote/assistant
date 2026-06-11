# calendar

Calendar management tools for the assistant. Provides CRUD operations and reminders for calendar events stored in PostgreSQL.

## Tools

| Tool | Description |
|---|---|
| `CreateEvent` | Create a new calendar event with optional attendees, recurrence, and reminders |
| `ListEvents` | List events for a given month |
| `ListEventsForYear` | List all events for a given year |
| `SearchEvents` | Search events by title or description |
| `UpdateEvent` | Update an existing event |
| `DeleteEvent` | Delete an event by ID |
| `CheckReminders` | Check for events with upcoming reminders |

All tools stamp the authenticated `user_id` via `_actor_field = "user_id"` so the LLM cannot spoof identity.

## Structure

| File | Role |
|---|---|
| `models.py` | Pydantic domain models: `EventModel`, `EventCreateRequest`, `EventUpdateRequest`, `AttendeeModel`, `RecurrenceRuleModel`, etc. |
| `ports.py` | `CalendarRepository` protocol, `UnconfiguredCalendarRepository` stub, factory |
| `repository.py` | `PostgresCalendarRepository` -- CRUD against the `calendar_events` table |
| `recurrence.py` | `expand_recurrence()` -- generates virtual occurrences for recurring events within a time window |
| `service.py` | `CalendarService` -- validation, timezone normalization, datetime parsing, recurrence expansion, orchestration |
| `tools.py` | Keel tool registrations |

## How it fits

Registered by `builtin_tools/__init__.py` at startup. The `CalendarService` is instantiated with a `PostgresCalendarRepository` (which uses the shared connection from `storage/`). Each tool wraps a service method and is dispatched by Keel when the LLM decides to call it.
