# Validation README: PolicyOps Deployment and Recovery

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch14/README.md](../../../../labs/ch14/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `3.04s`

## Verified commands

- `uv run policyops verify ch14 --profile fixture --junit build/ch14/junit.xml --evidence build/ch14`
- Validation summary: [ch14 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/deployment](../../../../src/policyops/deployment)
- Test directories: [tests/deployment](../../../../tests/deployment)
- Evidence artifacts: [junit.xml](../../../../build/ch14/junit.xml), [result.json](../../../../build/ch14/result.json), [scorecard.json](../../../../build/ch14/scorecard.json), [health_reports.json](../../../../build/ch14/health_reports.json), [load_report.json](../../../../build/ch14/load_report.json), [chaos_results.json](../../../../build/ch14/chaos_results.json)

## Coverage map

- Deployment topology and health handling: [src/policyops/deployment](../../../../src/policyops/deployment), [tests/deployment](../../../../tests/deployment), [health_reports.json](../../../../build/ch14/health_reports.json)
- Load, queue, and overload behavior: [src/policyops/deployment](../../../../src/policyops/deployment), [tests/deployment](../../../../tests/deployment), [load_report.json](../../../../build/ch14/load_report.json)
- Recovery, rollback, and chaos validation: [src/policyops/deployment](../../../../src/policyops/deployment), [tests/deployment](../../../../tests/deployment), [chaos_results.json](../../../../build/ch14/chaos_results.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
