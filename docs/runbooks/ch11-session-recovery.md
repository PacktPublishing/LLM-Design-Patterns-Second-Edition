# Chapter 11 session recovery runbook

Use this runbook when a PolicyOps session stops mid-flight and an operator needs to inspect, replay, resume, cancel, or reconcile it without creating a duplicate external effect.

1. Inspect the current state.

   `uv run policyops session inspect <session_id>`

   Confirm the session version, last checkpoint, pending outbox messages, and any recorded receipts.

2. Reconstruct state without external effects.

   `uv run policyops session replay <session_id> --no-effects`

   Use this when you want to prove the event log can rebuild state safely before touching the external system again.

3. Resume the session when work is still in progress.

   `uv run policyops session resume <session_id> --tenant-id tenant_alpha --actor-id actor_reader --expected-version <version>`

   Use resume when the effect has not happened yet or when the effect happened but the acknowledgement event is missing. The runtime reuses the original idempotency key.

4. Reconcile a partially delivered session.

   `uv run policyops session reconcile <session_id>`

   Use reconcile when the outbox still has a pending message and the operator wants the runtime to finish the session with the stored session identity.

5. Cancel the session when the work should stop.

   `uv run policyops session cancel <session_id> --tenant-id tenant_alpha --actor-id actor_reader --expected-version <version>`

   Cancel writes a terminal event and preserves the session history for review.
