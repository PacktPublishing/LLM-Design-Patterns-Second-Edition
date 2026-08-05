# Validation README: Adaptation Strategy

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch03/README.md](../../../../labs/ch03/README.md)
- Repo-wide regression check on August 5, 2026: full suite `284 passed` via `uv run pytest tests -q`
- Chapter verification on August 5, 2026: chapter gate `22 passed` via `uv run policyops verify ch03 --profile fixture --junit build/ch03/junit.xml --evidence build/ch03`

## Verified commands

- `uv run policyops verify ch03 --profile fixture --junit build/ch03/junit.xml --evidence build/ch03`
- `uv run policyops fault ch03 --scenario all`
- Validation summary: [ch03 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/adaptation](../../../../src/policyops/adaptation)
- Test directories: [tests/adaptation](../../../../tests/adaptation)
- Evidence artifacts: [junit.xml](../../../../build/ch03/junit.xml), [adaptation_scorecard.json](../../../../build/ch03/adaptation_scorecard.json), [candidate_reports.json](../../../../build/ch03/candidate_reports.json), [comparison_report.json](../../../../build/ch03/comparison_report.json), [adaptation_report.json](../../../../build/ch03/adaptation_report.json), [safety_drill_report.json](../../../../build/ch03/safety_drill_report.json), [drill contamination report](../../../../build/ch03/drill_contamination/adaptation_report.json)

## Coverage map

- Baseline comparison and candidate scoring: [src/policyops/adaptation](../../../../src/policyops/adaptation), [tests/adaptation](../../../../tests/adaptation), [candidate_reports.json](../../../../build/ch03/candidate_reports.json), [adaptation_report.json](../../../../build/ch03/adaptation_report.json)
- Data rights, provenance, and contamination checks: [src/policyops/adaptation](../../../../src/policyops/adaptation), [tests/adaptation](../../../../tests/adaptation), [drill contamination report](../../../../build/ch03/drill_contamination/adaptation_report.json)
- Adaptation decision record and release judgment: [src/policyops/adaptation](../../../../src/policyops/adaptation), [tests/adaptation](../../../../tests/adaptation), [adaptation_scorecard.json](../../../../build/ch03/adaptation_scorecard.json), [comparison_report.json](../../../../build/ch03/comparison_report.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
