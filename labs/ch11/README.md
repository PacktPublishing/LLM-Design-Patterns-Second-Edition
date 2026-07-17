# Chapter 11 Lab: Make the Agent Loop Resumable

This lab makes the selected PolicyOps loop resumable. It uses append-only events, checkpoints, fencing leases, approval-bound action intents, a transactional outbox, idempotent delivery, no-effect replay, and a scoped engineering review bundle.

## What you build

- A scoped engineering plan and review bundle.
- Append-only session events with tenant, actor, request, trace, configuration, and fence metadata.
- Checkpoints as recovery cursors, not alternative history.
- Database-style lease fencing in write predicates.
- Approval-bound action intents and outbox messages.
- Idempotent ticket delivery through the Chapter 9 ToolPort.
- Crash-window recovery and no-effect replay.
- Budget stops with typed reasons.

## Run

```bash
uv run policyops verify ch11 --profile fixture --junit build/ch11/junit.xml --evidence build/ch11
uv run policyops fault ch11 --scenario all
```

## Evidence

The verification command writes:

- `review_bundle.json`
- `fault_results.json`
- `replay_result.json`
- `runbook.json`
- `harness_scorecard.json`

## Production lesson

Idempotency alone is not a resumable loop. The production pattern is event history plus fencing, approval revalidation, transactional intent/outbox, deterministic replay, and operator evidence. After a crash, the system should know whether it has not acted yet, has acted but not acknowledged, has checkpointed, or must stop.
