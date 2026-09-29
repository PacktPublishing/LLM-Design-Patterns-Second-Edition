# Validation Summary

This file records the latest implementation-validation pass for the chapter labs. The policy guidance below remains in force, and the run results beneath it show the current READY status backed by source, tests, and build evidence.

## Latest run

- Date: August 2, 2026
- Repo-wide regression: `uv run pytest tests -q` -> `213 passed, 1 warning`
- Chapter verification loop: `uv run policyops verify chNN --profile fixture ...` for `ch01` through `ch16` completed with exit code `0` for all chapters
- Capstone verification: `uv run policyops verify ch16 --profile fixture --all --junit build/ch16/junit.xml --evidence build/ch16` passed
- Test fix applied during validation: [tests/inference/test_inference_gateway.py](../../tests/inference/test_inference_gateway.py)

## Chapter verdicts

- ch01: READY, `4.87s`, see [chapter README](chapters/ch01-policyops-foundation/README.md)
- ch02: READY, `3.84s`, see [chapter README](chapters/ch02-evaluation-driven-development-suite/README.md)
- ch03: READY, `2.34s`, see [chapter README](chapters/ch03-adaptation-strategy/README.md)
- ch04: READY, `2.29s`, see [chapter README](chapters/ch04-adaptive-inference-gateway/README.md)
- ch05: READY, `2.49s`, see [chapter README](chapters/ch05-context-planner/README.md)
- ch06: READY, `2.56s`, see [chapter README](chapters/ch06-citation-first-hybrid-rag/README.md)
- ch07: READY, `3.41s`, see [chapter README](chapters/ch07-graph-retrieval/README.md)
- ch08: READY, `3.01s`, see [chapter README](chapters/ch08-governed-long-term-memory/README.md)
- ch09: READY, `2.68s`, see [chapter README](chapters/ch09-secure-extension-pack/README.md)
- ch10: READY, `2.85s`, see [chapter README](chapters/ch10-bounded-orchestrator-worker/README.md)
- ch11: READY, `2.96s`, see [chapter README](chapters/ch11-resumable-agent-loop/README.md)
- ch12: READY, `3.03s`, see [chapter README](chapters/ch12-trace-to-safe-improvement/README.md)
- ch13: READY, `3.31s`, see [chapter README](chapters/ch13-prompt-injection-defense/README.md)
- ch14: READY, `3.04s`, see [chapter README](chapters/ch14-policyops-deployment-recovery/README.md)
- ch15: READY, `3.22s`, see [chapter README](chapters/ch15-governance-release-review/README.md)
- ch16: READY, `3.43s`, see [chapter README](chapters/ch16-policyops-capstone/README.md)

## Policy guidance

For every chapter lab (and before declaring a chapter complete):

1. Implement features + tests in the working agent.
2. Always run an independent validation pass whose only job is to inventory PRD/design claims vs tests, run pytest and chapter verify commands, add missing high-value tests or report gaps, and return READY / NOT READY.
3. Fix gaps found by the validator and rerun verify until green.
4. Do not treat fixture latency or replay answers as real-model quality.

This file is code-facing process guidance only, not manuscript content.
