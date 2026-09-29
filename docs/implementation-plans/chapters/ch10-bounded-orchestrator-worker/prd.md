# Chapter 10 PRD: Build a Bounded Orchestrator-Worker Flow

This project implements the hands-on work for Chapter 10, **Agentic AI and Orchestration Patterns**. It applies the secured [Chapter 9 capability boundary](../ch09-secure-extension-pack/prd.md) to the same policy-triage scenario as a deterministic workflow, a single tool-using agent, a fixture-based browser/computer-use path, and an orchestrator-worker topology. It produces the selected logical state graph for Chapter 11 to make crash-safe. See the [architecture](./architecture.md).

## Problem

Agent frameworks make it easy to add routers, planners, workers, handoffs, and browser/computer-use behavior before a task proves that it needs them. More agents increase context movement, latency, cost, supervision burden, and attack surface. PolicyOps needs an apples-to-apples implementation of deterministic, single-agent, browser/computer-use, and orchestrator-worker topologies using one state, tool, evaluation, and telemetry contract. Known rules must stay deterministic; delegation must be bounded and attributable; screen/DOM observations must be treated as untrusted data; writes must retain Chapter 9 approval; and multi-agent/A2A use must be recommended only when measured gains justify it.

## Goals

- Implement one policy-triage scenario as a deterministic workflow, single tool-using agent, and orchestrator-worker design.
- Add one fixture-based browser/computer-use task that fills a mock approval form through the Chapter 9 adapter boundary without bypassing exact-effect approval.
- Keep routing, joins, budgets, approvals, and final mutations deterministic across variants.
- Use an in-process signed delegation contract for the core and add A2A only in an optional independent-runtime variant.
- Isolate worker context and authority, validate typed results, handle conflicts and timeouts, and expose pause/cancel states.
- Compare task success, trace quality, latency, model/tool/browser actions, cost estimate, cost per successful outcome, and operational/security risk using Chapter 2 evaluations.
- Produce a topology ADR whose valid conclusion may be the simpler workflow or single agent.

## Non-goals

- Durable queues, crash recovery, exactly-once delivery, or resumable loop checkpoints; Chapter 11 owns those mechanics.
- Fleet management, open-ended peer conversation, self-modifying prompts, or autonomous permission changes.
- Binding the canonical design to one orchestration framework.
- Treating role labels alone as independent agents.
- Reimplementing Chapter 9 tool security, approval, extension packaging, or revocation.

## Users

- **AI engineer:** implements and compares orchestration topologies against one contract.
- **Platform engineer:** evaluates framework portability and independent runtime boundaries.
- **Security engineer:** audits identity, authority, delegation, approval, and merge behavior.
- **Product/evaluation owner:** selects the least complex topology that clears predeclared quality needs.

## User stories

- As an AI engineer, I can run the same triage cases through three variants and compare results without changing fixtures or metrics.
- As a security engineer, I can trace every worker task to an accountable principal, allowed tools, evidence, budget, expiry, and signed delegation.
- As an operator, I can inspect, pause, cancel, or resume at a modeled human-interrupt state without hidden side effects.
- As an evaluation owner, I can reject multi-agent complexity when it does not clear predeclared gain and risk thresholds.

## Functional requirements

- **CH10-FR-001 — Canonical state graph:** Define framework-neutral typed states, transitions, guards, fan-out/fan-in, cancellation, human-interrupt points, and terminal outcomes for the policy-triage scenario.
- **CH10-FR-002 — Deterministic workflow:** Implement known classification/routing rules and fixed evidence/validation steps without model calls; approved ticket creation uses the Chapter 9 `ToolPort`.
- **CH10-FR-003 — Single-agent variant:** Let one replay-backed agent choose among an allowlisted subset of read tools and propose a ticket, while deterministic guards enforce budgets, result schemas, approval, and terminal states.
- **CH10-FR-004 — Orchestrator-worker variant:** Have an orchestrator create bounded retrieval and validation tasks, run genuinely independent work concurrently, and merge typed results through deterministic policies.
- **CH10-FR-004A - Browser/computer-use fixture:** Implement a fixture-only browser/computer-use variant that reads DOM/screen observations, fills a mock approval form, records action traces, and hands the final mutation back to the Chapter 9 approval-bound `ToolPort`.
- **CH10-FR-005 — Delegation contract:** Include task and run IDs, accountable principal, worker identity, evidence references, allowed tools/actions, budget, output schema, success criteria, expiry, parent delegation, nonce, and signature.
- **CH10-FR-006 — Authority containment:** A worker cannot widen scope, delegate beyond its grant, create a final ticket, or convert evidence/memory into authority. Final writes require the same Chapter 9 effect-bound approval.
- **CH10-FR-007 — Result validation and merge:** Validate worker identity/signature, task binding, schema, evidence lineage, budget, and expiry; deterministically resolve duplicates and surface unresolved conflicts or merge collisions for review.
- **CH10-FR-008 — Failure handling:** Apply bounded timeouts, cancellation, one declared retry where safe, typed partial results, and explicit terminal failure for worker timeout, invalid scope, conflicting results, and merge collision.
- **CH10-FR-009 — Human interruption:** Model `awaiting_review`, `paused`, `cancelled`, and `resumed` transitions and expose a snapshot sufficient for Chapter 11 to persist later.
- **CH10-FR-010 — Optional A2A adapter:** In a separate independent-runtime profile, map the delegation/result contract to a pinned A2A adapter and record whether ownership, trust, deployment, or interoperability boundaries justify it.
- **CH10-FR-011 — Topology comparison:** Run identical evaluation cases through the deterministic, single-agent, browser/computer-use, and orchestrator-worker variants and produce a report and ADR against predeclared task-success, latency, cost, cost-per-successful-outcome, trace, supervision, and risk thresholds.

- **CH10-FR-012 — Run-local fan-out admission:** Reserve the complete run-local worker, concurrency, model-call, token, tool, time, and spend budget before spawning a fan-out group. If the reservation cannot be made, emit typed `capacity_unavailable` and follow the declared simpler, review, or terminal path; release unused reservations deterministically after join or cancellation.

## Non-functional requirements

- **CH10-NFR-001:** The required profile uses a deterministic replay `ModelClient`, in-process workers, test signing key, and no paid model/API credential.
- **CH10-NFR-002:** All variants share the same `TaskState`, `ToolPort`, evaluation cases, outcome schema, action-trace schema where applicable, and OpenTelemetry semantic conventions.
- **CH10-NFR-003:** Deterministic cases reach identical expected environment state across variants; known rules invoke zero model calls.
- **CH10-NFR-004:** Every run has finite model/tool/worker/token/time budgets and terminates when any hard limit is reached.
- **CH10-NFR-005:** Framework adapters contain no domain policy; replacing an adapter does not change state-transition or evaluation fixtures.

## Security and privacy requirements

- **CH10-SEC-001:** Derive the accountable principal from authenticated context and bind it into signed delegation; agents cannot self-assert identity or tenant.
- **CH10-SEC-002:** Apply least authority to each worker using explicit tool/action allowlists and evidence scope; deny unspecified capability.
- **CH10-SEC-003:** Treat worker output, tool observations, retrieved evidence, and A2A messages as untrusted; validate before state mutation or merge.
- **CH10-SEC-003A:** Treat DOM/screen observations and browser action results as untrusted; bind them to fixture identity, sandbox/profile constraints, and the Chapter 9 capability boundary before they influence state.
- **CH10-SEC-004:** Preserve Chapter 9 approval, hook, idempotency, extension-status, and revocation checks at the final tool boundary.
- **CH10-SEC-005:** Redact sensitive content from traces and delegation records while retaining hashes, identities, scope, decisions, and provenance.
- **CH10-SEC-006:** Reject expired, replayed, incorrectly signed, parentless, or scope-widened delegations and results.

## Fixtures and data

The supplied policy-triage suite includes deterministic routing cases, ambiguous cases, two parallel evidence tasks, expected validation findings, approval fixtures, a mock approval-form browser fixture, and expected environment state. Fault fixtures cover worker timeout, conflicting results, invalid scope, signature failure, result replay, browser/profile mismatch, DOM/screen confusion, and merge-key collision. The replay `ModelClient` provides fixed decisions and usage records. An optional independent-runtime fixture runs one worker behind the pinned A2A adapter; the required core stays in process.

## External behavior

- `POST /v1/triage/runs` accepts scenario, variant (`workflow`, `single_agent`, `orchestrator_worker`), principal, budgets, and idempotency key.
- `GET /v1/triage/runs/{id}` returns current typed state, budget consumption, delegated tasks, results, and available controls.
- `POST /v1/triage/runs/{id}:pause|:resume|:cancel` applies state-version checks; Chapter 10 guarantees logical transitions, not crash durability.
- Worker port: `execute(DelegatedTask) -> WorkerResult`; optional A2A transport maps this contract without changing it.
- `uv run policyops verify ch10 --profile fixture --junit build/ch10/junit.xml --evidence build/ch10` runs all variants and drills.

## Acceptance criteria and traceability

1. Given a known deterministic rule, all variants reach the same expected state and record zero model calls for that decision (`CH10-FR-002`, `CH10-NFR-003`).
2. Given a delegated task, traces identify principal, worker, task, evidence, allowlisted actions, budget, expiry, signature, and parent (`CH10-FR-005`, `CH10-SEC-001`).
3. Given invalid or widened scope, an expired/replayed delegation, or malformed worker output, validation rejects it before merge or tool execution (`CH10-FR-006`, `CH10-FR-007`, `CH10-SEC-006`).
4. Given timeout, conflicting results, or merge collision, the flow follows its declared bounded failure path and does not silently choose a final action (`CH10-FR-008`).
5. Given any ticket mutation, Chapter 9 exact-effect approval and idempotency still apply regardless of topology (`CH10-SEC-004`).
6. Given deterministic fixture cases, all three variants produce the same expected environment state and one common output schema (`CH10-NFR-002`, `CH10-NFR-003`).
7. The ADR recommends browser/computer-use or orchestrator-worker only if its predeclared task-success gain clears 10 percentage points or it demonstrates required UI, independent parallel, or context-isolation value, while its latency, cost, cost-per-successful-outcome, supervision burden, and risk remain within declared budgets; otherwise a simpler topology is the accepted result (`CH10-FR-011`).
8. A2A is implemented only when the independent-runtime profile has a real ownership, trust, deployment, or interoperability boundary; otherwise a no-use ADR is accepted (`CH10-FR-010`).
9. Given the canonical state graph and identical fixtures, the deterministic, single-agent, and orchestrator-worker adapters validate every transition and terminal outcome; the worker variant runs genuinely independent tasks before a deterministic join; and pause/review/cancel/resume preserves a snapshot sufficient for Chapter 11 (`CH10-FR-001`, `CH10-FR-003`, `CH10-FR-004`, `CH10-FR-009`).
10. Given insufficient run-local capacity, no partial fan-out is spawned, `capacity_unavailable` is recorded, the declared fallback or terminal transition occurs, and all acquired reservations are released after cancellation or join (`CH10-FR-012`).

## Success metrics

Report task success, deterministic-case agreement, route/merge accuracy, model/tool/worker calls, browser action count where applicable, token and cost estimates, cost per successful outcome, p50/p95 latency, trace completeness, budget violations, invalid delegation rejection, approval bypasses, human-interrupt correctness, and operator steps. Hard gates are zero authority widening, zero approval bypass, deterministic joins, and finite termination.

## Prerequisites and dependencies

Use Python 3.12+, `uv`, FastAPI, Pydantic, pytest, OpenTelemetry, Docker Compose, Chapter 2 evaluations, Chapter 9 tool/approval boundary, shared `TaskState`, replay model, and test signing key. In-process async execution is sufficient for the core; PostgreSQL, Redis, durable queues, and workflow engines are intentionally deferred to Chapter 11. Lock optional A2A versions at implementation kickoff.

## Risks and mitigations

- **Role-play mistaken for architecture:** require independent context or parallel work and measurable comparison.
- **Policy duplicated across adapters:** keep transitions/guards in the canonical state graph.
- **Worker result trusted implicitly:** verify signature, task binding, schema, evidence, budget, and expiry.
- **Fan-out explodes cost:** atomically reserve hard worker/task/concurrency/call/token/spend budgets before spawn and return typed `capacity_unavailable` when the group cannot fit.
- **Framework lock-in:** test each adapter against framework-neutral contracts.
- **A2A added for novelty:** require a documented independent boundary or record no use.

## Delivery milestones

1. Define `TaskState`, topology-independent state graph, budgets, outcomes, and evaluation fixtures.
2. Implement deterministic workflow and single-agent adapters over shared ports.
3. Add signed delegation, orchestrator-worker fan-out/fan-in, validation, and merge policies.
4. Implement logical human interrupts and all failure drills; optionally add independent A2A profile.
5. Instrument, compare topologies, write ADR, gate CI, and register selected graph/delegation evidence for the capstone.

## Future extensions

Chapter 11 will persist the selected state graph, make side effects crash-safe, and provide durable pause/resume. The optional A2A worker can later move to an independently operated runtime without changing the delegation contract.

## Lab delivery contract

- **Starter:** `ed2-v1.0-ch10-start` with policy-triage scenario, shared `TaskState`/`ToolPort`, and Chapter 2 evaluations.
- **Task:** implement deterministic, single-agent, fixture browser/computer-use, and orchestrator-worker variants; start in process and add A2A only for a justified independent-runtime variant.
- **Drill:** worker timeout, conflicting results, invalid delegation scope, browser/profile mismatch, DOM/screen confusion, and merge collision.
- **Artifact:** framework-neutral state graph, four adapters, signed delegation record, browser action-trace record, traces, comparison report, and topology ADR.
- **Acceptance:** no model for known rules, deterministic joins, traceable scope/identity, approved writes, fixture browser/computer-use cannot bypass the Chapter 9 boundary, measured multi-agent recommendation, justified A2A/no-use outcome, and identical deterministic environment state.
- **Verify:** `uv run policyops verify ch10 --profile fixture --junit build/ch10/junit.xml --evidence build/ch10`.
- **Handoff:** create `work/ch10`, compare it with `ed2-v1.0-ch10-solution`, and register state graph, topology comparison, delegation contract, failure tests, and A2A implementation or no-use ADR in `capstone/traceability.yaml`; Chapter 11 makes the accepted topology crash-safe.
- **Execution:** 4–6 hours with Chapter 9 tool, fixtures, replay model, test signing key, and optional A2A adapter; no independent runtime in core.
- **Repository/CI:** `labs/ch10/manifest.toml`, base tag `ed2-v1.0-ch10-start`, and `src/policyops/orchestration`, `schemas/delegation`, `tests/orchestration`, `docs/adrs`; `verify-ch10` runs all earlier gates.
- **Run/cleanup:** `uv sync --frozen`; `uv run policyops env up --lab ch10 --profile fixture`; `uv run policyops verify ch10 --profile fixture --junit build/ch10/junit.xml --evidence build/ch10`; `uv run policyops fault ch10 --scenario all`; `uv run policyops env down --lab ch10` (which must remove test key material).
- **Proposal:** add a small orchestrator-worker design for parallel policy retrieval and validation plus a fixture-based browser/computer-use task that fills a mock approval form while keeping routing, merging, budgets, and final actions deterministic, then compare it with simpler paths.
