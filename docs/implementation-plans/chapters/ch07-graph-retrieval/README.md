# Validation README: Graph Retrieval

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch07/README.md](../../../../labs/ch07/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `3.41s`

## Verified commands

- `uv run policyops verify ch07 --profile fixture --junit build/ch07/junit.xml --evidence build/ch07`
- Validation summary: [ch07 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/graph](../../../../src/policyops/graph)
- Test directories: [tests/graph](../../../../tests/graph)
- Evidence artifacts: [junit.xml](../../../../build/ch07/junit.xml), [result.json](../../../../build/ch07/result.json), [scorecard.json](../../../../build/ch07/scorecard.json), [graph_results.jsonl](../../../../build/ch07/graph_results.jsonl), [repair_receipt.json](../../../../build/ch07/repair_receipt.json), [graph_vs_rag_adr.json](../../../../build/ch07/graph_vs_rag_adr.json)

## Coverage map

- Graph routes for relationship-heavy questions: [src/policyops/graph](../../../../src/policyops/graph), [tests/graph](../../../../tests/graph), [graph_results.jsonl](../../../../build/ch07/graph_results.jsonl)
- Repair and update of graph-backed claims: [src/policyops/graph](../../../../src/policyops/graph), [tests/graph](../../../../tests/graph), [repair_receipt.json](../../../../build/ch07/repair_receipt.json)
- Graph-versus-RAG decision evidence: [src/policyops/graph](../../../../src/policyops/graph), [tests/graph](../../../../tests/graph), [graph_vs_rag_adr.json](../../../../build/ch07/graph_vs_rag_adr.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
