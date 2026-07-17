# Chapter 5 PRD: Build a Context Planner

**Chapter:** Context Engineering and Prompt Architecture Patterns
**Related design:** [Architecture](./architecture.md)
**Inputs:** [Chapter 2 evaluation suite](../ch02-evaluation-driven-development-suite/prd.md) and [Chapter 4 inference gateway](../ch04-adaptive-inference-gateway/prd.md)
**Implementation checkpoint:** `ed2-v1.0-ch05-start` to `work/ch05`

## Product context

PolicyOps has stable request/answer contracts, release gates, and an adaptive inference gateway. This project replaces a long monolithic prompt with a deterministic planner for one model call. It assembles immutable policy, project and task instructions, current conversation state, typed evidence and capability fixtures, and user input under explicit authority, provenance, sensitivity, token, compaction, and stable-prefix rules.

The chapter owns current-call context assembly. It does not build retrieval indexes (Chapters 6–7), persistent memory (Chapter 8), protocol-level capability discovery (Chapter 9), or durable execution checkpoints (Chapter 11). Those components will later implement the same typed source ports.

## Problem statement

Large prompts often mix policy with untrusted documents, include irrelevant history, leak secrets, truncate required evidence silently, and change layout in ways that defeat prompt caching. Model behavior then becomes difficult to test or explain. PolicyOps needs a context planner that treats tokens, authority, freshness, provenance, and sensitivity as managed resources and can prove why each item was included, compacted, rejected, or omitted.

## Goals

- Define typed instruction, evidence, conversation-state, memory-source, and capability-source contracts.
- Establish a strict authority/trust order that untrusted text cannot elevate.
- Plan token allocations before rendering and refuse impossible required-content plans.
- Load fixture sources lazily and include only task-relevant content.
- Compact current conversation/tool history while preserving decisions and artifact references.
- Order stable high-authority prefixes before variable content and measure exact-prefix reuse.
- Produce a structured model request plus a machine-readable context manifest.
- Demonstrate token reduction without reducing the Chapter 2 pass rate.

## Non-goals

- Retrieving documents from a production index or deciding graph routes.
- Storing, consolidating, expiring, correcting, or deleting long-term memory.
- Discovering or invoking MCP/tools, Agent Skills, plugins, or hooks.
- Using hidden chain-of-thought as an interface or persisted artifact.
- Owning cache storage, invalidation, model routing, or provider failover.

## Users

- **AI application engineer:** defines context policy and source adapters.
- **Prompt engineer:** creates versioned instruction templates and structured-output contracts.
- **Security engineer:** verifies authority boundaries, secret handling, and untrusted-data treatment.
- **Evaluator:** compares monolithic and planned context through snapshots, traces, token reports, and Chapter 2 gates.

## User stories

- As an AI engineer, I can explain each context item's source, authority, sensitivity, token cost, and inclusion decision.
- As a security engineer, I can inject a document instruction and prove it remains untrusted evidence rather than policy.
- As a caller, I receive an explicit abstention/error when required facts do not fit or are absent, never an answer based on silent truncation.
- As a performance engineer, I can compare token use and stable-prefix reuse without changing the Chapter 4 cache implementation.

## Functional requirements

- **CH05-FR-001:** Define versioned `ContextItem`, `SourceSummary`, `ContextRequest`, `ContextPlan`, `ContextManifest`, `CompactionResult`, and `RenderedContext` schemas.
- **CH05-FR-002:** Classify every item by source type, authority level, trust label, provenance, freshness, sensitivity, required/optional status, and stable/variable placement.
- **CH05-FR-003:** Implement a non-overridable authority order for system policy, project instructions, task instructions, verified evidence, observations/state, user input, and untrusted content.
- **CH05-FR-004:** Expose typed `EvidenceSource`, `MemorySource`, and `CapabilitySource` summary/materialization ports; use fixture implementations only in the core.
- **CH05-FR-005:** Compute token estimates with a frozen tokenizer fixture, allocate per-layer budgets, and reserve output/headroom before loading optional content.
- **CH05-FR-006:** Select and lazily materialize only source items relevant to the declared task; preserve source identifiers and hashes in the manifest.
- **CH05-FR-007:** Compact current-call conversation and oversized tool-result fixtures using deterministic rules that retain decisions, unresolved constraints, artifact pointers, and provenance.
- **CH05-FR-008:** Render a cache-friendly stable prefix followed by variable evidence, state, and user content; emit exact prefix and full-context fingerprints for Chapter 4.
- **CH05-FR-009:** Bind the rendered prompt to the Chapter 1 structured `Answer` schema and handle schema refusal/repair through declared bounded policy.
- **CH05-FR-010:** Detect missing required facts, conflicting high-authority instructions, impossible token plans, secret-bearing content, and unsafe trust transitions; reject, compact, or abstain with typed reasons.
- **CH05-FR-011:** Produce deterministic context snapshots, an inclusion/exclusion manifest, token report, stable-prefix report, and A/B traces against the monolithic baseline.
- **CH05-FR-012:** Execute drills for a secret, conflicting instruction, oversized tool result, missing fact, lost-in-the-middle distractor, and silent-truncation attempt.
- **CH05-FR-013:** Normalize the supplied image/table observation fixture into a typed, provenance-bearing observation before planning; raw multimodal bytes and model- or tool-supplied instructions shall not enter the rendered context as trusted instructions.

## Non-functional requirements

- **CH05-NFR-001:** Fixed inputs, policy, tokenizer, and fake clock must produce byte-stable plan, manifest, context fingerprints, and snapshots.
- **CH05-NFR-002:** Planner execution must remain bounded by item count, materialization calls, and token budget; it may not recursively query sources.
- **CH05-NFR-003:** Source adapters and renderers must be model/provider neutral and tested independently.
- **CH05-NFR-004:** Token estimates and actual rendered counts must stay within a declared tolerance; violations fail verification.
- **CH05-NFR-005:** No required content may be dropped without a typed plan failure recorded in the manifest.
- **CH05-NFR-006:** The 2–3 hour core runs offline without an external service or model credential.

## Security and privacy requirements

- **CH05-SEC-001:** Untrusted evidence, history, and user content cannot create or modify policy, authorization, approval, capability scope, or data classification.
- **CH05-SEC-002:** Detect and reject or redact fixture secrets before rendering; never emit raw secrets in snapshots, logs, traces, or manifests.
- **CH05-SEC-003:** Enforce sensitivity compatibility between each source item, tenant/actor context, model profile, and output destination.
- **CH05-SEC-004:** Preserve provenance and trust labels through selection, compaction, and rendering; summaries cannot increase authority.
- **CH05-SEC-005:** Treat source materialization output as untrusted and validate size, schema, tenant, freshness, and content classification.
- **CH05-SEC-006:** Use allowlisted manifest fields and hashes so diagnostic artifacts do not reconstruct sensitive prompts.

## Fixtures and data

The starter includes a long prompt, typed `EvidenceSource` and `CapabilitySource` fixtures, current-conversation records, oversized and tool-overload fixtures, one synthetic image/table observation with extracted coordinates and provenance, and expected context snapshots. A `MemorySource` fixture demonstrates the port but does not persist or claim authority. Evidence includes verified, stale, unauthorized, conflicting, and missing-fact cases. A frozen tokenizer implementation ensures deterministic counts, while optional adapters can compare another tokenizer/model.

Each item carries an opaque tenant, source version/hash, authority and trust label, sensitivity, timestamp/freshness, token estimate, and required/optional flag. Secret fixtures use obvious synthetic markers and must never appear in generated evidence.

## External behavior and configuration

The planner is called by the answer service before the Chapter 4 gateway:

```python
planned = planner.plan(context_request, run_context)
result = await model_client.generate(planned.model_request, run_context)
```

It returns either `RenderedContext` plus `ContextManifest` or a typed failure such as `REQUIRED_FACT_MISSING`, `CONTEXT_BUDGET_IMPOSSIBLE`, `AUTHORITY_CONFLICT`, `SENSITIVITY_VIOLATION`, or `SOURCE_INVALID`. Configuration in `config/context_policy.yaml` declares layer order, budgets, source-call limits, compaction strategy, stable-prefix rules, and output reserve. It cannot weaken service hard limits.

Verification uses:

```text
uv run policyops verify ch05 --profile fixture --junit build/ch05/junit.xml --evidence build/ch05
```

## Acceptance criteria and traceability

| Criterion | Verification | Requirements |
|---|---|---|
| Every context item is rejected unless source kind, authority, trust, provenance, freshness, sensitivity, required status, and placement metadata are valid. | Context-item schema and invalid-label matrix | CH05-FR-002 |
| Evidence, memory, and capability fixture adapters pass the same summary/materialization contract without gaining authority. | Parametrized source-port contract tests | CH05-FR-004 |
| Only task-relevant selected IDs are materialized, and every source call and content hash appears in the manifest. | Spy-source lazy-loading and manifest assertions | CH05-FR-006 |
| Rendered context binds the Chapter 1 answer schema; refusal and repair stop at the declared attempt limit. | Structured-output, refusal, invalid-repair, and attempt-budget tests | CH05-FR-009 |
| Secret, conflict, oversized result, tool overload, missing fact, distractor, and truncation drills each produce the declared safe outcome. | Parameterized chapter fault runner | CH05-FR-012 |
| The supplied multimodal observation becomes a typed, budgeted, provenance-bearing observation; raw bytes or embedded instructions never become authority. | Normalization schema, coordinate/provenance, and injection tests | CH05-FR-013, CH05-SEC-001, CH05-SEC-004 |
| Fixed inputs produce identical plans, manifests, snapshots, and fingerprints. | Two-run canonical diff | CH05-FR-001, CH05-NFR-001 |
| Required evidence remains or planning fails explicitly. | Budget and truncation property tests | CH05-FR-005, CH05-FR-010, CH05-NFR-005 |
| Untrusted instructions never become policy or authorization. | Trust-order/injection tests | CH05-FR-003, CH05-SEC-001, CH05-SEC-004 |
| Secret fixture is absent from rendered context and all evidence. | Secret drill and artifact scan | CH05-FR-010, CH05-SEC-002, CH05-SEC-006 |
| Oversized results compact with decision and artifact provenance intact. | Snapshot and invariant tests | CH05-FR-007 |
| Stable prefix precedes variable content and yields reproducible fingerprint/reuse evidence. | Ordering and prefix report tests | CH05-FR-008 |
| Planned context reduces tokens without lowering Chapter 2 pass rate. | Locked A/B suite | CH05-FR-011 |
| Alternate tokenizer/model retains authority, provenance, missing-fact, and truncation gates. | Optional adapter contract suite | CH05-NFR-003, CH05-NFR-004 |

## Success metrics

- 100% deterministic snapshot and manifest equality under fixture mode.
- Zero authority elevation, secret exposure, cross-tenant materialization, or silent required-item drops.
- Every included and excluded item has a reason code and source hash.
- Planned context uses fewer input tokens than the supplied monolith while meeting all mandatory Chapter 2 gates.
- Token estimate error remains within the declared fixture tolerance.
- Source calls and total included tokens never exceed policy limits.

## Dependencies and prerequisites

The project depends on Chapter 2 release gates and uses the Chapter 4 selected model/gateway profile and cache fingerprint seam. It requires typed context-source fixtures, a frozen tokenizer, snapshots, Python 3.12+, `uv`, Pydantic, pytest, and OpenTelemetry. It needs no PostgreSQL, Redis, retrieval service, or hosted model. Primary paths are `src/policyops/context`, `config/context_policy.yaml`, `tests/context`, and `fixtures/context`.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| “Authority” is encoded only in prompt prose. | Enforce typed labels and deterministic ordering before rendering. |
| Token estimation differs by model. | Use a tokenizer port, bind fingerprints to tokenizer/model, and test tolerance. |
| Compaction invents or drops decisions. | Use deterministic extraction for core fields and snapshot provenance; avoid free-form model summary in mandatory path. |
| Planner duplicates retrieval or memory logic. | Limit adapters to source contracts and fixture materialization; later chapters own source lifecycle. |
| Stable prefix conflicts with task relevance. | Stabilize only policy/project layers and measure, rather than maximize, prefix reuse. |
| Manifests leak sensitive content. | Record metadata, hashes, counts, and reason codes instead of raw text. |

## Delivery milestones

1. Define item, source, plan, manifest, compaction, and rendered-context contracts.
2. Implement trust order, policy validation, tokenizer port, and budget allocator.
3. Implement lazy fixture sources, deterministic selection, and materialization validation.
4. Add current-call compaction, stable-prefix ordering, structured-output binding, and typed failure paths.
5. Add snapshots, token/prefix reports, A/B runner, and telemetry.
6. Run all fault drills and register manifest, planner, snapshots, token report, authority tests, and rollback configuration in `capstone/traceability.yaml`.

## Lab delivery contract

- **Starter:** `ed2-v1.0-ch05-start` with a long monolithic prompt, typed evidence/capability fixtures, context snapshots, frozen tokenizer fixture, and Chapter 2 gates.
- **Task/drill:** implement authority-ranked layers, provenance/sensitivity labels, budgets, history compaction, stable-prefix ordering, structured output, and just-in-time loading; inject a secret, conflicting instruction, oversized tool result, and missing required fact.
- **Artifacts/acceptance:** context manifest, planner, budget policy, repository map, snapshots, token report, and A/B traces; fixed inputs are deterministic, required evidence remains, untrusted text never becomes policy, and token reduction does not lower the release-suite pass rate.
- **Environment/repository:** Python 3.12+, `uv`, no external service or paid credential; `labs/ch05/manifest.toml`, `src/policyops/context`, `config/context_policy.yaml`, `tests/context`, and `fixtures/context`.
- **Lifecycle:** `uv sync --frozen`; `uv run policyops env up --lab ch05 --profile fixture`; `uv run policyops verify ch05 --profile fixture --junit build/ch05/junit.xml --evidence build/ch05`; `uv run policyops fault ch05 --scenario all`; `uv run policyops env down --lab ch05`.
- **Handoff:** compare `work/ch05` with `ed2-v1.0-ch05-solution` and register manifest, planner, snapshots, authority/source contract tests, token report, configuration hash, test command, and rollback in `capstone/traceability.yaml`.

## Future extensions

Replace one tokenizer or model adapter and rerun the same contracts. Chapters 6, 8, and 9 will implement retrieval, persistent memory, and capability sources. The context planner remains the single owner of how those typed materials are assembled for a current model call; it does not inherit their storage, permissions, or execution responsibilities.
