# Validation README: Citation-First Hybrid RAG

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch06/README.md](../../../../labs/ch06/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `2.56s`

## Verified commands

- `uv run policyops verify ch06 --profile fixture --junit build/ch06/junit.xml --evidence build/ch06`
- Validation summary: [ch06 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/retrieval](../../../../src/policyops/retrieval)
- Test directories: [tests/retrieval](../../../../tests/retrieval)
- Evidence artifacts: [junit.xml](../../../../build/ch06/junit.xml), [result.json](../../../../build/ch06/result.json), [scorecard.json](../../../../build/ch06/scorecard.json), [evidence_packs.jsonl](../../../../build/ch06/evidence_packs.jsonl), [freshness_receipts.json](../../../../build/ch06/freshness_receipts.json)

## Coverage map

- Hybrid retrieval and reranking: [src/policyops/retrieval](../../../../src/policyops/retrieval), [tests/retrieval](../../../../tests/retrieval), [scorecard.json](../../../../build/ch06/scorecard.json)
- Citation-first evidence pack generation: [src/policyops/retrieval](../../../../src/policyops/retrieval), [tests/retrieval](../../../../tests/retrieval), [evidence_packs.jsonl](../../../../build/ch06/evidence_packs.jsonl)
- Freshness, deletion, and authorization handling: [src/policyops/retrieval](../../../../src/policyops/retrieval), [tests/retrieval](../../../../tests/retrieval), [freshness_receipts.json](../../../../build/ch06/freshness_receipts.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
