# Validation README: Trace to Safe Improvement

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch12/README.md](../../../../labs/ch12/README.md)
- Repo-wide regression check on August 5, 2026: full suite `287 passed` via `uv run pytest tests -q`
- Chapter verification on August 5, 2026: exit code `0`, elapsed `2.37s`

## Verified commands

- `uv run policyops verify ch12 --profile fixture --junit build/ch12/junit.xml --evidence build/ch12`
- Validation summary: [ch12 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/telemetry](../../../../src/policyops/telemetry)
- Test directories: [tests/telemetry](../../../../tests/telemetry)
- Evidence artifacts: [junit.xml](../../../../build/ch12/junit.xml), [result.json](../../../../build/ch12/result.json), [scorecard.json](../../../../build/ch12/scorecard.json), [experiment_ledger.json](../../../../build/ch12/experiment_ledger.json), [experiment_trial_report.json](../../../../build/ch12/experiment_trial_report.json), [accepted_candidate_ledger.json](../../../../build/ch12/accepted_candidate_ledger.json), [accepted_candidate_trial_report.json](../../../../build/ch12/accepted_candidate_trial_report.json), [canary_report.json](../../../../build/ch12/canary_report.json), [canary_trial_report.json](../../../../build/ch12/canary_trial_report.json), [eval_case_from_trace.json](../../../../build/ch12/eval_case_from_trace.json), [adjudication.json](../../../../build/ch12/adjudication.json)

## Coverage map

- Structured traces and behavior manifests: [src/policyops/telemetry](../../../../src/policyops/telemetry), [tests/telemetry](../../../../tests/telemetry), [result.json](../../../../build/ch12/result.json)
- Experiment protection, keep-or-revert evidence, and cost-per-success metrics: [src/policyops/telemetry](../../../../src/policyops/telemetry), [tests/telemetry](../../../../tests/telemetry), [experiment_ledger.json](../../../../build/ch12/experiment_ledger.json), [experiment_trial_report.json](../../../../build/ch12/experiment_trial_report.json), [accepted_candidate_ledger.json](../../../../build/ch12/accepted_candidate_ledger.json), [accepted_candidate_trial_report.json](../../../../build/ch12/accepted_candidate_trial_report.json)
- Canary comparison and rollback signals: [src/policyops/telemetry](../../../../src/policyops/telemetry), [tests/telemetry](../../../../tests/telemetry), [canary_report.json](../../../../build/ch12/canary_report.json), [canary_trial_report.json](../../../../build/ch12/canary_trial_report.json)
- Trace-to-eval graduation and adjudication flow: [src/policyops/telemetry](../../../../src/policyops/telemetry), [tests/telemetry](../../../../tests/telemetry), [eval_case_from_trace.json](../../../../build/ch12/eval_case_from_trace.json), [adjudication.json](../../../../build/ch12/adjudication.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
