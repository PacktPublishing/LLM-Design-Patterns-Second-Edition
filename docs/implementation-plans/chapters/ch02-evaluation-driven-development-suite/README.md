# Validation README: Evaluation-Driven Development Suite

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch02/README.md](../../../../labs/ch02/README.md)
- Repo-wide regression check on August 5, 2026: full suite `285 passed` via `uv run pytest tests -q`
- Chapter verification on August 5, 2026: chapter gate `44 passed` via `uv run policyops verify ch02 --profile fixture --junit build/ch02/junit.xml --evidence build/ch02`

## Verified commands

- `uv run policyops verify ch02 --profile fixture --junit build/ch02/junit.xml --evidence build/ch02`
- `uv run pytest tests/eval/test_eval.py -q`
- Validation summary: [ch02 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/eval](../../../../src/policyops/eval)
- Test directories: [tests/eval](../../../../tests/eval)
- Evidence artifacts: [junit.xml](../../../../build/ch02/junit.xml), [summary.json](../../../../build/ch02/summary.json), [cost_report.json](../../../../build/ch02/cost_report.json), [evidence_index.json](../../../../build/ch02/evidence_index.json), [grades.jsonl](../../../../build/ch02/grades.jsonl), [failure_taxonomy.json](../../../../build/ch02/failure_taxonomy.json)

## Coverage map

- Versioned task cases and graders: [src/policyops/eval](../../../../src/policyops/eval), [tests/eval](../../../../tests/eval), [grades.jsonl](../../../../build/ch02/grades.jsonl)
- Failure taxonomy and holdout governance: [src/policyops/eval](../../../../src/policyops/eval), [tests/eval](../../../../tests/eval), [failure_taxonomy.json](../../../../build/ch02/failure_taxonomy.json), [evidence_index.json](../../../../build/ch02/evidence_index.json)
- Release gating and measured CPSO outputs: [src/policyops/eval](../../../../src/policyops/eval), [tests/eval](../../../../tests/eval), [summary.json](../../../../build/ch02/summary.json), [cost_report.json](../../../../build/ch02/cost_report.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
