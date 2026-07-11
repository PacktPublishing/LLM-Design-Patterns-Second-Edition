# Chapter 11 Project PRD: Make the Agent Loop Resumable

This project implements the hands-on project for Chapter 11, **Harness and Agentic Engineering: Reliable Agents and Reliable Delivery**. It turns the topology selected in [Chapter 10](../ch10-bounded-orchestrator-worker/prd.md) into a crash-consistent action loop and pairs that runtime work with a bounded engineering workflow. The companion [architecture](./architecture.md) defines the implementation boundaries and contracts.

## Product proposal

Use a scoped, test-first engineering workflow to add checkpoints, bounded retries, approval expiry, and idempotent side effects to the PolicyOps agent loop. Interrupt execution at controlled crash windows and resume it without creating a duplicate policy ticket.

## Problem

An agent demo can succeed while its production loop remains unsafe. A worker can crash after creating a ticket but before recording acknowledgement, two workers can race for the same session, or an old approval can be reused after the proposed action changes. At the same time, an engineering agent can expand a small repair into an unrelated refactor and declare success without direct evidence. Chapter 11 needs one focused project that makes both loops inspectable: the product runtime must resume safely, and the change process must prove that the supplied defect was repaired without broadening scope.

## Goals

- Repair one seeded PolicyOps defect through inspect, plan, implement, verify, and fresh-review stages.
- Persist an append-only session history, checkpoints, leases, approvals, effects, and outbox records.
- Guarantee one observable business effect for one idempotency key across all supplied crash windows.
- Resume from verified state without replaying completed external effects.
- Enforce iteration, time, tool, file, destination, and external-effect budgets.
- Produce machine-readable evidence that later chapters can observe, attack, deploy, and govern.

## Non-goals

- Choosing between workflow, single-agent, and multi-agent topology; Chapter 10 owns that decision.
- Building a production telemetry and improvement pipeline; [Chapter 12](../ch12-trace-to-safe-improvement/prd.md) consumes the events produced here.
- Scaling the protocol across brokers, replicas, and failure domains; Chapter 14 owns fleet delivery.
- Requiring a coding-agent subscription, a second person, GitHub branch protection, or paid model access.
- Claiming exactly-once transport. The project provides an effectively-once business outcome inside its declared database and ticket-service boundary.

## Users

- **AI engineer:** implements and tests the state machine and effect protocol.
- **Application developer:** repairs the seeded defect through an allowlisted change surface.
- **Reviewer:** evaluates the scoped plan, diff, tests, and direct API or UI evidence.
- **Operator:** diagnoses stuck sessions and resumes, cancels, or reconciles them from the runbook.
- **Security engineer:** checks approval binding, lease fencing, sandbox limits, and replay safety.

## User stories

- As an AI engineer, I can kill the worker at any supplied crash point and resume the same session without a duplicate ticket.
- As a reviewer, I can see which files were allowed, what changed, which checks ran, and whether any blocking finding remains.
- As an operator, I can distinguish a retryable dependency failure from a policy, authorization, semantic, or permanent failure.
- As an approver, I know an approval authorizes only the exact preview, actor, tenant, expiry window, and action digest I reviewed.
- As a security engineer, I can prove a second worker cannot commit work after losing its lease.

## Functional requirements

- **CH11-FR-001:** The engineering session shall begin with read-only inspection and produce a scoped plan naming allowed files, acceptance checks, and explicit exclusions before mutation.
- **CH11-FR-002:** The change workflow shall reject modifications outside the allowlisted paths and package the diff, automated checks, direct QA evidence, and review findings in a machine-readable review bundle.
- **CH11-FR-003:** The runtime shall model trigger, plan, act, observe, verify, repair, checkpoint, stop, and escalate as explicit states with validated transitions.
- **CH11-FR-004:** Every state transition shall append a versioned event containing session, Chapter 1 request/trace IDs, tenant, actor, configuration, prior-state, new-state, and timestamp fields.
- **CH11-FR-005:** A checkpoint shall identify the last verified event, current budget counters, pending action, approval reference, and resumable state.
- **CH11-FR-006:** A lease shall have an owner, monotonically increasing fencing token, expiry, and renewal timestamp; stale owners shall be unable to append authoritative transitions.
- **CH11-FR-007:** A proposed side effect shall be stored with its canonical preview digest, idempotency key, approval identity, approval expiry, and expected postcondition.
- **CH11-FR-008:** The database transaction that marks an action ready shall also create its outbox record. Delivery retries shall reuse the same idempotency key.
- **CH11-FR-009:** The worker shall classify transient, semantic, policy, authorization, verification, and permanent failures before retry, repair, escalation, or stop.
- **CH11-FR-010:** Replay shall reconstruct state from events without calling models, tools, or external services and without emitting new outbox messages.
- **CH11-FR-011:** The loop shall stop or escalate when any declared iteration, elapsed-time, tool-call, file, destination, effect, or spend budget is exhausted.
- **CH11-FR-012:** The fault harness shall interrupt before effect, after effect before acknowledgement, after checkpoint persistence, and during lease contention, then verify recovery.

## Non-functional requirements

- **CH11-NFR-001:** The fixture profile shall run from a clean checkout without paid credentials or a coding-agent subscription.
- **CH11-NFR-002:** Runtime contracts shall use typed, versioned Pydantic models and deterministic clocks and identifiers in tests.
- **CH11-NFR-003:** The required verification suite shall complete on a developer machine with the declared PostgreSQL and Linux-container prerequisites.
- **CH11-NFR-004:** Database migrations shall be forward-applicable, rollback-aware, and exercised against an empty database.
- **CH11-NFR-005:** All containers shall run as non-root, expose only required ports, and have bounded CPU, memory, and process settings.
- **CH11-NFR-006:** The verifier shall emit JSON, JUnit, trace, dependency, fixture, configuration, and declared-hardware evidence and exit non-zero on any mandatory failure.

## Security and privacy requirements

- **CH11-SEC-001:** Session, event, checkpoint, approval, and idempotency records shall be tenant-scoped at every read and write boundary.
- **CH11-SEC-002:** Approval shall fail when actor, tenant, action digest, preview, scope, or expiry differs from the approved record.
- **CH11-SEC-003:** Event and review bundles shall redact secrets and sensitive payloads while preserving hashes and metadata needed for audit.
- **CH11-SEC-004:** The isolated engineering workspace shall use a declared filesystem and network policy and shall not receive production credentials.
- **CH11-SEC-005:** Lease fencing shall be enforced in the database write predicate, not only in worker memory.
- **CH11-SEC-006:** Replay mode shall use adapters that reject every external effect attempt.

## Starter, fixtures, and data

Start from tag `ed2-v1.0-ch11-start`. The starter will contain a seeded PolicyOps defect, short repository map, isolated-workspace recipe, versioned event schema, evaluator stub, working migration/repository skeletons for events, checkpoints, leases and outbox, a reducer/replay scaffold, deterministic dispatcher seam, named-boundary fault injector, and failing crash-window tests. Readers implement transition policy, atomicity, fencing, approval revalidation, recovery, and verification rather than database/fixture plumbing. PostgreSQL stores runtime state. The ticket service is a deterministic local fixture implementing the Chapter 9 tool contract. A fake clock controls lease and approval expiry. Fixture identities cover two tenants, an approver, an operator, and two competing workers.

Primary paths are `src/policyops/harness`, `src/policyops/worker`, `tests/harness`, `tests/faults`, and `docs/runbooks`. `labs/ch11/manifest.toml` records the fixture hash, services, hardware, network, credentials, commands, cleanup, artifacts, gates, and fault scenarios.

## External behavior

The core will expose a `POST /sessions/{session_id}/run` operation, `POST /sessions/{session_id}/resume`, `POST /sessions/{session_id}/cancel`, and read-only event and checkpoint endpoints. The CLI will provide `policyops session inspect`, `policyops session replay --no-effects`, and `policyops session reconcile`. Mutating calls require tenant and actor envelopes plus expected session version. Conflicts return a typed `409` response; expired or changed approvals return `403`; exhausted budgets return a typed stopped state rather than an implicit retry.

## Required drill

First reject one unrelated proposed change through the allowlist. Then kill the worker before the effect, after the effect but before acknowledgement, after checkpoint persistence, and while a second worker holds the lease. The test must show which event, outbox record, ticket-service response, checkpoint, and fencing token establish the recovery result.

## Required artifacts

Deliver the scoped plan, atomic change, automated and direct-QA evidence, independent review bundle, state table, event and session schemas, sandbox recipe, checkpoint and outbox records, replay tool, fault results, and recovery runbook.

## Acceptance criteria and traceability

- **AC-01 (CH11-FR-001, CH11-FR-002):** Given the seeded defect, when Session A finishes, then the bundle contains a scoped plan, allowlisted atomic diff, reproducible tests, direct API or UI evidence, and no unresolved blocking review finding.
- **AC-02 (CH11-FR-006, CH11-SEC-005):** Given two workers, when the first lease expires and the second receives a higher fence, then writes carrying the old fence fail.
- **AC-03 (CH11-FR-007, CH11-SEC-002):** Given an approved preview, when any bound field changes or approval expires, then execution is denied.
- **AC-04 (CH11-FR-008, CH11-FR-012):** Given every crash window and duplicate delivery, when the session resumes, then one idempotency key produces exactly one ticket.
- **AC-05 (CH11-FR-005, CH11-FR-010):** Given persisted events and a checkpoint, when replay runs, then reconstructed state matches the live result and no tool call occurs.
- **AC-06 (CH11-FR-011):** Given a non-converging fixture, when a budget is reached, then the loop stops with a typed reason and emits no further effect.
- **AC-07 (CH11-NFR-001, CH11-NFR-006):** Given a clean checkout, when the fixture verifier runs, then no paid credential is requested and all required evidence is produced.
- **AC-08 (CH11-FR-002, CH11-FR-003, CH11-FR-004, CH11-FR-009, CH11-FR-010, CH11-FR-012):** Given the allowlisted repair and every seeded runtime failure, then the review bundle rejects out-of-scope changes, transitions and events validate with required identity/configuration fields, failure classification selects the declared action, replay performs no external call, and each crash-window drill reaches the expected state.

## Success metrics

- 100% of supplied crash cases recover to the expected terminal state.
- Zero duplicate tickets across repeated fault-suite runs.
- Zero changes outside the declared engineering allowlist.
- 100% of state-changing events include request/trace, tenant, actor, configuration, and fence metadata.
- Replay produces zero external calls, verified by rejecting adapters.
- Every stopped loop reports a machine-readable stop or escalation reason.

## Execution contract

Core duration is **6-8 hours over two sessions**. Prerequisites are Python 3.12+, `uv`, Git worktrees, PostgreSQL, Linux containers, the seeded defect, event schema, and crash-window harness. Run:

```text
uv sync --frozen
uv run policyops env up --lab ch11 --profile fixture
uv run policyops verify ch11 --profile fixture --junit build/ch11/junit.xml --evidence build/ch11
uv run policyops fault ch11 --scenario all
uv run policyops env down --lab ch11
```

Pull requests run `verify-ch11` plus all earlier regression gates. The optional extension repeats Session A with a subscribed coding-agent CLI, a second human or agent reviewer, and branch protection, then compares quality, latency, supervision, and evidence without weakening the deterministic gate.

## Dependencies and handoff

The project consumes the Chapter 10 state graph and selected control topology, the Chapter 9 ticket adapter, earlier request and evaluation contracts, and an accepted `ch10` checkpoint. It produces the repository map, scoped plan, review evidence, event schemas, sandbox recipe, checkpoint and outbox records, replay output, fault results, and recovery runbook. Register them in `capstone/traceability.yaml`, compare with `ed2-v1.0-ch11-solution`, and tag `ch11-complete`. Chapter 12 consumes these events as continuous evidence; Chapter 14 later distributes the protocol.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Tests model only a convenient crash point | Fault injection targets four named transaction boundaries and records database evidence. |
| Idempotency is mistaken for exactly-once transport | Define the business-effect boundary and retain at-least-once delivery semantics. |
| Lease logic races under a fake clock | Enforce fencing in conditional database writes and add real-clock integration coverage. |
| Engineering workflow dominates the runtime lesson | Time-box Session A and keep its artifact contract separate from Session B. |
| Replay accidentally invokes effects | Use a replay-only dependency container whose model and tool adapters always reject calls. |

## Delivery milestones

1. Freeze schemas, repository map, scoped plan format, and failing acceptance tests.
2. Complete the seeded repair and machine-readable review bundle.
3. Implement events, leases, checkpoints, approvals, and budget enforcement.
4. Implement transactional outbox, idempotent ticket delivery, replay, and reconciliation.
5. Pass the fault matrix, container checks, earlier regressions, and evidence validation.

## Future extensions

Run the same lifecycle through a subscribed coding-agent CLI; add branch-protected independent review; compare PostgreSQL polling with a broker-backed dispatcher; and add an operator console. These extensions must preserve the same event, idempotency, approval, and replay contracts.
