# Chapter 1 PRD: Build the PolicyOps Foundation

**Chapter:** Modern LLM Design Patterns and Architecture
**Related design:** [Architecture](./architecture.md)
**Implementation checkpoint:** `ed2-v1.0-ch01-start` to `work/ch01`

## Product context

PolicyOps is the running project for the second edition: a multi-tenant service that will eventually answer policy questions with evidence and perform tightly controlled actions. This first project establishes only the deterministic shell and provider-neutral model boundary. It deliberately does not implement evaluation infrastructure, retrieval, memory, tools, orchestration, or deployment operations owned by later chapters.

The starter supplies a fixture pack, repository skeleton, and failing contract tests. The required path must be reproducible without a model download, GPU, hosted API, or paid credential.

## Problem statement

An LLM prototype often leaks provider-specific request and response types throughout the application, accepts malformed outputs, omits identity and tenant context, and has no stable health or trace contract. Such a prototype cannot safely evolve into a production system. Readers need a small but credible service foundation in which probabilistic generation is isolated behind a port and deterministic code owns validation, authorization context, configuration, error behavior, and telemetry fields.

## Goals

- Define stable `ModelClient`, `RunContext`, request, answer, citation, usage, and error contracts.
- Serve a basic policy answer endpoint plus liveness and readiness endpoints.
- Provide a deterministic replay adapter as the mandatory implementation profile.
- Permit an optional local-model adapter through the same interface without changing application code.
- Fail closed on invalid identity, tenant, configuration, adapter timeout, and malformed model output.
- Emit a baseline trace and scorecard suitable for Chapter 2 evaluation work.
- Package a non-root container and local run workflow that starts from a clean clone.

## Non-goals

- Measuring answer quality or introducing release gates; Chapter 2 owns these.
- Selecting or fine-tuning a production model; Chapter 3 owns adaptation decisions.
- Routing across models, caching responses, or optimizing inference; Chapter 4 owns these.
- Retrieval, persistent memory, tool execution, approval flows, agents, or production failover.
- Claiming that the fixture adapter represents real model quality or performance.

## Users

- **Reader-engineer:** implements the contracts and adapters and runs the verification workflow.
- **Application developer:** calls the HTTP API without knowing which model provider is configured.
- **Platform operator:** checks health, readiness, configuration identity, and baseline telemetry.
- **Test author:** injects deterministic responses and failures through the replay adapter.

## User stories

- As an application developer, I can submit a tenant- and actor-scoped question and receive a schema-valid answer or a typed error.
- As a test author, I can replay success, malformed output, and timeout cases without network access.
- As an operator, I can distinguish a live process from a ready service and identify the active configuration without exposing secrets.
- As an adapter author, I can add a model implementation without importing provider types into the API or domain layers.

## Functional requirements

- **CH01-FR-001:** Define versioned `RunContext` carrying `request_id`, `trace_id`, `tenant_id`, `actor_id`, roles, purpose, `configuration_id` plus component configuration versions, deadline, budget, data classification, typed authorization context, approval reference, and optional idempotency key.
- **CH01-FR-002:** Define provider-neutral `ModelRequest`, `Answer`, `Citation`, `Usage`, and typed failure contracts; unknown fields must not silently change application behavior.
- **CH01-FR-003:** Define an asynchronous `ModelClient.generate()` port that accepts only domain contracts and supports cancellation or deadline propagation.
- **CH01-FR-004:** Implement a deterministic replay adapter keyed by fixture scenario and configuration hash, including success, invalid-JSON, schema-invalid, timeout, and upstream-error responses.
- **CH01-FR-005:** Expose `POST /v1/answer`; reject missing or invalid actor, tenant, request identifiers, unsupported content type, and malformed body before invoking the adapter.
- **CH01-FR-006:** Expose `/health/live` for process health and `/health/ready` for validated configuration and adapter availability.
- **CH01-FR-007:** Validate configuration at startup, select adapters through dependency injection, and report a non-secret configuration fingerprint.
- **CH01-FR-008:** Parse and validate adapter output before returning it; invalid output must produce a typed, retry-classified error and no partial answer.
- **CH01-FR-009:** Emit correlated baseline spans and structured events for request receipt, model invocation, validation, and response, preserving actor, tenant, trace, and configuration identifiers.
- **CH01-FR-010:** Provide CLI commands for fixture startup, verification, fault execution, evidence output, and cleanup using the chapter manifest.

## Non-functional requirements

- **CH01-NFR-001:** A clean clone must install with `uv sync --frozen` and run the fixture profile on Python 3.12+ without a paid credential.
- **CH01-NFR-002:** Fixed fixture inputs must produce byte-stable canonical JSON apart from explicitly excluded timestamps.
- **CH01-NFR-003:** The API must publish an OpenAPI document and pass compatibility checks against the checked-in contract snapshot.
- **CH01-NFR-004:** The fixture profile must complete the contract suite within the chapter's 2–3 hour implementation scope and ordinary laptop resources.
- **CH01-NFR-005:** Provider substitution must require only adapter and composition changes; provider packages and types must not cross the adapter boundary.
- **CH01-NFR-006:** The container must run as a non-root user, expose only the API port, and handle termination without abandoning in-flight request logs.

## Security and privacy requirements

- **CH01-SEC-001:** Reject absent tenant or actor identity and any request whose authenticated tenant conflicts with body or header context.
- **CH01-SEC-002:** Never commit credentials; supply `.env.example` with names and safe defaults only.
- **CH01-SEC-003:** Redact prompts, outputs, authorization claims, and error details according to data classification; telemetry may contain opaque identifiers but not secrets.
- **CH01-SEC-004:** Do not return provider errors, stack traces, or configuration secrets to clients.
- **CH01-SEC-005:** Treat model output as untrusted data and perform schema plus semantic validation before use.
- **CH01-SEC-006:** Use a non-root runtime image and fail startup when mandatory secure configuration is absent or contradictory.

## Fixtures and data

The fixture pack must include two tenants, at least two actors with different claims, a small versioned policy excerpt, canonical requests and answers, and replay scenarios for valid output, malformed JSON, missing required fields, timeout, and upstream failure. Each fixture has a content hash and license/source note. No fixture contains a live credential or personal data. A fake clock and fixed identifiers make deterministic evidence possible.

## External behavior

`POST /v1/answer` accepts a JSON question and authenticated context. On success it returns a typed answer, zero or more citations, usage metadata, `trace_id`, and `configuration_id`. Validation failures use `400`; authentication or tenant conflicts use `401`/`403`; adapter timeout or unavailable state uses a typed `503`; invalid adapter output uses a typed `502`. Liveness does not call a model. Readiness validates the selected adapter and configuration without generating billable traffic.

The implementation workflow is:

```text
uv sync --frozen
uv run policyops env up --lab ch01 --profile fixture
uv run policyops verify ch01 --profile fixture --junit build/ch01/junit.xml --evidence build/ch01
uv run policyops fault ch01 --scenario all
uv run policyops env down --lab ch01
```

## Acceptance criteria and traceability

| Criterion | Verification | Requirements |
|---|---|---|
| Request, context, answer, citation, usage, and error contracts preserve every required field and reject invalid versions or missing fields. | Schema round-trip, version, and required-field tests | CH01-FR-001, CH01-FR-002 |
| Invalid startup configuration is rejected and valid configuration exposes only a stable non-secret fingerprint. | Configuration matrix, readiness, and redaction assertions | CH01-FR-007 |
| A clean checkout starts with no paid credential or model download. | Fresh-environment fixture smoke test | CH01-FR-004, CH01-FR-010, CH01-NFR-001 |
| Replay and every enabled optional adapter pass one contract suite. | Parametrized adapter contract tests | CH01-FR-003, CH01-FR-004, CH01-NFR-005 |
| Malformed output and adapter timeout fail closed with typed errors. | Fault scenarios plus API assertions | CH01-FR-008, CH01-SEC-005 |
| Missing identity and cross-tenant requests never invoke the model. | Spy-adapter authorization tests | CH01-FR-005, CH01-SEC-001 |
| No provider type or secret crosses its boundary. | Import-boundary and secret scans | CH01-NFR-005, CH01-SEC-002, CH01-SEC-003 |
| Health, OpenAPI, non-root container, and trace fields pass. | Container smoke, schema snapshot, trace assertions | CH01-FR-006, CH01-FR-009, CH01-NFR-003, CH01-NFR-006 |

The verifier emits JSON, JUnit, trace, dependency, fixture, configuration, and hardware evidence and exits non-zero on any mandatory gate.

## Success metrics

- 100% pass rate for mandatory deterministic contract and fault tests.
- Zero adapter calls for rejected identity or cross-tenant scenarios.
- Zero secrets detected in source, images, logs, traces, or evidence.
- Identical domain test results across replay and each enabled optional adapter.
- A baseline scorecard records test runtime, request latency distribution, error classification, and environment fingerprint without presenting fixture latency as provider performance.

## Dependencies and prerequisites

Python 3.12+, `uv`, and Git are required. Docker is required only for container and telemetry smoke tests. Shared implementation assumptions are FastAPI, Pydantic, pytest, OpenTelemetry, and Docker Compose, with exact dependency pins locked when implementation begins. This chapter has no dependency on later PolicyOps components.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Provider details leak through convenient SDK objects. | Enforce import boundaries and contract tests at the adapter port. |
| Replay tests overstate real model behavior. | Label replay evidence, keep quality claims out of Chapter 1, and add Chapter 2 suites next. |
| Telemetry captures prompts or credentials. | Default-deny attributes, redaction tests, and safe fixture values. |
| Readiness creates cost or instability. | Use configuration and lightweight adapter checks; never generate billable content. |
| Initial schema becomes too broad. | Include only cross-cutting envelope fields and version contracts explicitly. |

## Delivery milestones

1. Define domain schemas, typed failures, and boundary tests.
2. Implement replay adapter, composition root, and validated configuration.
3. Implement answer and health endpoints with error mapping.
4. Add spans, container policy, OpenAPI snapshot, and evidence emitter.
5. Run verification and fault drills; record the architecture ADR and baseline scorecard.
6. Compare `work/ch01` with `ed2-v1.0-ch01-solution`, register contracts, configuration hashes, rollback path, tests, and scorecard in `capstone/traceability.yaml`, then create the accepted `work/ch01` checkpoint.

## Future extensions

Enable a pinned local-model adapter and repeat the same contract and load suite. Later chapters add evaluation gates, adaptation decisions, routing, context, retrieval, memory, capabilities, orchestration, production telemetry, security, deployment, and governance without weakening this foundational boundary.
