# Validation README: Bounded Orchestrator-Worker

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch10/README.md](../../../../labs/ch10/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `2.85s`

## Verified commands

- `uv run policyops verify ch10 --profile fixture --junit build/ch10/junit.xml --evidence build/ch10`
- Validation summary: [ch10 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/orchestration](../../../../src/policyops/orchestration)
- Test directories: [tests/orchestration](../../../../tests/orchestration)
- Evidence artifacts: [junit.xml](../../../../build/ch10/junit.xml), [result.json](../../../../build/ch10/result.json), [scorecard.json](../../../../build/ch10/scorecard.json), [state_graph_runs.json](../../../../build/ch10/state_graph_runs.json), [delegation_contract.json](../../../../build/ch10/delegation_contract.json), [topology_comparison.json](../../../../build/ch10/topology_comparison.json)

## Coverage map

- Explicit state graph and stage routing: [src/policyops/orchestration](../../../../src/policyops/orchestration), [tests/orchestration](../../../../tests/orchestration), [state_graph_runs.json](../../../../build/ch10/state_graph_runs.json)
- Delegation boundaries and worker contracts: [src/policyops/orchestration](../../../../src/policyops/orchestration), [tests/orchestration](../../../../tests/orchestration), [delegation_contract.json](../../../../build/ch10/delegation_contract.json)
- Topology comparison and orchestration evidence: [src/policyops/orchestration](../../../../src/policyops/orchestration), [tests/orchestration](../../../../tests/orchestration), [topology_comparison.json](../../../../build/ch10/topology_comparison.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
