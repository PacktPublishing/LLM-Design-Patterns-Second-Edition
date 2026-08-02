# Validation README: Governed Long-Term Memory

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch08/README.md](../../../../labs/ch08/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `3.01s`

## Verified commands

- `uv run policyops verify ch08 --profile fixture --junit build/ch08/junit.xml --evidence build/ch08`
- Validation summary: [ch08 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/memory](../../../../src/policyops/memory)
- Test directories: [tests/memory](../../../../tests/memory)
- Evidence artifacts: [junit.xml](../../../../build/ch08/junit.xml), [result.json](../../../../build/ch08/result.json), [scorecard.json](../../../../build/ch08/scorecard.json), [memory_events.jsonl](../../../../build/ch08/memory_events.jsonl), [memory_views.json](../../../../build/ch08/memory_views.json), [deletion_receipt.json](../../../../build/ch08/deletion_receipt.json)

## Coverage map

- Append-only memory ledger and event model: [src/policyops/memory](../../../../src/policyops/memory), [tests/memory](../../../../tests/memory), [memory_events.jsonl](../../../../build/ch08/memory_events.jsonl)
- Recall views and governed retrieval of memory: [src/policyops/memory](../../../../src/policyops/memory), [tests/memory](../../../../tests/memory), [memory_views.json](../../../../build/ch08/memory_views.json)
- Correction, forgetting, and deletion evidence: [src/policyops/memory](../../../../src/policyops/memory), [tests/memory](../../../../tests/memory), [deletion_receipt.json](../../../../build/ch08/deletion_receipt.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
