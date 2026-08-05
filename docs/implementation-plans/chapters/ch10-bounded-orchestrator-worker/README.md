# Validation README: Bounded Orchestrator-Worker

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch10/README.md](../../../../labs/ch10/README.md)
- Repo-wide regression check on August 5, 2026: full suite `286 passed` via `uv run pytest tests -q`
- Chapter verification on August 5, 2026: chapter gate `127 passed` via `uv run policyops verify ch10 --profile fixture --junit build/ch10/junit.xml --evidence build/ch10`

## Verified commands

- `uv run policyops verify ch10 --profile fixture --junit build/ch10/junit.xml --evidence build/ch10`
- `uv run pytest tests/orchestration/test_bounded_orchestration.py -q`
- Validation summary: [ch10 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/orchestration](../../../../src/policyops/orchestration)
- Test directories: [tests/orchestration](../../../../tests/orchestration)
- Evidence artifacts: [junit.xml](../../../../build/ch10/junit.xml), [result.json](../../../../build/ch10/result.json), [orchestration_scorecard.json](../../../../build/ch10/orchestration_scorecard.json), [state_graph_runs.json](../../../../build/ch10/state_graph_runs.json), [delegation_contract.json](../../../../build/ch10/delegation_contract.json), [topology_comparison.json](../../../../build/ch10/topology_comparison.json), [budget_ledger.json](../../../../build/ch10/budget_ledger.json)

## Coverage map

- Explicit state graph and stage routing: [src/policyops/orchestration](../../../../src/policyops/orchestration), [tests/orchestration](../../../../tests/orchestration), [state_graph_runs.json](../../../../build/ch10/state_graph_runs.json)
- Delegation boundaries and worker contracts: [src/policyops/orchestration](../../../../src/policyops/orchestration), [tests/orchestration](../../../../tests/orchestration), [delegation_contract.json](../../../../build/ch10/delegation_contract.json), [budget_ledger.json](../../../../build/ch10/budget_ledger.json)
- Topology comparison and orchestration evidence: [src/policyops/orchestration](../../../../src/policyops/orchestration), [tests/orchestration](../../../../tests/orchestration), [topology_comparison.json](../../../../build/ch10/topology_comparison.json), [orchestration_scorecard.json](../../../../build/ch10/orchestration_scorecard.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
