# TODO

## Pending Question TTL Cleanup

**Status:** Not started
**Description:** Wire `PendingQuestionRepository.delete_expired()` to a Beacon scheduled event for automatic cleanup of stale pending questions.
**Location:** `assistant/interaction/repository.py:66-78`
**Blocked by:** Beacon scheduled events feature
**Reference:** Plan at `.mimocode/plans/1781405184555-shiny-eagle.md`
