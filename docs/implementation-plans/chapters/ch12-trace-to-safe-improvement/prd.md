# Chapter 12 Project PRD: Turn a Production Trace into a Safe Improvement

This project implements the hands-on work for Chapter 12, **LLMOps, Observability, and Continuous Improvement**. It consumes the durable events and recovery evidence from [Chapter 11](../ch11-resumable-agent-loop/prd.md), then builds the boundary from observed production behavior to a human-reviewed configuration candidate. The [architecture](./architecture.md) specifies the telemetry, evaluation, experiment, and behavior-canary components.

## Product proposal

Instrument the main model, retrieval, memory, agent, browser/computer-use, approval, and tool operations; diagnose one failed trace; convert the adjudicated failure into an evaluation case; track cost per successful outcome; and test one prompt or routing improvement through a simulated behavior canary that automatically rolls back on regression.

## Problem

Raw traces do not create safe improvement. They may contain private data, misleading workflow noise, high-cardinality fields, or one-off practitioner preferences. A team can overfit a prompt to the visible failure, change the grader to make the candidate pass, replay a trace that repeats an effect, or deploy a configuration without a stop condition. PolicyOps needs a closed but bounded pipeline that correlates behavior, protects telemetry, requires domain adjudication, freezes its evidence, measures targeted and regression effects, and keeps human release authority.

## Goals

- Correlate model, context, retrieval, memory, orchestration, approval, tool, and outcome spans under one trace identity.
- Maintain a system artifact registry for every behavior-affecting version and configuration.
- Enforce privacy-aware field collection, redaction, tenant separation, sampling, and cardinality limits.
- Turn one expert-adjudicated production failure into a versioned evaluation case.
- Run a bounded keep-or-revert experiment over one writable prompt or routing surface.
- Compare candidates against a read-only hashed holdout and predeclared quality, safety, latency, and cost gates.
- Track cost per successful outcome so a cheaper but lower-quality candidate and a more expensive but more reliable candidate can be compared honestly.
- Behavior-canary the winning candidate and automatically revert a seeded bad release.

## Non-goals

- Replaying the Chapter 11 execution state or invoking real side effects during diagnosis.
- Automatically rewriting code, graders, holdouts, policies, or security gates.
- Deploying container, schema, or infrastructure canaries; Chapter 14 owns those rollouts.
- Replacing Chapter 2's evaluation schemas or offline release suite.
- Conducting the adversarial security campaign from Chapter 13.
- Making an autonomous production-release decision; Chapter 15 governs that decision.

## Users

- **AI engineer:** instruments components and compares behavior candidates.
- **Domain expert:** adjudicates whether a trace is a product failure and labels expected behavior.
- **ML/LLMOps engineer:** owns artifact lineage, experiments, canaries, and rollback evidence.
- **Privacy engineer:** defines collection, redaction, retention, sampling, and access policy.
- **Operator:** sees SLO breaches and can stop or revert a canary.

## User stories

- As a domain expert, I can review a redacted trace and classify it as a real product failure, preference, unsupported request, or infrastructure noise.
- As an AI engineer, I can reproduce the failure without executing tools and add a case whose source trace and adjudication are explicit.
- As an operator, I can follow one correlation ID from request through final outcome and identify all artifact versions.
- As a privacy engineer, I can prove supplied PII and secrets do not reach the default trace backend.
- As a release reviewer, I can see why a candidate was kept or reverted and confirm the holdout remained unchanged.

## Functional requirements

- **CH12-FR-001:** A versioned artifact registry shall identify data, prompts, context policies, model adapters, indexes, memory policies, tools, skills, protocols, graders, security policies, and deployment profiles used by each run.
- **CH12-FR-002:** One correlation ID shall link request, model, retrieval, reranking, memory, agent, handoff, browser/computer-use observation/action, approval, tool, sandbox, external-effect, and outcome spans where present.
- **CH12-FR-003:** A semantic adapter shall map provider- or framework-specific events to a stable internal schema and an OpenTelemetry-style export schema.
- **CH12-FR-004:** Collection policy shall apply field allowlists, redaction or hashing, tenant isolation, head or tail sampling rules, and attribute-cardinality limits before export.
- **CH12-FR-005:** SLO definitions shall cover outcome quality, p95 latency, error rate, cost budget, cost per successful outcome, recovery, and high-impact action success with explicit windows and owners.
- **CH12-FR-006:** A trace-adjudication record shall classify the failure, name the expert role, capture evidence, and state whether it may graduate into an evaluation.
- **CH12-FR-007:** Trace reconstruction shall be non-executing and shall reject any attempt to call a model, tool, sandbox, or external effect.
- **CH12-FR-008:** The graduation pipeline shall create a versioned evaluation case linked to the redacted trace, expected outcome, adjudication, provenance, and protected split.
- **CH12-FR-009:** Each experiment shall declare a fixed metric set, time or trial budget, one writable configuration surface, baseline hash, candidate hash, and keep-or-revert result.
- **CH12-FR-010:** Graders, target cases, holdouts, safety gates, and artifact evidence shall be mounted read-only to the candidate process and verified by hash before and after a trial.
- **CH12-FR-011:** A behavior canary shall compare baseline and candidate traffic under predeclared stop conditions and automatically restore the last accepted configuration on regression.
- **CH12-FR-012:** The project shall record a harness-retirement decision after comparing whether one existing scaffold still improves measured outcomes under the selected model profile.

## Non-functional requirements

- **CH12-NFR-001:** The required fixture profile shall use deterministic model, grader, and trace replays and require no paid credentials.
- **CH12-NFR-002:** Export shall remain bounded under load and shall not block the PolicyOps request path when a telemetry backend is unavailable.
- **CH12-NFR-003:** Mandatory CI assertions shall use a deterministic exporter rather than timing-sensitive dashboards.
- **CH12-NFR-004:** Telemetry schemas and artifact records shall be versioned and backwards-readable for the supplied fixture set.
- **CH12-NFR-005:** The verifier shall emit JSON, JUnit, trace, dependency, fixture, configuration, and hardware evidence and exit non-zero on failure.
- **CH12-NFR-006:** The same semantic contracts shall support an optional hosted or alternate local backend without changing acceptance gates.

## Security and privacy requirements

- **CH12-SEC-001:** Raw prompt, retrieved content, memory value, token, secret, and approval payload fields shall be denied by default from telemetry export.
- **CH12-SEC-002:** Tenant identifiers shall be pseudonymized for shared dashboards, and backend queries shall enforce tenant and role access.
- **CH12-SEC-003:** Sampling decisions shall never drop required security, high-impact action, or rollback evidence.
- **CH12-SEC-004:** Evaluation graduation shall retain only the minimum reviewed content and a reference to controlled source evidence.
- **CH12-SEC-005:** Candidate execution shall have no write access to holdouts, graders, evidence records, or accepted configuration aliases.
- **CH12-SEC-006:** Non-executing reconstruction and canary analysis shall not repeat a tool call or external effect.

## Starter, fixtures, and data

Start from `ed2-v1.0-ch12-start`. The starter includes a pinned OpenTelemetry Collector configuration, deterministic CI exporter, local dashboards, redaction rules, sampled traces, a read-only hashed holdout, one adjudicated-failure candidate, and a seeded bad configuration. It consumes the Chapter 11 session/event contract and earlier evaluation schemas.

Primary paths are `src/policyops/telemetry`, `observability`, `tests/telemetry`, `evals`, and `build/ch12`. `labs/ch12/manifest.toml` declares fixture hashes, local services, network, credentials, cleanup, evidence, gates, and fault scenarios.

## External behavior and interfaces

The service will expose no public raw-trace endpoint. Authorized local APIs will support `GET /operations/{correlation_id}`, `POST /adjudications`, `POST /experiments`, and `POST /canaries/{id}/stop`. The CLI will provide `policyops trace inspect`, `policyops eval graduate`, `policyops experiment run`, and `policyops canary simulate`. Every command emits a typed record and an evidence path. The accepted-configuration alias changes only through the canary controller after gate evaluation.

## Required drill

Inject PII and a secret-like token into input, emit a high-cardinality untrusted attribute, submit a candidate that improves the target case but overfits the holdout, simulate a telemetry-backend outage, and reconstruct a side-effecting trace. The expected result is redacted export, capped or dropped cardinality, rejected overfit candidate, non-blocking request behavior, and zero repeated effects.

## Required artifacts

Deliver the semantic-field adapter, Collector configuration, artifact registry, local dashboards, SLO records, redaction and sampling policies, expert adjudication, graduated evaluation case, experiment ledger, candidate comparison, behavior-canary rollback evidence, and non-executing incident reconstruction.

## Acceptance criteria and traceability

- **AC-01 (CH12-FR-001, CH12-FR-002, CH12-FR-003):** Given one fixture request, when it completes, then one correlation ID resolves every relevant span and records all behavior-affecting artifact versions.
- **AC-02 (CH12-FR-004, CH12-SEC-001, CH12-SEC-002, CH12-SEC-003):** Given supplied PII, secrets, and high-cardinality values, when telemetry exports, then sensitive content is absent, cardinality stays within policy, and required security evidence remains.
- **AC-03 (CH12-FR-006, CH12-FR-007, CH12-FR-008):** Given the reviewed failure, when an expert approves graduation, then a provenance-linked evaluation case is created; non-product noise cannot graduate.
- **AC-04 (CH12-FR-009, CH12-FR-010, CH12-SEC-005):** Given an overfit candidate, when targeted and holdout suites run, then the candidate is reverted and hashes prove protected assets did not change.
- **AC-05 (CH12-FR-011):** Given the seeded regression, when the simulated behavior canary crosses its stop condition, then accepted configuration automatically returns to the baseline.
- **AC-06 (CH12-FR-007, CH12-SEC-006):** Given a trace that originally created a ticket, when reconstructed, then no model, tool, or effect adapter is called.
- **AC-07 (CH12-NFR-001, CH12-NFR-002, CH12-NFR-003, CH12-NFR-004, CH12-NFR-005):** Given a clean checkout, when `verify-ch12` runs, then the deterministic profile passes without paid credentials and emits the declared evidence.
- **AC-08 (CH12-FR-005, CH12-FR-012):** Given the accepted artifact profile, then each quality, latency, error, cost, cost-per-successful-outcome, recovery, and high-impact-action SLO has a window and owner, and the scaffold-retirement ADR records measured benefit or removes the scaffold with a rollback path.

## Success metrics

- 100% correlation coverage for required fixture spans and artifact versions.
- Zero supplied PII or secret values in exported span attributes or logs.
- Cardinality limits hold for every untrusted attribute in the drill.
- 100% of graduated cases have expert adjudication, provenance, expected behavior, and split assignment.
- The overfit candidate and bad canary are rejected automatically.
- Cost per successful outcome is reported for baseline and candidate runs where outcome and cost fixtures exist.
- Telemetry-backend loss adds no request failure in the supplied outage test.
- Non-executing reconstruction produces zero external calls.

## Execution contract

Core duration is **4-6 hours**. Prerequisites are the Chapter 11 solution, pinned OpenTelemetry Collector, deterministic CI exporter, local dashboards, sampled traces, and a read-only hashed holdout.

```text
uv sync --frozen
uv run policyops env up --lab ch12 --profile fixture
uv run policyops verify ch12 --profile fixture --junit build/ch12/junit.xml --evidence build/ch12
uv run policyops fault ch12 --scenario all
uv run policyops env down --lab ch12
```

Pull requests run `verify-ch12` and earlier gates. The extension exports the same semantic fields to one hosted or alternate local backend and runs a larger behavior canary while preserving redaction, holdout, rollback, and cost evidence.

## Dependencies and handoff

The project consumes Chapter 2 evaluation contracts, Chapter 11 events and action receipts, configuration hashes from prior chapters, and an accepted `ch11` checkpoint. It produces the artifact registry, semantic adapter, telemetry policy, SLO definitions, adjudication, graduated case, experiment ledger, protected-holdout evidence, behavior-canary rollback, reconstruction evidence, and harness-retirement ADR. Register these in `capstone/traceability.yaml`, compare with `ed2-v1.0-ch12-solution`, and tag `ch12-complete`. [Chapter 13](../ch13-prompt-injection-defense/prd.md) attacks the composed system and this improvement pipeline.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Traces become a sensitive data lake | Deny content fields by default, redact before export, isolate tenants, and limit retention and access. |
| Candidate optimizes the visible failure only | Require immutable holdout, regression, and safety gates before a canary. |
| Nondeterministic telemetry makes CI flaky | Use a deterministic file exporter and schema assertions in mandatory gates. |
| Canary rollback races with another release | Use an accepted-configuration alias with optimistic versioning and one active canary lease. |
| Trace reconstruction repeats an action | Resolve only rejecting model and effect adapters in reconstruction mode. |

## Delivery milestones

1. Freeze semantic fields, artifact schema, redaction policy, and deterministic export tests.
2. Instrument all required spans and build correlation and local dashboards.
3. Implement adjudication, non-executing reconstruction, and trace-to-eval graduation.
4. Implement bounded experiments, hash-protected assets, and keep-or-revert ledger.
5. Implement behavior canary, seeded rollback, evidence bundle, and earlier regressions.

## Future extensions

Add a hosted telemetry backend, larger sampled canary, drift clustering, human-review queue, and alternate semantic-convention adapter. Any extension must retain the deterministic exporter and the same privacy, immutable-evidence, and rollback gates.
