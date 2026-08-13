# Chapter 4 Lab: Adaptive Inference Gateway

This lab implements a fixture-runnable inference gateway for PolicyOps. It allocates
test-time compute by request risk, verifies candidates deterministically, escalates
from small to stronger profiles only when needed, enforces spend/time/candidate
budgets, and uses a tenant-safe response cache.

### Route profiles

Routing is a named, reviewable policy layer (`src/policyops/inference/route_policy.py`)
over the underlying model profiles, not an ad-hoc per-request choice. The benchmark
compares exactly three route profiles:

- **`direct-baseline`** — a single `small-fast` call, no escalation. Cheapest and fastest,
  but has no fallback if that one candidate fails verification.
- **`enhanced-with-candidates`** — up to three `standard`-tier candidates sampled at one
  tier, with no escalation across tiers.
- **`routed-with-escalation`** — an escalating `small-fast` → `standard` → `reasoned`
  sequence with early exit on the first verified candidate.

Run it with:

```powershell
uv run policyops verify ch04 --profile fixture --junit build/ch04/junit.xml --evidence build/ch04
uv run policyops fault ch04 --scenario all
```

Evidence is written under `build/ch04/`, including:

- `benchmark_rows.jsonl` — raw per-(request, route profile, cache state) rows.
- `inference_report.json` — the full benchmark report: raw rows plus per-profile
  aggregates (p50/p95/p99 latency, cost per successful outcome, success rate, Pareto
  dominance) for the 3 route profiles x {cold, warm} cache-state matrix.
- `benchmark_summary.json` — per-profile summary and the objective-improvement reasons
  behind the selected profile.
- `matched_pair_comparison.json` — for every fixture case, every pair of route profiles is
  classified as agreement / disagreement / reversal, with the full reversal set listed
  explicitly (not just counted).
- `serving_adr.json` — the decision record: chosen route profile, the conditions under
  which that choice holds, a rollback plan, and an explicit statement of what this
  benchmark does NOT prove.
- `route_policy_manifest.json` — the three route profiles' definitions and budgets.
- `gateway_result.json`, `fingerprints.json`, `junit.xml`, and the standard redacted trace
  sample.

Fixture latency and spend are learning evidence, not hosted-provider performance
claims.

## GitHub evidence

- Source implementation: [src/policyops/inference](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/inference)
- Primary tests: [tests/inference/test_inference_gateway.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/inference/test_inference_gateway.py)
- Recorded verification evidence: [build/ch04](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch04) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch04/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch04/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch04/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch04-adaptive-inference-gateway/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch04-adaptive-inference-gateway/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch04-adaptive-inference-gateway/design.md)
