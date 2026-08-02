# Validation README: Governance Release Review

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch15/README.md](../../../../labs/ch15/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `3.22s`

## Verified commands

- `uv run policyops verify ch15 --profile fixture --junit build/ch15/junit.xml --evidence build/ch15`
- Validation summary: [ch15 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/governance](../../../../src/policyops/governance)
- Test directories: [tests/governance](../../../../tests/governance)
- Evidence artifacts: [junit.xml](../../../../build/ch15/junit.xml), [result.json](../../../../build/ch15/result.json), [scorecard.json](../../../../build/ch15/scorecard.json), [approval_matrix.json](../../../../build/ch15/approval_matrix.json), [control_evidence_graph.json](../../../../build/ch15/control_evidence_graph.json), [release_decision.json](../../../../build/ch15/release_decision.json)

## Coverage map

- Approval matrix and ownership controls: [src/policyops/governance](../../../../src/policyops/governance), [tests/governance](../../../../tests/governance), [approval_matrix.json](../../../../build/ch15/approval_matrix.json)
- Control-to-evidence linkage: [src/policyops/governance](../../../../src/policyops/governance), [tests/governance](../../../../tests/governance), [control_evidence_graph.json](../../../../build/ch15/control_evidence_graph.json)
- Release decision and governance outcome: [src/policyops/governance](../../../../src/policyops/governance), [tests/governance](../../../../tests/governance), [release_decision.json](../../../../build/ch15/release_decision.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
