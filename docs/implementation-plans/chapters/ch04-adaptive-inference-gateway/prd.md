# Chapter 4 PRD: Build an Adaptive Inference Gateway

**Chapter:** Test-Time Reasoning and Inference Optimization Patterns
**Related design:** [Architecture](./architecture.md)
**Inputs:** [Chapter 2 release suite](../ch02-evaluation-driven-development-suite/prd.md) and [Chapter 3 adaptation decision](../ch03-adaptation-strategy/prd.md)
**Implementation checkpoint:** `ed2-v1.0-ch04-start` to `work/ch04`

## Product context

PolicyOps has a selected baseline or adaptation candidate and a reusable release suite. This project inserts a request-level inference gateway behind the existing `ModelClient` port. It chooses direct or enhanced reasoning, generates a bounded number of candidates, applies deterministic verification, escalates from a small to a larger model profile when justified, enforces token/time/spend budgets, and uses a tenant-safe response cache.

The lab owns quality-driven compute allocation and model-server optimization. It does not own provider-health failover, fleet capacity, whole-service queues, or deployment rollout, which Chapter 14 addresses.

## Problem statement

Using the largest model and maximum reasoning effort for every request wastes latency and cost, while using a cheap single pass for every request may violate quality and safety expectations. Unscoped caches can leak tenant data or return stale answers, and unbounded candidate generation can exhaust budgets. PolicyOps needs a deterministic gateway policy that allocates more inference only when task and verification signals justify it, records its decision, compares cost per successful outcome, and safely terminates under faults.

## Goals

- Implement direct generation and bounded enhanced-reasoning paths.
- Support deterministic candidate verification and early exit.
- Route between replayable small and large model profiles based on declared quality and policy signals.
- Enforce input/output token, wall-clock, candidate, reserved future tool-call, and spend budgets.
- Implement an in-memory response cache with complete tenant, authorization, model, prompt, configuration, and freshness keys.
- Benchmark cold and warm paths against Chapter 2 quality gates.
- Produce a Pareto comparison and select a serving profile that improves at least one objective, including cost per successful outcome where applicable, without crossing the quality floor.
- Fail or fall back predictably on stale cache, verifier failure, timeout, and budget exhaustion.

## Non-goals

- Selecting a new adapted model or changing Chapter 3 data/model lineage.
- Building context planning, retrieval, or semantic cache embeddings.
- Provider outage detection, cross-region failover, autoscaling, broker queues, or binary rollout.
- Requiring quantization, speculative decoding, shared KV caching, or GPU hardware in the core lab.
- Treating fixture latency or spend as portable production performance.

## Users

- **AI application engineer:** defines task classes, verification rules, and escalation policy.
- **Performance engineer:** runs workload benchmarks and compares quality, latency, total cost, and cost per successful outcome.
- **Platform operator:** inspects route decisions, budget outcomes, and cache behavior.
- **Release reviewer:** verifies that an optimized profile retains Chapter 2 gates.

## User stories

- As a caller, I receive an answer or typed budget/deadline failure within declared limits.
- As an AI engineer, I can explain why a request used direct generation, multiple candidates, or model escalation.
- As a tenant administrator, I can trust that another tenant or authorization state cannot reuse my cached result.
- As a release reviewer, I can compare raw benchmark evidence rather than accept a generic optimization claim.

## Functional requirements

- **CH04-FR-001:** Define `InferencePolicy`, `InferenceBudget`, `RouteDecision`, `Candidate`, `VerificationResult`, `CacheKey`, and `GatewayResult` contracts with schema and policy versions.
- **CH04-FR-002:** Accept the Chapter 1 `ModelRequest` and `RunContext`, calculate remaining deadline/budget, and reject impossible work before a model call.
- **CH04-FR-003:** Implement a direct path that invokes one configured model profile and validates its structured result.
- **CH04-FR-004:** Implement bounded candidate generation with an explicit maximum count, remaining-budget checks before every call, deterministic ranking/verification, and early exit on a verified result.
- **CH04-FR-005:** Implement quality-driven small-to-large routing using declared task class, risk, verification outcome, and remaining budget; do not use provider health as a routing signal in this chapter.
- **CH04-FR-006:** Enforce token, candidate, time, and spend ceilings across the entire request, including failed attempts; return a typed reason when no safe path remains.
- **CH04-FR-007:** Implement a response cache keyed by tenant, effective authorization, model/profile, prompt/context fingerprint, inference policy/configuration, data/source freshness, and request semantics.
- **CH04-FR-008:** Reject expired, stale, authorization-mismatched, corrupted, or schema-incompatible cache entries; validate cached answers before return.
- **CH04-FR-009:** Record route, candidate count, verification result, budget consumption, cache outcome, latency, and safe fallback reason in correlated evidence.
- **CH04-FR-010:** Run deterministic workload benchmarks for direct, enhanced, routed, cold-cache, and warm-cache profiles using the Chapter 2 suite.
- **CH04-FR-011:** Produce raw benchmark data, quality-latency-cost and cost-per-successful-outcome comparison, Pareto plot, routing policy, and serving ADR.
- **CH04-FR-012:** Support optional declared-hardware experiments for shared/prefix/KV cache, quantization, batching, or speculative decoding without changing fixture-profile gates.

## Non-functional requirements

- **CH04-NFR-001:** Every request must terminate within its deadline or a bounded cancellation grace period.
- **CH04-NFR-002:** Deterministic replay fixtures, fake clock, and seeded workload must reproduce route, verification, cache, and budget outcomes.
- **CH04-NFR-003:** Gateway policy must remain provider-neutral and configurable without importing provider SDK types into domain/application packages.
- **CH04-NFR-004:** Benchmark evidence must record hardware, workload, concurrency, cache state, model/configuration hashes, quality floor, and raw per-request results.
- **CH04-NFR-005:** The in-memory core must run without GPU, external cache, hosted model, or paid credential.
- **CH04-NFR-006:** Cancellation and timeout handling must release request-scoped resources and prevent late results from populating the cache.

## Security and privacy requirements

- **CH04-SEC-001:** Cache keys must isolate tenant and effective authorization, not only user-supplied query text.
- **CH04-SEC-002:** Sensitive or non-cacheable classifications must bypass storage; cache metadata and telemetry must not contain raw secrets.
- **CH04-SEC-003:** Cached entries must bind configuration, model, prompt/context, source freshness, schema, and policy versions.
- **CH04-SEC-004:** Route policy cannot escalate model or budget beyond tenant and actor authorization.
- **CH04-SEC-005:** Candidate outputs and cached values remain untrusted until the same schema and semantic validators pass.
- **CH04-SEC-006:** Cache corruption, key collision tests, or unavailable verification must fail closed rather than return an unverified answer.

## Fixtures and data

The starter supplies replayable “small” and “large” model outputs, a fake clock, deterministic verifier scaffold, workload generator, and in-memory cache implementation seam. Workloads contain easy, ambiguous, verification-failing, timeout, and budget-constrained cases mapped to Chapter 2 task IDs. Price tables are fixture data and clearly labeled; they demonstrate spend accounting rather than quote current provider prices.

Cache fixtures include current, expired, wrong-tenant, wrong-authorization, wrong-configuration, stale-source, corrupted, and schema-old entries. Raw benchmark rows preserve input class and artifact hashes but not sensitive prompt bodies.

## External behavior and configuration

The Chapter 1 API contract remains stable. Successful responses add non-sensitive inference metadata such as route ID, cache status, and budget consumption. Typed failures distinguish deadline exceeded, budget exhausted, no verified candidate, invalid cached result, and model failure.

An illustrative policy is:

```yaml
default_route: direct_small
enhanced:
  max_candidates: 3
  escalate_on: [verification_failed, high_risk]
budgets:
  max_total_tokens: 6000
  max_duration_ms: 5000
  max_spend_units: 25
cache:
  ttl_seconds: 300
  cacheable_classifications: [public, internal]
```

Fixture values are locked at implementation kickoff and validated against hard safety ceilings.

## Acceptance criteria and traceability

| Criterion | Verification | Requirements |
|---|---|---|
| Policy, budget, route, candidate, verification, cache-key, and result contracts round-trip and reject unknown versions or unsafe limits. | Schema snapshot and invalid-policy tests | CH04-FR-001 |
| A request whose deadline or minimum safe budget is already impossible is rejected before cache or model work begins. | Spy-cache/adapter tests with fake clock and exhausted budgets | CH04-FR-002 |
| All requests obey token, candidate, time, and spend limits. | Fake-clock and usage-ledger property tests | CH04-FR-006, CH04-NFR-001 |
| Direct, enhanced, and routed paths produce explainable decisions. | Route evidence contract tests | CH04-FR-003, CH04-FR-004, CH04-FR-005, CH04-FR-009 |
| Cache isolates tenant, authorization, model, prompt, configuration, and freshness. | Collision and cross-context tests | CH04-FR-007, CH04-SEC-001, CH04-SEC-003 |
| Stale/corrupt entries never return and late results never populate cache. | Fault and cancellation tests | CH04-FR-008, CH04-NFR-006, CH04-SEC-006 |
| Verifier failure, timeout, and budget exhaustion exit or fall back safely. | Chapter fault runner | CH04-FR-004, CH04-FR-006 |
| Selected profile improves one objective without crossing Chapter 2 quality gates. | Locked benchmark comparison | CH04-FR-010, CH04-FR-011 |
| Hardware extension reports absolute results without becoming a fixture CI threshold. | Extension manifest validation | CH04-FR-012, CH04-NFR-004 |

## Success metrics

- 100% of fixture requests finish within declared budgets and deterministic route expectations.
- Zero cache hits across tenant, authorization, configuration, schema, or freshness boundaries.
- 100% stale, corrupt, and invalid cached answers are rejected.
- Selected profile retains every mandatory Chapter 2 gate and improves median latency, fixture spend, or quality on the declared workload.
- Every benchmark row binds model, policy, workload, cache, fixture, environment, and hardware identities.
- Seeded timeout, verifier, stale-cache, and exhaustion scenarios return expected typed outcomes.

## Dependencies and prerequisites

The lab consumes Chapter 2 gates and the Chapter 3 selected profile. It uses replayable model fixtures, a fake clock, workload generator, verifier, and in-memory cache. Python 3.12+, `uv`, Pydantic, pytest, FastAPI/OpenTelemetry integration, and no GPU are required for the core. Primary paths are `src/policyops/model_gateway`, `config/routing.yaml`, `tests/inference`, `tests/load`, and `build/ch04`.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Routing becomes an opaque model call. | Keep the core policy deterministic and emit a reasoned `RouteDecision`. |
| Candidate generation overruns budget. | Reserve/check worst-case cost before every call and cancel at the shared deadline. |
| Cache leaks data or serves stale policy. | Use complete keys, classification bypass, version/freshness binding, and validators. |
| Benchmark optimizes to fixtures. | Retain Chapter 2 holdouts and label hardware/workload limits. |
| Optional hardware path distracts from core concepts. | Keep it isolated and prohibit its numbers as portable CI thresholds. |
| Small-to-large routing duplicates failover. | Route solely on request quality/policy; defer provider health and fleet recovery to Chapter 14. |

## Delivery milestones

1. Define policies, budgets, route decisions, usage ledger, and cache contracts.
2. Implement direct path and deterministic verifier.
3. Add bounded candidates, early exit, and quality-driven escalation.
4. Add complete cache keys, validation, expiry, and cancellation safety.
5. Build workload runner and raw quality-latency-cost plus outcome-cost reports.
6. Run all fault drills, choose a profile by predeclared floor, and register gateway, policy, benchmark, cache, and ADR evidence in `capstone/traceability.yaml`.

## Outline implementation contract

- **Starter:** Begin from `ed2-v1.0-ch04-start` with replayable model outputs, workload generator, and the Chapter 2 gates.
- **Task:** Implement direct generation, bounded candidate generation, deterministic verification, quality-driven routing, token/time/spend limits, and a tenant-, authorization-, model-, prompt-, configuration-, and freshness-aware response cache.
- **Extension:** Benchmark one shared-cache, prefix/KV-caching, quantization, batching, or speculative-decoding profile on declared hardware; retain absolute latency as labeled evidence rather than a portable CI threshold.
- **Failure drill:** Inject a stale cache entry, verifier failure, timeout, and budget exhaustion; prove that the gateway exits or falls back only through a safe declared path.
- **Artifacts:** Gateway, raw benchmark data, cold/warm-cache report, routing policy, Pareto plot, and serving ADR.
- **Acceptance:** Every request obeys deadline and budget; cache keys isolate tenant and configuration; stale entries invalidate; the selected profile improves one objective without crossing the Chapter 2 quality floor.
- **Verification:** `uv run policyops verify ch04 --profile fixture --junit build/ch04/junit.xml --evidence build/ch04`
- **Run and cleanup:** `uv sync --frozen`; `uv run policyops env up --lab ch04 --profile fixture`; run the verification command; `uv run policyops fault ch04 --scenario all`; `uv run policyops env down --lab ch04`.
- **Repository and CI:** Use `labs/ch04/manifest.toml`; primary paths are `src/policyops/model_gateway`, `config/routing.yaml`, `tests/inference`, `tests/load`, and `build/ch04`. Pull requests run `verify-ch04` plus all earlier regression gates and retain JSON, JUnit, trace, dependency, fixture, configuration, and hardware evidence.
- **Handoff:** Compare `work/ch04` with `ed2-v1.0-ch04-solution` and register gateway, routing, cache, budget, benchmark, serving ADR, test command, and rollback evidence in `capstone/traceability.yaml`; Chapter 5 consumes the selected profile and Chapter 14 operates it under fleet failure.
- **Proposal:** Add direct and enhanced-reasoning paths, deterministic verification, model routing, token and time budgets, and safe response caching; compare quality, latency, spend, and cost per successful outcome.

## Future extensions

On declared hardware, readers may measure one shared cache, prefix/KV cache, quantization, batching, or speculative-decoding configuration. Chapter 5 consumes the selected profile and structures its context. Chapter 14 later operates the gateway under provider failure, queues, capacity constraints, and binary rollout.
