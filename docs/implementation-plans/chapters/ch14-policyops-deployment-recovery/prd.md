# Chapter 14 Project PRD: Deploy and Recover the PolicyOps Service

This project implements the hands-on work for Chapter 14, **Production Deployment and Reliability Patterns**. It takes the crash-consistent protocol from [Chapter 11](../ch11-resumable-agent-loop/prd.md), the behavior evidence from [Chapter 12](../ch12-trace-to-safe-improvement/prd.md), and the containment controls from [Chapter 13](../ch13-prompt-injection-defense/prd.md), then operates them across processes, queues, dependency failures, rollouts, and backup restoration. The companion [architecture](./architecture.md) defines the production-shaped topology.

## Product proposal

Deploy the PolicyOps API, worker, database, model gateway, telemetry collector, egress controls, and ticket service with Docker Compose. Add health checks, bounded work admission, deadlines, retry classification, backpressure, canary rollback, load and fault profiles, and backup/restore validation. Simulate dependency outages and a faulty release without losing durable state or duplicating an approved ticket.

## Problem

A correct loop can still fail when its worker is replicated, its dependency slows down, its queue grows without bound, or a bad image or migration reaches production. Simple retries can amplify outages; provider fallback can silently lower quality; a stale readiness check can route traffic to a service that cannot safely resume; and an untested backup may be unusable. PolicyOps needs a runnable local production topology that makes its scaling units and failure domains explicit and generates recovery evidence under declared hardware rather than promising portable performance.

## Goals

- Place gateway, API, durable session store, stateless workers, sandboxes, tools, credentials, and telemetry in explicit processes and network zones.
- Enforce end-to-end deadlines, cancellation, bounded queues, concurrency limits, and backpressure.
- Scale Chapter 11's outbox and idempotency protocol across multiple workers and delivery attempts.
- Operate Chapter 4's model profile through provider health, failover, and declared degraded modes without silently lowering its quality floor.
- Distinguish liveness, readiness, dependency health, and safe-to-resume state.
- Test load, model/tool/store/network faults, worker loss, bad container rollout, rollback, backup corruption, restore integrity, and recovery time and data-loss objectives.
- Produce exact operator, rollback, migration, and restore runbooks.

## Non-goals

- Redesigning agent state, checkpoint, approval, or idempotency semantics from Chapter 11.
- Running prompt, model, routing, or policy behavior canaries; Chapter 12 owns those.
- Reimplementing Chapter 13 policy, sandbox, egress, or secret controls.
- Requiring Kubernetes for the core project; Kind and Helm are a separately timed extension.
- Claiming universal latency or capacity numbers independent of declared hardware and fixture workload.
- Making the final governance release decision; Chapter 15 consumes this evidence.

## Users

- **Platform engineer:** packages and deploys services, policies, migrations, and configuration.
- **Site reliability engineer:** defines SLOs, capacity limits, fault tests, recovery objectives, and runbooks.
- **AI engineer:** validates provider failover and quality-floor behavior.
- **Database engineer:** owns migration safety, backup, restore, and integrity checks.
- **Operator:** diagnoses, contains, rolls back, restores, and validates a failed service.

## User stories

- As an operator, I can tell whether a process is alive, ready for new work, and safe to resume existing sessions.
- As an SRE, I can overload the fixture service and see bounded rejection or deferral rather than unbounded memory and queue growth.
- As an AI engineer, I can fail the primary model and observe only a policy-approved fallback or a declared degraded response.
- As a database engineer, I can reject a corrupt backup and restore a valid one within the declared objectives.
- As a release engineer, I can canary a bad container, observe automatic rollback, and retain immutable evidence of the decision.

## Functional requirements

- **CH14-FR-001:** The deployment shall separate API/control plane, PostgreSQL durable state, stateless workers, outbox delivery, model gateway, sandbox/tool runtime, ticket service, egress proxy, and telemetry collector into declared processes and networks.
- **CH14-FR-002:** The gateway shall propagate request, session, tenant, actor, configuration, deadline, cancellation, budget, authorization, approval, and idempotency metadata across service boundaries.
- **CH14-FR-003:** Work admission shall enforce bounded queue depth, weighted tenant fairness, per-tenant and global concurrency, maximum payload size, deadline feasibility, and explicit service-entry `429` overload responses with safe `Retry-After` guidance; rejected work shall never enter the durable queue.
- **CH14-FR-004:** Workers shall claim work with durable ownership, acknowledge only after checkpoint or terminal state persistence, and preserve Chapter 11 fencing and idempotency invariants across replicas.
- **CH14-FR-005:** Retry policy shall classify transient, throttling, timeout, semantic, policy, authorization, and permanent failures and cap attempts, elapsed time, and retry amplification.
- **CH14-FR-006:** Circuit breakers shall isolate failing model, tool, store, and sandbox dependencies; half-open probes shall not consume normal request budgets or create effects.
- **CH14-FR-007:** Provider-health routing shall use Chapter 4 capability and quality constraints and shall return a declared degraded or unavailable result rather than silently choosing an inadequate model.
- **CH14-FR-008:** Liveness, startup, readiness, and dependency diagnostics shall be distinct; readiness shall include schema compatibility, durable-store access, configuration validity, and safe worker participation.
- **CH14-FR-009:** Database changes shall use a migration plan with compatibility window, preflight, transactional or resumable execution, rollback or roll-forward action, and clean-database verification.
- **CH14-FR-010:** The container rollout controller shall canary digest-pinned images against health, error, saturation, policy, and smoke-test gates and automatically restore the accepted digest on failure.
- **CH14-FR-011:** Backup jobs shall capture required durable state and metadata, verify checksums and catalog, reject corrupt material, and restore into an isolated environment for integrity checks.
- **CH14-FR-012:** Load and chaos suites shall inject worker, sandbox, model, tool, database, network, queue, disk-pressure, redelivery, brownout, overlapping-binary rollout, and restore/reconciliation faults and measure SLO, recovery time objective (RTO), and recovery point objective (RPO) results.
- **CH14-FR-013:** Operator commands and runbooks shall cover diagnosis, traffic containment, provider failover, queue draining, reconciliation, rollback, restore, validation, and escalation.

## Non-functional requirements

- **CH14-NFR-001:** The required Compose core shall run on the declared approximately 12 GB RAM profile without paid model credentials.
- **CH14-NFR-002:** Every image shall run as non-root, have a read-only root filesystem where compatible, declare limits, and be pinned by digest in release evidence.
- **CH14-NFR-003:** Performance results shall name fixture version, workload, concurrency, hardware, configuration, and warm-up; p95 and error thresholds shall be declared before the run.
- **CH14-NFR-004:** Queue, retry, breaker, and timeout settings shall be configuration-as-code with schema validation and safe defaults.
- **CH14-NFR-005:** A telemetry outage shall not prevent core request handling, while loss and buffering limits remain observable.
- **CH14-NFR-006:** The verifier shall emit JSON, JUnit, trace, dependency, fixture, configuration, image, migration, load, chaos, and declared-hardware evidence and exit non-zero on failure.

## Security and privacy requirements

- **CH14-SEC-001:** Networks shall default deny cross-zone access; only required service-to-service paths shall be routable.
- **CH14-SEC-002:** Tenant partitions shall apply to durable state, queues, indexes, memory, traces, credentials, rate limits, and sandboxes.
- **CH14-SEC-003:** Services shall receive only workload-specific credentials through runtime injection; secrets shall not appear in images, Compose files, logs, or evidence.
- **CH14-SEC-004:** Health endpoints shall not expose secrets, tenant data, internal stack traces, or sensitive dependency details.
- **CH14-SEC-005:** Rollback and restore shall preserve current revocations, approval validity rules, audit evidence, and deletion obligations.
- **CH14-SEC-006:** Dependency and image scans, policy checks, and SBOM validation shall block a release when mandatory controls fail.

## Starter, fixtures, and data

Start from `ed2-v1.0-ch14-start`. The supplied Compose baseline includes API, worker, PostgreSQL, model gateway, telemetry collector, Toxiproxy-style dependency fault injection, egress proxy, and ticket service, plus working scaffolds for admission/backpressure configuration, canary control, backup/restore orchestration, and the scenario driver. Readers complete the policies, thresholds, health gates, reconciliation, and recovery assertions rather than building deployment controllers from scratch. Kind and Helm scaffolds are reserved for the extension. Fixtures include deterministic model responses, load scenarios, a bad image, compatible and incompatible migrations, valid and corrupt backups, and expected recovery evidence.

Primary paths are `deploy/compose`, `deploy/helm`, `deploy/kind`, `tests/load`, `tests/chaos`, and `docs/runbooks`. `labs/ch14/manifest.toml` declares the hardware, network, services, image and fixture hashes, commands, cleanup, acceptance thresholds, and fault matrix.

## External behavior and operator interfaces

The API preserves Chapter 1 `/health/live` and `/health/ready`, adds `/health/startup`, and exposes an authenticated diagnostic endpoint. Overload returns a typed response with retry guidance when safe; expired deadlines are not enqueued. Operator CLI commands include `policyops ops status`, `queue drain`, `outbox reconcile`, `release canary`, `release rollback`, `backup verify`, `restore run`, and `game-day execute`. All mutating operator commands require authenticated role, explicit target, dry-run preview where feasible, and an evidence record.

## Required drill

Kill the harness worker and sandbox; duplicate a queued effect; fail the model and ticket service; add latency and packet loss; exhaust a dependency; overload the queue; deploy the bad image; present a corrupt backup; and restore valid durable state. Each scenario records detected condition, automatic response, operator action if needed, recovery duration, data loss, final integrity, and duplicate-effect count.

## Required artifacts

Deliver digest-pinned images, Compose and optional Kind/Helm bundles, migrations, configuration schemas, load and chaos scripts, SLO dashboard, canary and rollback evidence, verified backup and restore evidence, and operator, migration, rollback, and recovery runbooks.

## Acceptance criteria and traceability

- **AC-01 (CH14-FR-003, CH14-FR-004, CH14-FR-005, CH14-FR-006):** Given the declared load and dependency faults, when capacity is exceeded, then weighted tenant fairness remains within its declared bound, queues remain bounded, service-entry overload returns typed `429` without enqueueing, retries do not amplify without limit, breakers isolate failures, and the service rejects or degrades explicitly.
- **AC-02 (CH14-FR-004):** Given duplicate delivery and worker termination, when processing resumes, then one idempotency key produces one ticket and durable state remains consistent.
- **AC-03 (CH14-FR-007):** Given primary model failure, when routing evaluates alternatives, then only a capability- and quality-compliant fallback runs; otherwise the result declares unavailability or approved degradation.
- **AC-04 (CH14-FR-009, CH14-FR-010, CH14-SEC-006):** Given unsafe migration or bad image, when pull-request and canary gates run, then deployment is blocked or automatically rolled back to the accepted digest.
- **AC-05 (CH14-FR-011, CH14-FR-012, CH14-SEC-005):** Given corrupt and valid backups, when validation and restore run, then corrupt material is rejected, valid state passes integrity checks, and measured RTO/RPO satisfy the predeclared fixture objectives.
- **AC-06 (CH14-NFR-003, CH14-NFR-006):** Given declared hardware and workload, when load runs, then p95 and error results are captured and evaluated against frozen thresholds with complete evidence.
- **AC-07 (CH14-SEC-001, CH14-SEC-002, CH14-SEC-003, CH14-SEC-004):** Given cross-zone, cross-tenant, secret, and health-endpoint probes, then unauthorized paths fail and sensitive data remains absent.
- **AC-08 (CH14-FR-001, CH14-FR-002, CH14-FR-008, CH14-FR-013):** Given the Compose topology, then each declared process/network boundary is present, the full request/session/identity/configuration/budget/approval/idempotency envelope survives a cross-service trace, health states distinguish process/startup/readiness/dependency failures, and every injected incident resolves to an executable diagnosis, containment, recovery, validation, and escalation runbook step.
- **AC-09 (CH14-FR-004, CH14-FR-010, CH14-FR-011, CH14-FR-012):** Given multi-worker claim races, effect redelivery, provider brownout, overlapping old/new binaries, and restored state, the Chapter 11 action-intent/outbox/idempotency/receipt protocol remains unchanged, exactly one business effect is observed, and reconciliation completes before readiness.

## Success metrics

- Queue depth never exceeds its configured hard bound in the supplied load profile.
- Zero duplicate tickets across all queue, worker, and network fault scenarios.
- Retry attempts and concurrent work remain within predeclared budgets.
- Bad image rolls back automatically and the accepted digest resumes serving.
- Corrupt backup is rejected; valid restore meets fixture RTO/RPO and integrity checks.
- Declared p95 latency and error SLOs pass on the recorded hardware profile.
- Every game-day scenario produces a complete, machine-readable result and runbook reference.

## Execution contract

The required Compose core takes **6-8 hours**. The optional Kind/Helm extension takes **4-6 additional hours**. The core expects Docker Compose and about 12 GB RAM; no paid model credential is required.

```text
uv sync --frozen
uv run policyops env up --lab ch14 --profile fixture
uv run policyops verify ch14 --profile fixture --junit build/ch14/junit.xml --evidence build/ch14
uv run policyops fault ch14 --scenario all
uv run policyops env down --lab ch14
```

Pull requests run `verify-ch14` plus all earlier regression gates, proving bounded queues, no duplicate effects, policy checks, migration safety, and successful recovery. Nightly system gates exercise Kind deployment, bad-canary rollback, corrupt-backup rejection, restore integrity, and RTO/RPO evidence. The extension lints and renders Helm, deploys digest-pinned images to Kind, runs binary and schema canaries, and repeats chaos and restore checks.

## Dependencies and handoff

The project consumes the accepted Chapter 11 effect protocol, Chapter 12 semantic fields and SLO format, Chapter 13 policy/sandbox/egress controls, Chapter 4 gateway profile, and prior data stores. It produces image digests, Compose and optional Helm bundles, migrations, load and chaos reports, SLO dashboard, canary rollback, backup/restore evidence, and operator runbooks. Register them in `capstone/traceability.yaml`, compare with `ed2-v1.0-ch14-solution`, and tag `ch14-complete`. [Chapter 15](../ch15-governance-release-review/prd.md) governs the evidence and release decision.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Local Compose results are mistaken for cloud capacity | Bind every result to hardware, workload, configuration, and fixture hashes. |
| Retries cause cascading failure | Classify failures, cap budgets, propagate deadlines, and use breakers and backpressure. |
| Readiness says healthy while recovery is unsafe | Include schema, durable store, configuration, and worker-participation checks. |
| Backup exists but cannot restore | Verify catalog and checksums and restore into isolation on a schedule. |
| Rollback reintroduces revoked access or deleted data | Reconcile current governance and security state after restore before serving traffic. |

## Delivery milestones

1. Freeze topology, network zones, manifests, thresholds, recovery objectives, and image policy.
2. Implement metadata propagation, health/readiness, bounded admission, deadlines, and cancellation.
3. Add replicated workers, retry classification, breakers, backpressure, and reconciliation.
4. Add migration gates, image canary and rollback, backup verification, and isolated restore.
5. Run load and chaos matrix, complete runbooks, and register release evidence.

## Future extensions

Deploy the same contracts to Kind/Helm, add regional provider failover, test a managed queue, and automate scheduled restore drills. Each extension must preserve the fixture profile and state which new failure domains and operational assumptions it introduces.
