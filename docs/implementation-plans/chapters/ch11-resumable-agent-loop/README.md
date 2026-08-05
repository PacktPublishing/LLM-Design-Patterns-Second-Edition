# Validation README: Resumable Agent Loop

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch11/README.md](../../../../labs/ch11/README.md)
- Repo-wide regression check on August 5, 2026: full suite `287 passed` via `uv run pytest tests -q`
- Chapter verification on August 5, 2026: exit code `0`, elapsed `2.80s`

## Verified commands

- `uv run policyops verify ch11 --profile fixture --junit build/ch11/junit.xml --evidence build/ch11`
- Validation summary: [ch11 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/harness](../../../../src/policyops/harness)
- Test directories: [tests/harness](../../../../tests/harness)
- Evidence artifacts: [junit.xml](../../../../build/ch11/junit.xml), [result.json](../../../../build/ch11/result.json), [scorecard.json](../../../../build/ch11/scorecard.json), [harness_scorecard.json](../../../../build/ch11/harness_scorecard.json), [fault_results.json](../../../../build/ch11/fault_results.json), [replay_result.json](../../../../build/ch11/replay_result.json), [review_bundle.json](../../../../build/ch11/review_bundle.json), [runbook.json](../../../../build/ch11/runbook.json)

## Coverage map

- Session state, checkpoints, and crash recovery: [src/policyops/harness](../../../../src/policyops/harness), [tests/harness](../../../../tests/harness), [fault_results.json](../../../../build/ch11/fault_results.json), [replay_result.json](../../../../build/ch11/replay_result.json)
- Review bundles and post-run evidence: [src/policyops/harness](../../../../src/policyops/harness), [tests/harness](../../../../tests/harness), [review_bundle.json](../../../../build/ch11/review_bundle.json)
- Operational recovery procedure and runbook: [src/policyops/harness](../../../../src/policyops/harness), [tests/harness](../../../../tests/harness), [harness_scorecard.json](../../../../build/ch11/harness_scorecard.json), [runbook.json](../../../../build/ch11/runbook.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
