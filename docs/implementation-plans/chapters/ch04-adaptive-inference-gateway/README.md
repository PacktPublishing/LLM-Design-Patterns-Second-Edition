# Validation README: Adaptive Inference Gateway

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch04/README.md](../../../../labs/ch04/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `2.29s`

## Verified commands

- `uv run policyops verify ch04 --profile fixture --junit build/ch04/junit.xml --evidence build/ch04`
- Validation summary: [ch04 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/inference](../../../../src/policyops/inference)
- Test directories: [tests/inference](../../../../tests/inference)
- Evidence artifacts: [junit.xml](../../../../build/ch04/junit.xml), [result.json](../../../../build/ch04/result.json), [scorecard.json](../../../../build/ch04/scorecard.json), [inference_report.json](../../../../build/ch04/inference_report.json), [benchmark_rows.jsonl](../../../../build/ch04/benchmark_rows.jsonl), [serving_adr.json](../../../../build/ch04/serving_adr.json)

## Coverage map

- Routing profiles, budgets, and verifier flow: [src/policyops/inference](../../../../src/policyops/inference), [tests/inference](../../../../tests/inference), [inference_report.json](../../../../build/ch04/inference_report.json)
- Benchmarking the quality-latency-cost frontier: [src/policyops/inference](../../../../src/policyops/inference), [tests/inference](../../../../tests/inference), [benchmark_rows.jsonl](../../../../build/ch04/benchmark_rows.jsonl)
- Serving decision and architecture record: [src/policyops/inference](../../../../src/policyops/inference), [tests/inference](../../../../tests/inference), [serving_adr.json](../../../../build/ch04/serving_adr.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
