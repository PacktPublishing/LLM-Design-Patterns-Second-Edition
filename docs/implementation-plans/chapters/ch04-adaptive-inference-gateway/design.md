# Chapter 4 Design: Adaptive Inference Gateway

The implemented lab adds `policyops.inference`, a provider-neutral gateway package
that fulfills the chapter architecture role. It keeps the mandatory path CPU-only
and deterministic while exercising the production concerns from the chapter:
bounded test-time reasoning, verifier-guided escalation, safe cache identity,
budget accounting, and benchmark evidence.

## Implemented components

- `InferenceRequest`, `InferenceBudget`, `ModelProfile`, `CacheKey`,
  `CandidateResult`, `GatewayResult`, and benchmark schemas.
- `AdaptiveInferenceGateway`, which implements the Chapter 1 `ModelClient` port.
- `BudgetLedger` for total request duration, spend, and candidate limits.
- `ResponseCache` with tenant, authorization, semantic request, model/profile,
  configuration, policy, freshness, and schema identity.
- Deterministic verifier and route planner for direct, enhanced, quantized, and
  speculative fixture paths.
- Benchmark runner that emits raw rows, a selected profile, Pareto labels, and a
  serving ADR.

## Verification

```powershell
uv run ruff check src/policyops/inference tests/inference
uv run policyops verify ch04 --profile fixture --junit build/ch04/junit.xml --evidence build/ch04
uv run policyops fault ch04 --scenario all
```

The fixture profile proves behavior and contracts. It does not claim real provider
latency, GPU throughput, or current market pricing.
