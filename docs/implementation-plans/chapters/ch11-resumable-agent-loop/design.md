# Chapter 11 Design: Resumable Agent Loop Lab

This implementation models the Chapter 11 durability contract without requiring a live PostgreSQL service in the mandatory fixture path. The in-memory repository enforces the same semantics readers must preserve in production: append-only events, optimistic versions, fencing tokens, checkpoints, action intents, outbox delivery, idempotency, replay purity, and review evidence.

## Reader-facing flow

1. Start with a scoped engineering plan and path allowlist.
2. Create a session and append a trigger event.
3. Record the plan, proposed action, and outbox message.
4. Deliver the action through the Chapter 9 ToolPort with a stable idempotency key.
5. Persist an effect receipt and checkpoint.
6. Interrupt at named crash windows and resume from events plus outbox state.
7. Replay with no-effect adapters to prove reconstruction is read-only.
8. Emit a review bundle, fault results, replay result, runbook, and scorecard.

## Files

| Area | Path |
|---|---|
| Schemas | `src/policyops/harness/schemas.py` |
| Runtime and verifier | `src/policyops/harness/service.py` |
| Public API | `src/policyops/harness/__init__.py` |
| Tests | `tests/harness/test_resumable_loop.py` |
| Lab guide | `labs/ch11/README.md` |
| Lab manifest | `labs/ch11/manifest.toml` |

## Key design decisions

- Use an append-only event stream as the source of truth.
- Treat checkpoints as recovery cursors only.
- Enforce fencing on every authoritative append and checkpoint write.
- Create action intent and outbox together before external delivery.
- Reuse the same idempotency key after crashes.
- Install no-effect replay adapters that fail if an external effect is attempted.

## Verification coverage

The Chapter 11 verifier covers:

- scoped engineering review and out-of-scope rejection;
- required event identity/configuration/fence metadata;
- stale fence write rejection;
- crash before effect, after effect before acknowledgement, and after checkpoint;
- one ticket per idempotency key after resume;
- replay without external effects;
- budget exhaustion as a typed stop;
- failure classification and recovery runbook evidence.
