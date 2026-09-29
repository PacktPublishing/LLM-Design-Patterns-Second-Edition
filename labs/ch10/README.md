# Chapter 10 Lab: Build a Bounded Orchestrator-Worker Flow

This lab compares four ways to run the same PolicyOps triage task: deterministic workflow, single replay-backed agent, browser/computer-use fixture, and orchestrator-worker fan-out. The lesson is deliberately practical: use the least complex topology that satisfies the measured requirement.

## GitHub evidence

- Source implementation: [src/policyops/orchestration](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/orchestration)
- Primary tests: [tests/orchestration/test_bounded_orchestration.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/orchestration/test_bounded_orchestration.py)
- Recorded verification evidence: [build/ch10](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch10) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch10/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch10/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch10/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch10-bounded-orchestrator-worker/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch10-bounded-orchestrator-worker/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch10-bounded-orchestrator-worker/design.md)

## What you build

- A canonical transient `TaskState` and state-graph boundary.
- Deterministic, single-agent, browser/computer-use, and orchestrator-worker variants over the same state and ToolPort.
- Signed, narrow delegation records for worker tasks.
- Deterministic result validation and merge.
- Run-local fan-out budget admission with no partial spawn.
- Pause, resume, and cancel transitions for Chapter 11 to make durable.
- A topology comparison report and A2A no-use ADR.

## Run

```bash
uv run policyops verify ch10 --profile fixture --junit build/ch10/junit.xml --evidence build/ch10
uv run policyops fault ch10 --scenario all
```

## Evidence

The verification command writes:

- `state_graph_runs.json`
- `delegation_contract.json`
- `worker_results.json`
- `topology_comparison.json`
- `a2a_no_use_adr.json`
- `orchestration_scorecard.json`

## Production lesson

Agents and workers are not free. Each new topology moves context, authority, budget, and accountability across another boundary. Use deterministic routing for known rules, isolate worker authority when delegation helps, treat browser observations as untrusted, and keep final writes behind the Chapter 9 exact-effect approval boundary.
