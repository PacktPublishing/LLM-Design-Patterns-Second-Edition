# Chapter 8 PRD: Add Governed Long-Term Memory

This project implements the hands-on work for Chapter 8, **Memory Engineering for Stateful AI**. It adds consented persistent memory beside external evidence from [Chapters 6–7](../ch07-graph-retrieval/prd.md); recalled memory is neither a citation nor authority. Its controlled context can inform the extension workflows in [Chapter 9](../ch09-secure-extension-pack/prd.md). See the [architecture](./architecture.md).

## Problem

Stateful assistants benefit from remembering user preferences, task history, learned facts, and approved procedures, but indiscriminate transcript storage creates stale facts, privacy leaks, prompt-injection persistence, and cross-tenant exposure. PolicyOps needs one governed ledger with typed views, explicit write decisions, provenance, consent, optimistic concurrency, expiry, correction, quarantine, inspection, export, and deletion. Memory must improve multi-session work without increasing the agent's permissions.

## Goals

- Represent working, episodic, semantic, and procedural memory as typed views over one auditable ledger.
- Authorize each proposed mutation as `ADD`, `UPDATE`, `DELETE`, or `NOOP` using value, consent, sensitivity, confidence, owner, and scope.
- Preserve provenance and competing facts; reject stale concurrent changes.
- Support task-relevant recall, effective dates, TTL, correction, consolidation, quarantine, export, and deletion.
- Isolate personal, team, tenant, and global scopes and require approval to widen sharing.
- Prove with a deterministic benchmark that memory helps selected multi-session tasks without granting tool authority.

## Non-goals

- Treating the chat transcript, Chapter 6 evidence, or current context window as persistent memory.
- Letting recalled text change permissions, approve actions, or become a system instruction.
- Autonomous global knowledge-base creation or silent cross-user sharing.
- Model training, user profiling for advertising, or an unbounded vector-memory service.
- Chapter 9 tool execution or Chapter 11 durable workflow state.

## Users

- **End user:** consents to, inspects, corrects, exports, and deletes remembered information.
- **AI engineer:** integrates a typed recall and mutation contract.
- **Privacy/security engineer:** verifies isolation, consent, poisoning controls, and erasure.
- **Evaluator:** measures recall quality, forgetting, correction, and downstream task benefit.

## User stories

- As an end user, I can see why a memory exists, where it came from, when it expires, and who can use it.
- As an end user, I can correct or delete a memory and receive a receipt covering all views.
- As an AI engineer, I can request task-relevant recall without allowing memory to expand tool scope.
- As a security engineer, I can quarantine a poisoned instruction and prove it cannot be recalled across tenants.

## Functional requirements

- **CH08-FR-001 — Unified typed ledger:** Store immutable mutation events and materialize working, episodic, semantic, and procedural views from one record model.
- **CH08-FR-002 — Mutation authorization:** Evaluate every proposal as `ADD`, `UPDATE`, `DELETE`, or `NOOP` with machine-readable reasons based on consent, sensitivity, value, confidence, owner, scope, and retention policy.
- **CH08-FR-003 — Provenance and versioning:** Record source type/reference, creation and effective times, owner, tenant, scope, confidence, sensitivity, consent reference, expiry, verification state, and optimistic version.
- **CH08-FR-004 — Concurrency:** Require expected version for update/delete; stale writes return an explicit conflict and do not overwrite the active record.
- **CH08-FR-005 — Governed recall:** Filter by authenticated owner/tenant, allowed scopes, task relevance, status, sensitivity policy, effective time, TTL, and configurable result/token budgets.
- **CH08-FR-006 — Contradiction and correction:** Link competing memories, retain prior versions, prefer declared authority and user corrections, and surface unresolved conflicts.
- **CH08-FR-007 — Consolidation and forgetting:** Consolidate repeated episodes under a documented policy, expire records using a fake clock, and preserve source links from summaries to originals.
- **CH08-FR-008 — Scope controls:** Support personal, team, tenant, and global scopes; widening scope requires a specific approved proposal and cannot be inferred from recalled text.
- **CH08-FR-009 — Poisoning quarantine:** Detect benchmark attack patterns, quarantine suspicious proposed writes, and exclude quarantined content from normal recall while retaining restricted inspection evidence.
- **CH08-FR-010 — User control:** Provide authenticated list, detail, correction, deletion, and export operations plus receipts proving all materialized views were updated.
- **CH08-FR-011 — Benchmark:** Compare no-memory and governed-memory runs for recall, precision, stale rejection, correction, forgetting, isolation, and downstream task success.

## Non-functional requirements

- **CH08-NFR-001:** The core fixture profile is deterministic, uses PostgreSQL and a fake clock, and requires no hosted model or paid credential.
- **CH08-NFR-002:** A mutation is atomic across ledger event, active record, scope index, and deletion/export receipt metadata.
- **CH08-NFR-003:** On the supplied dataset, recall p95 is at most 300 ms before any optional embedding rerank.
- **CH08-NFR-004:** Every decision and recall exclusion is explainable by stable reason codes without logging sensitive content.
- **CH08-NFR-005:** Schemas and lifecycle policy are versioned; incompatible changes require migration and replay tests.

## Security and privacy requirements

- **CH08-SEC-001:** Tenant and subject identity come from authenticated context. The API rejects attempts to query or mutate another subject without an explicit administrative capability.
- **CH08-SEC-002:** Sensitive categories require an active consent receipt and purpose; absent, expired, or mismatched consent fails closed.
- **CH08-SEC-003:** Memory content is untrusted. Recall cannot alter system instructions, tool allowlists, approval state, or delegated authority.
- **CH08-SEC-004:** Deletion removes active rows, derived indexes, consolidation artifacts, and caches; the retained receipt contains IDs and hashes but no deleted content.
- **CH08-SEC-005:** Exports are authenticated, time-limited, encrypted in transit, and audited; observability redacts content and consent tokens.
- **CH08-SEC-006:** Quarantine inspection is a separate privileged operation and quarantined content is not model-visible during normal requests.

## Fixtures and data

The benchmark defines two tenants, multiple users, consent grants and expiry, preferences, policy-task episodes, corrected semantic facts, approved procedures, repeated episodes for consolidation, and poisoned instruction proposals. A fake clock drives effective dates and TTL. Expected decisions and recalls are labeled. The required retriever uses deterministic structured features; an optional semantic adapter may use a verified local model or hosted `ModelClient` without changing the ledger contract.

## External behavior

- `POST /v1/memory/proposals:evaluate` returns a proposed mutation decision and reason codes without writing.
- `POST /v1/memory/records` and `PATCH|DELETE /v1/memory/records/{id}` require consent, expected version, and idempotency key as applicable.
- `POST /v1/memory/recall` accepts task purpose, allowed scopes, effective time, and budgets; it returns typed records, exclusions, and provenance.
- `GET /v1/memory/records`, `GET /v1/memory/records/{id}`, `POST /v1/memory/exports`, and `GET /v1/memory/receipts/{id}` implement user inspection and portability.
- `uv run policyops memory seed|verify|benchmark --profile fixture` provides the local fixture lifecycle and diagnostic surface; these commands call the same application ports and do not introduce a second policy or persistence path.
- `uv run policyops verify ch08 --profile fixture --junit build/ch08/junit.xml --evidence build/ch08` runs lifecycle, privacy, and benchmark gates.

## Acceptance criteria and traceability

1. Given two concurrent updates with the same expected version, exactly one succeeds and the other receives `MEMORY_VERSION_CONFLICT`; provenance remains intact (`CH08-FR-003`, `CH08-FR-004`).
2. Given sensitive content without valid purpose-bound consent, the authorizer chooses `NOOP` and persists no content (`CH08-FR-002`, `CH08-SEC-002`).
3. Given fake-clock advancement, expired records and consolidations derived only from them disappear from normal recall (`CH08-FR-007`).
4. Given deletion, inspection and recall show no active or derived content and an authenticated receipt covers every view (`CH08-FR-010`, `CH08-SEC-004`).
5. Given poisoned text or a cross-tenant request, no unsafe or other-tenant record is returned; poison is quarantined and cannot change authority (`CH08-FR-009`, `CH08-SEC-001`, `CH08-SEC-003`).
6. Given a user correction and an older competing memory, recall prefers the correction while preserving the conflict chain for inspection (`CH08-FR-006`).
7. On labeled multi-session tasks, governed memory improves success over no memory by at least 15 percentage points while precision is at least 0.90 and isolation violations remain zero (`CH08-FR-011`).
8. Given ADD/UPDATE/DELETE/NOOP events across personal, team, tenant, and global fixtures, all four views rebuild from the typed ledger, recall applies owner/tenant/purpose/status/sensitivity/time and token limits, and any scope widening without explicit approval is denied (`CH08-FR-001`, `CH08-FR-005`, `CH08-FR-008`).
9. Given the Chapter 5 planner, `MemoryContextSource` passes the shared two-phase source contract, preserves tenant/provenance/sensitivity/expiry/placement metadata, excludes expired, quarantined, deleted, and other-tenant records, and cannot populate authority, capability, or approval fields (`CH08-FR-005`, `CH08-FR-007`, `CH08-SEC-003`).

## Success metrics

Report mutation-decision accuracy, recall precision/recall, stale-memory rejection, correction success, TTL and deletion completeness, quarantine precision, tenant violations, consent failures, p50/p95 latency, and task success with/without memory. Hard gates are zero cross-tenant recalls, zero authority changes from memory, and complete deletion coverage.

## Prerequisites and dependencies

Use Python 3.12+, `uv`, FastAPI, Pydantic, pytest, OpenTelemetry, Docker Compose, PostgreSQL, migration scaffold, fake clock, and supplied benchmark. Consume the authenticated principal and context-budget contracts from earlier chapters. PostgreSQL full-text search is sufficient; pgvector is optional behind the retrieval port. Redis is not required. Lock versions at implementation kickoff.

## Risks and mitigations

- **Over-remembering:** default to `NOOP`, require purpose and value, and cap retention.
- **False consolidation:** preserve links, require minimum supporting episodes, and allow rollback.
- **Poison persistence:** quarantine untrusted instructions and never elevate recalled content.
- **Deletion gaps:** enumerate all derived views in a transactional deletion plan and verify receipts.
- **Scope creep:** widening scope is a separate approved mutation with explicit subject and expiry.

## Delivery milestones

1. Define schemas, ledger events, lifecycle policy, consent fixtures, and migrations.
2. Implement mutation authorizer, optimistic concurrency, and materialized views.
3. Add governed recall, contradictions, correction, consolidation, fake-clock TTL, and quarantine.
4. Implement inspector, export, deletion planner, and receipts.
5. Add benchmark, privacy/fault drills, telemetry, CI gate, and capstone evidence registration.

## Future extensions

Add a semantic retrieval adapter or alternate durable store behind the same ports, then rerun consent, concurrency, TTL, quarantine, export, deletion, and tenant-isolation tests. Later orchestration may propose memory writes, but this authorizer remains the enforcement point.

## Lab delivery contract

- **Starter:** `ed2-v1.0-ch08-start` with typed records, two tenants, consent fixtures, and supplied benchmark.
- **Task:** one ledger with four views; `ADD`, `UPDATE`, `DELETE`, `NOOP`; concurrency, consent, TTL, correction, quarantine, export, and deletion.
- **Drill:** race conflicting updates, recall poisoned instruction, request deletion, and attempt cross-tenant retrieval.
- **Artifact:** schemas, migrations, lifecycle policy, authorizer, retrieval adapter, user inspector API, benchmark, and deletion evidence.
- **Acceptance:** provenance, explicit conflicts, consent, fake-clock TTL, exclusion of expired/deleted/quarantined/other-tenant records, complete inspection/deletion receipts, and no authority changes.
- **Verify:** `uv run policyops verify ch08 --profile fixture --junit build/ch08/junit.xml --evidence build/ch08`.
- **Handoff:** create `work/ch08`, compare it with `ed2-v1.0-ch08-solution`, and register schema, lifecycle policy, authorizer, context-adapter tests, isolation benchmark, correction, export/deletion evidence, and rollback in `capstone/traceability.yaml`; Chapter 9 adds controlled actions.
- **Execution:** 4–5 hours with PostgreSQL, migrations, fake clock, two-tenant consent fixture, and benchmark; no hosted model.
- **Repository/CI:** `labs/ch08/manifest.toml`, base tag `ed2-v1.0-ch08-start`, and `src/policyops/memory`, `db/migrations`, `tests/memory`, `tests/privacy`; `verify-ch08` runs earlier gates.
- **Run/cleanup:** `uv sync --frozen`; `uv run policyops env up --lab ch08 --profile fixture`; `uv run policyops verify ch08 --profile fixture --junit build/ch08/junit.xml --evidence build/ch08`; `uv run policyops fault ch08 --scenario all`; `uv run policyops env down --lab ch08`.
- **Proposal:** add durable user and task memory with consent, provenance, expiry, correction, deletion, and tenant isolation, then demonstrate multi-session benefit without increased authority.
