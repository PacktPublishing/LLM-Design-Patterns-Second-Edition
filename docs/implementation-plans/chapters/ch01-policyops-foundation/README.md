# Validation README: PolicyOps Foundation

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch01/README.md](../../../../labs/ch01/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `4.87s`

## Verified commands

- `uv run policyops verify ch01 --profile fixture --junit build/ch01/junit.xml --evidence build/ch01`
- Validation summary: [ch01 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/contracts](../../../../src/policyops/contracts), [src/policyops/adapters](../../../../src/policyops/adapters), [src/policyops/api](../../../../src/policyops/api)
- Test directories: [tests/contract](../../../../tests/contract), [tests/api](../../../../tests/api), [tests/boundary](../../../../tests/boundary), [tests/fault](../../../../tests/fault)
- Evidence artifacts: [junit.xml](../../../../build/ch01/junit.xml), [result.json](../../../../build/ch01/result.json), [scorecard.json](../../../../build/ch01/scorecard.json), [trace_redaction.json](../../../../build/ch01/trace_redaction.json)

## Coverage map

- Typed contracts and request context: [src/policyops/contracts](../../../../src/policyops/contracts), [tests/contract](../../../../tests/contract), [result.json](../../../../build/ch01/result.json)
- Provider-neutral adapters and replay path: [src/policyops/adapters](../../../../src/policyops/adapters), [tests/fault](../../../../tests/fault), [scorecard.json](../../../../build/ch01/scorecard.json)
- FastAPI boundary, identity checks, and redacted traces: [src/policyops/api](../../../../src/policyops/api), [tests/api](../../../../tests/api), [tests/boundary](../../../../tests/boundary), [trace_redaction.json](../../../../build/ch01/trace_redaction.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
