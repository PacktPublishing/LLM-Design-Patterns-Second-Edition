# Validation README: Evaluation-Driven Development Suite

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch02/README.md](../../../../labs/ch02/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `3.84s`

## Verified commands

- `uv run policyops verify ch02 --profile fixture --junit build/ch02/junit.xml --evidence build/ch02`
- Validation summary: [ch02 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/eval](../../../../src/policyops/eval)
- Test directories: [tests/eval](../../../../tests/eval)
- Evidence artifacts: [junit.xml](../../../../build/ch02/junit.xml), [result.json](../../../../build/ch02/result.json), [scorecard.json](../../../../build/ch02/scorecard.json), [grades.jsonl](../../../../build/ch02/grades.jsonl), [failure_taxonomy.json](../../../../build/ch02/failure_taxonomy.json)

## Coverage map

- Versioned task cases and graders: [src/policyops/eval](../../../../src/policyops/eval), [tests/eval](../../../../tests/eval), [grades.jsonl](../../../../build/ch02/grades.jsonl)
- Failure taxonomy and holdout governance: [src/policyops/eval](../../../../src/policyops/eval), [tests/eval](../../../../tests/eval), [failure_taxonomy.json](../../../../build/ch02/failure_taxonomy.json)
- Release gating and scorecard outputs: [src/policyops/eval](../../../../src/policyops/eval), [tests/eval](../../../../tests/eval), [scorecard.json](../../../../build/ch02/scorecard.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
