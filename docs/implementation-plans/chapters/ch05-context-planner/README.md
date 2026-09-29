# Validation README: Context Planner

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch05/README.md](../../../../labs/ch05/README.md)
- Repo-wide regression check on August 2, 2026: full suite `213 passed` via `uv run pytest tests -q`
- Chapter verification on August 2, 2026: exit code `0`, elapsed `2.49s`

## Verified commands

- `uv run policyops verify ch05 --profile fixture --junit build/ch05/junit.xml --evidence build/ch05`
- Validation summary: [ch05 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/context](../../../../src/policyops/context)
- Test directories: [tests/context](../../../../tests/context)
- Evidence artifacts: [junit.xml](../../../../build/ch05/junit.xml), [result.json](../../../../build/ch05/result.json), [scorecard.json](../../../../build/ch05/scorecard.json), [context_manifest.json](../../../../build/ch05/context_manifest.json), [token_report.json](../../../../build/ch05/token_report.json), [rendered_context.txt](../../../../build/ch05/rendered_context.txt)

## Coverage map

- Authority-ranked context selection and manifests: [src/policyops/context](../../../../src/policyops/context), [tests/context](../../../../tests/context), [context_manifest.json](../../../../build/ch05/context_manifest.json)
- Budget enforcement and rendered context output: [src/policyops/context](../../../../src/policyops/context), [tests/context](../../../../tests/context), [token_report.json](../../../../build/ch05/token_report.json), [rendered_context.txt](../../../../build/ch05/rendered_context.txt)
- Conflict, stale-source, and unauthorized-context handling: [src/policyops/context](../../../../src/policyops/context), [tests/context](../../../../tests/context), [scorecard.json](../../../../build/ch05/scorecard.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
