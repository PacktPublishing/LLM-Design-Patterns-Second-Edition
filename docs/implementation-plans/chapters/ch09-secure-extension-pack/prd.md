# Chapter 9 PRD: Build a Secure PolicyOps Extension Pack

This project implements the hands-on work for Chapter 9, **Capability Extension Patterns: Tools, MCP, Agent Skills, Plugins, and Hooks**. It turns the governed context and memory from [Chapter 8](../ch08-governed-long-term-memory/prd.md) into tightly bounded ticket operations and supplies secured capabilities to [Chapter 10 orchestration](../ch10-bounded-orchestrator-worker/prd.md). See the [architecture](./architecture.md).

## Problem

Teams often package every new behavior as an “agent,” blurring the difference between an atomic operation, interoperable protocol, reusable workflow guidance, distributable bundle, deterministic lifecycle control, and computer-use adapter. That ambiguity creates excessive authority, invisible execution, brittle activation, supply-chain exposure, stale approvals, and revocation gaps. PolicyOps needs a small extension pack that demonstrates when to use a typed tool, MCP server, Agent Skill, plugin, hook, or computer-use adapter boundary—and secures their composition from install through emergency disablement.

## Goals

- Start with one directly testable ticket tool and expose it through MCP only for interoperable discovery and invocation.
- Add a focused Agent Skill that teaches a safe, repeatable ticket workflow with progressive disclosure and precise activation.
- Package the tool adapter, MCP configuration, skill, hooks, and assets as a signed, versioned plugin for one reference host.
- Add bounded pre-action and post-action hooks for deterministic approval enforcement and redacted audit evidence.
- Bind identity, consent, approval, scope, action hash, expiry, and idempotency to each mutation.
- Verify provenance, compatibility, tamper resistance, update/rollback, disablement, and revocation without paid credentials.

## When to use each extension surface

| Surface | Use when | PolicyOps example | Do not use when |
|---|---|---|---|
| Typed tool/API/CLI | One explicit operation needs a small validated input/output contract | Create or read one policy ticket | The task is only guidance or needs host interoperability |
| MCP server | Multiple compatible hosts need discoverable tools/resources/prompts across a standard boundary | Expose ticket creation and schema resource to local hosts | One in-process caller is sufficient, or the server would broaden authority |
| Agent Skill | Repeatable workflow knowledge, examples, scripts, and references should load progressively | Teach when and how to draft, preview, approve, and create a ticket | Deterministic enforcement or a privileged mutation is required |
| Plugin | A versioned bundle of related skill, MCP config, hooks, agents, and assets must be installed/distributed together | Distribute the PolicyOps ticket extension to one reference host | A personal/project-local experiment needs only standalone files |
| Lifecycle hook | A bounded deterministic check or side effect must run at a named event | Block stale approval before action; write redacted evidence after action | Open-ended judgment, hidden agent loops, or long-running orchestration is needed |
| Computer-use adapter | A host exposes screen, DOM, or browser observations as a capability surface | Document the secured capability boundary; Chapter 10 builds the mock approval-form fixture | A stable API or typed tool is available, or the adapter would bypass approval and audit controls |

## Non-goals

- A marketplace, universal cross-host plugin format, or production identity provider.
- Autonomous ticket prioritization, Chapter 10 multi-agent orchestration, or Chapter 11 crash-safe workflow execution.
- Using hooks for model judgment, retries without limits, or alternate hidden action paths.
- Giving a skill, plugin manifest, MCP metadata, or tool result implicit trust.
- Letting a computer-use adapter bypass the typed tool, approval, sandbox, egress, or audit boundary.
- Supporting more than one reference host in the required implementation.

## Users

- **AI engineer:** implements typed capabilities and host-neutral adapters.
- **Workflow author:** writes focused skills and deterministic hooks.
- **Platform/security engineer:** reviews permissions, signatures, sandboxing, and revocation.
- **Operator:** installs, updates, disables, rolls back, and audits the extension pack.

## User stories

- As an AI engineer, I can call the ticket tool directly in tests and through MCP with the same schema and behavior.
- As a workflow author, I can activate the ticket skill for intended tasks without granting any capability by activation alone.
- As an operator, I can verify a signed plugin, stage an update, roll back, or revoke it and see why loading succeeded or failed.
- As a security engineer, I can prove a stale approval, tampered package, injected metadata, duplicate delivery, or hook timeout cannot silently authorize a ticket.

## Functional requirements

- **CH09-FR-001 — Typed tool:** Implement `create_policy_ticket` and read-only `preview_policy_ticket` against the supplied local ticket adapter with strict input/output schemas, typed errors, timeouts, impact classes, and one idempotency key per mutation.
- **CH09-FR-002 — Effect preview and approval:** Canonicalize the proposed ticket effect, hash it, preview it to the caller, and require a signed approval bound to principal, tenant, exact effect hash, allowed operation, audience, expiry, and nonce before creation.
- **CH09-FR-003 — MCP adapter:** Expose the same `ToolPort` through a local MCP server using pinned stable protocol/SDK fixtures, supporting stdio and local HTTPS clients without changing business semantics.
- **CH09-FR-004 — Agent Skill:** Provide concise activation metadata and progressively disclosed instructions, examples, references, and scripts for safe ticket drafting, preview, approval, creation, verification, and recovery. Sensitive mutation guidance requires explicit invocation.
- **CH09-FR-005 — Plugin package:** Bundle one-host configuration, skill, MCP connection, hooks, schemas, and assets in a versioned manifest declaring hashes, provenance, compatibility, permissions, entry points, and rollback metadata.
- **CH09-FR-006 — Pre-action hook:** Before every mutation path, validate principal, tenant, action hash, approval audience/scope/expiry/nonce, extension status, and idempotency key within a strict timeout. Failure or timeout denies the mutation.
- **CH09-FR-007 — Post-action hook:** After success or typed failure, append a redacted, correlation-linked audit record. Its failure cannot convert a denied action to allowed or duplicate a completed mutation; the operation reports degraded evidence delivery.
- **CH09-FR-008 — Loader and provenance:** Verify package hashes and signature against a local trust store, check compatibility and requested permissions, stage updates, and refuse tampered, unknown, incompatible, disabled, or revoked versions.
- **CH09-FR-009 — Lifecycle controls:** Support list, enable, disable, stage, activate, rollback, and revoke; revocation prevents new loads and calls while preserving minimal audit evidence.
- **CH09-FR-010 — Alternate-path coverage:** Direct tool, MCP, skill-driven host flow, and plugin entry point must converge on the same authorization and hook-enforcement boundary.
- **CH09-FR-011 — Compatibility notes:** Record which concepts map cleanly to a second compatible host and where activation, packaging, hooks, or permissions differ, without implementing that host.

- **CH09-FR-012 — Versioned MCP profiles and explicit state:** Ship the required lab against the stable `2025-11-25` profile, record the announced breaking `2026-07-28` release-candidate profile as an opt-in compatibility target, and version-gate transport/session behavior, Tasks/Apps extensions, sampling/logging, schemas, and authorization. Persist workflow, approval, idempotency, subscription, and resumable-result state explicitly even when the selected transport is stateless or sessionless.

## Non-functional requirements

- **CH09-NFR-001:** The fixture profile runs locally with a ticket stub, development-only token issuer, ephemeral signing keys, test CA, and no paid model/API credential.
- **CH09-NFR-002:** Tool and MCP contract tests are deterministic; duplicate delivery with one idempotency key creates exactly one ticket.
- **CH09-NFR-003:** Pre-action hook p95 overhead is at most 100 ms locally and has a hard 500 ms timeout; post-action work is bounded and never blocks beyond its configured timeout.
- **CH09-NFR-004:** All plugin contents are reproducibly packaged, hash-addressed, and verifiable before execution.
- **CH09-NFR-005:** Compatibility, protocol, schema, and manifest versions are pinned at implementation kickoff and reported in evidence.

## Security and privacy requirements

- **CH09-SEC-001:** Use least-privilege, audience-bound, short-lived tokens; keep credentials outside model-visible context, skill files, manifests, logs, and tool results.
- **CH09-SEC-002:** Treat skill text, plugin/MCP metadata, tool descriptions, resource content, and tool results as untrusted input; they cannot override policy or approval checks.
- **CH09-SEC-003:** Execute extension processes as non-root with restricted filesystem, environment, subprocess access, and egress. HTTPS validates the test CA; stdio uses a controlled executable path.
- **CH09-SEC-004:** Approval verifies exact effect hash, principal, tenant, operation, audience, scope, expiry, and nonce at the final mutation boundary; preview changes invalidate approval.
- **CH09-SEC-005:** Verify signatures and content hashes before loading, maintain provenance and revocation state, and fail closed on missing trust or verification errors.
- **CH09-SEC-006:** Hook failure cannot authorize a mutation. Every alternate action path invokes the same pre-action policy and ticket repository.
- **CH09-SEC-007:** Audit evidence is append-only and redacted; ticket descriptions and tokens do not enter telemetry by default.

## Fixtures and data

Fixtures include a local ticket service, `ToolPort`, stdio and HTTPS clients, development-only token issuer, test CA, ephemeral package keys, approved/denied/stale approval tokens, valid and tampered packages, incompatible update, revocation list, malicious metadata, duplicate requests, and hook-timeout scenarios. A versioned activation corpus contains 40 intended tasks and 40 negative/near-neighbor tasks, including explicit-invocation, ambiguous, adversarial-metadata, and unrelated-tool cases. The sample policy ticket contains non-sensitive synthetic data. A replay `ModelClient` exercises activation without network access; optional hosted or local profiles do not change enforcement.

## External behavior

- Tool: `preview_policy_ticket(input, context: RunContext) -> EffectPreview`; `create_policy_ticket(preview, approval, idempotency_key, context: RunContext) -> TicketResult`.
- MCP: exposes the same tools plus read-only schema/help resources; protocol errors map to stable domain error codes.
- Loader CLI: `policyops extensions verify|install|stage|activate|disable|rollback|revoke <package>`.
- Lifecycle API: `GET /v1/extensions`, `POST /v1/extensions/{id}:disable`, `:activate`, `:rollback`, and `:revoke` for the local reference host.
- Verification: `uv run policyops verify ch09 --profile fixture --junit build/ch09/junit.xml --evidence build/ch09`.

## Acceptance criteria and traceability

1. Given the frozen 80-case activation corpus, the skill reaches precision at least 0.95 and recall at least 0.90, never auto-activates a sensitive mutation path without explicit invocation, and produces a valid preview for intended tasks (`CH09-FR-004`).
2. Given missing, stale, mismatched, or out-of-scope approval, all direct, MCP, and host mutation paths fail before the ticket repository (`CH09-FR-002`, `CH09-FR-006`, `CH09-FR-010`).
3. Given one approved effect and repeated delivery with the same idempotency key, exactly one ticket exists and every response references it (`CH09-FR-001`, `CH09-NFR-002`).
4. Given prompt injection in metadata or a tool result, policy, effect, and approval fields remain unchanged and no secret appears in model context (`CH09-SEC-001`, `CH09-SEC-002`).
5. Given a tampered, incompatible, disabled, or revoked package, the loader refuses it before entry-point execution (`CH09-FR-008`, `CH09-FR-009`, `CH09-SEC-005`).
6. Given hook timeout or failure, the pre-action path denies; post-action failure is visible and cannot duplicate or authorize an action (`CH09-FR-006`, `CH09-FR-007`, `CH09-SEC-006`).
7. Given a staged invalid update, the active version remains healthy; rollback restores the previous verified version (`CH09-FR-008`, `CH09-FR-009`).
8. Given direct, stdio-MCP, and HTTPS-MCP fixture clients, all transports pass the same tool contract; the signed one-host plugin installs the declared skill, hooks, schemas, and permissions; and the compatibility report names the concrete activation, packaging, hook, and permission gaps for a second host (`CH09-FR-003`, `CH09-FR-005`, `CH09-FR-011`).
9. Given the Chapter 5 planner, `CapabilityContextSource` passes the shared two-phase source contract and exposes only allowlisted schema/help metadata; it never reveals a secret, approval, grant, or mutation result and cannot invoke the tool (`CH09-FR-001`, `CH09-FR-010`, `CH09-SEC-002`).

10. Given stable and release-candidate compatibility fixtures, the required stable profile passes, the release candidate runs only when explicitly selected, unsupported negotiated features fail closed, and application state survives transport/session replacement (`CH09-FR-003`, `CH09-FR-012`).

## Success metrics

Report tool/MCP contract pass rate, skill activation precision/recall and corpus hash, unauthorized mutation count, idempotency violations, approval reason distribution, package verification failures, revocation propagation, hook p50/p95/timeout rates, redaction failures, update/rollback success, and trace completeness. Hard gates are activation precision at least 0.95, recall at least 0.90, zero unauthorized tickets, zero secret exposure, one effect per idempotency key, and no load of tampered or revoked code.

## Prerequisites and dependencies

Use Python 3.12+, `uv`, FastAPI, Pydantic, pytest, OpenTelemetry, Docker Compose, MCP stable `2025-11-25` fixtures plus a profile-gated `2026-07-28` release-candidate compatibility fixture, ticket stub, test CA, ephemeral signing keys, local HTTPS endpoint, and development issuer. Consume the canonical Chapter 1 `RunContext` and Chapter 8 memory/context adapter, but never derive authority from memory. No PostgreSQL or Redis is required for the core ticket stub; the audit/idempotency adapter may use SQLite. Lock all versions at kickoff.

## Risks and mitigations

- **Wrong abstraction:** require the decision table and keep the atomic tool independently testable.
- **Approval confused with conversation consent:** bind a signed approval to the exact canonical effect at the final boundary.
- **Supply-chain compromise:** verify signature/hash/provenance before execution and support immediate revocation.
- **Hooks become hidden workflows:** make them time-limited, idempotent, deterministic, and event-specific.
- **Alternate-path bypass:** route every invocation through one policy-enforced `ToolPort` decorator.
- **Skill over-activation:** use narrow metadata, negative examples, and an activation benchmark.

## Delivery milestones

1. Implement typed tool, preview/effect canonicalization, idempotent repository, and contract tests.
2. Add approval verifier, common policy decorator, stdio/HTTPS MCP server, and clients.
3. Author skill, activation benchmark, bounded hooks, and redacted evidence sink.
4. Build manifest, reproducible packager, signature/trust verification, host adapter, and lifecycle controls.
5. Run tamper/timeout/alternate-path/update/revocation drills, produce compatibility notes, gate CI, and register evidence.

## Future extensions

Map the same skill and hook intent to a second compatible host and document concrete portability gaps. Additional tools may join the pack only with their own impact class, effect schema, approval policy, sandbox profile, and revocation tests.

## Lab delivery contract

- **Starter:** `ed2-v1.0-ch09-start` with local ticket service, `ToolPort`, stdio/HTTPS clients, development-only issuer, working deterministic packager/loader, test trust store and registry adapters, reference-host adapter, bounded hook runner, frozen activation corpus, and failing policy/lifecycle tests. Readers implement the tool/MCP/skill/plugin policies and security seams rather than commodity archive, host, and hook plumbing.
- **Task:** implement one typed tool and local MCP server; add a focused Agent Skill; package for one reference host; add bounded pre/post hooks.
- **Drill:** missing/stale approval, injected metadata, tampered package, invalid update, duplicate delivery, hook timeout, alternate paths, disablement, rollback, and revocation.
- **Artifact:** typed contracts, local MCP server, Agent Skill, one-host plugin, pre-action policy hook, post-action audit hook, compatibility notes, threat model, and tests.
- **Acceptance:** correct activation, denied unapproved writes, one ticket per approved idempotency key, no secret leakage, no tampered/revoked load, and fail-closed hook behavior.
- **Verify:** `uv run policyops verify ch09 --profile fixture --junit build/ch09/junit.xml --evidence build/ch09`.
- **Handoff:** register typed contracts, MCP/skill/plugin packages, hooks, computer-use adapter boundary, registry/revocation/approval bindings, compatibility notes, threat model, contract tests, rollback, and revocation evidence in `capstone/traceability.yaml`; Chapter 10 then uses the secured extension surfaces while comparing deterministic, single-agent, browser/computer-use, and multi-agent topologies.
- **Execution:** 4–6 hours with pinned MCP fixtures, ticket stub, test CA, ephemeral keys, local HTTPS, and development issuer; no paid credential.
- **Repository/CI:** `labs/ch09/manifest.toml`, base tag `ed2-v1.0-ch09-start`, and `services/mcp_server`, `services/test_issuer`, `src/policyops/tools`, `tests/mcp`, `tests/contract`; `verify-ch09` runs all prior gates.
- **Run/cleanup:** `uv sync --frozen`; `uv run policyops env up --lab ch09 --profile fixture`; `uv run policyops verify ch09 --profile fixture --junit build/ch09/junit.xml --evidence build/ch09`; `uv run policyops fault ch09 --scenario all`; `uv run policyops env down --lab ch09` (which must remove ephemeral keys and tokens).
- **Proposal:** build one local MCP server, safe ticket Agent Skill, one-host plugin, fail-closed pre-action approval hook, and redacted post-action evidence hook; test advisory, approved, denied, tampered, and revoked cases.
