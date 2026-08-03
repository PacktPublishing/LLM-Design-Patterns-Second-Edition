# Chapter 16 Lab: Integrate and Release the PolicyOps Agent

This lab runs the capstone release verifier. It validates the accepted Chapter 1-15 handoffs, executes the ordered production game day, signs the evidence bundle, and returns a final `GO` or `NO-GO` decision.

## GitHub evidence

- Source implementation: [src/policyops/capstone](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/capstone)
- Primary tests: [tests/capstone/test_capstone.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/capstone/test_capstone.py)
- Recorded verification evidence: [build/ch16](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch16) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch16/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch16/result.json) | [capstone_scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch16/capstone_scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch16-policyops-capstone/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch16-policyops-capstone/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch16-policyops-capstone/design.md)

## What you build

- A traceability closure validator.
- A 16-step ordered game-day runner.
- A seeded mandatory-failure proof.
- A signed release evidence bundle.
- A final capstone scorecard and release decision.

## Run

```bash
uv run policyops verify ch16 --profile fixture --all --junit build/ch16/junit.xml --evidence build/ch16
uv run policyops fault ch16 --scenario all
```

## Evidence

The verification command writes:

- `traceability_closure.json`
- `game_day_results.json`
- `seeded_failure_game_day.json`
- `release_bundle.json`
- `release_decision.json`
- `seeded_failure_decision.json`
- `capstone_scorecard.json`

## Production lesson

A production AI system is not ready because each pattern worked once. It is ready only when the assembled system preserves identity, evidence, authorization, citations, memory rights, approval, idempotency, security, operations, governance, and release accountability across the boundaries where failures actually happen.
