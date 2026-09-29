# Validation README: Prompt Injection Defense

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch13/README.md](../../../../labs/ch13/README.md)
- Repo-wide regression check on August 5, 2026: full suite `288 passed` via `uv run pytest tests -q`
- Chapter verification on August 5, 2026: exit code `0`, elapsed `2.50s`

## Verified commands

- `uv run policyops verify ch13 --profile fixture --junit build/ch13/junit.xml --evidence build/ch13`
- Validation summary: [ch13 entry](../../validation-summary.json)

## Implementation links

- Source directories: [src/policyops/security](../../../../src/policyops/security)
- Test directories: [tests/security](../../../../tests/security)
- Evidence artifacts: [junit.xml](../../../../build/ch13/junit.xml), [result.json](../../../../build/ch13/result.json), [scorecard.json](../../../../build/ch13/scorecard.json), [attack_corpus.json](../../../../build/ch13/attack_corpus.json), [security_report.json](../../../../build/ch13/security_report.json), [mcp_authorization.json](../../../../build/ch13/mcp_authorization.json), [sandbox_profile.json](../../../../build/ch13/sandbox_profile.json)

## Coverage map

- Threat modeling and attack coverage: [src/policyops/security](../../../../src/policyops/security), [tests/security](../../../../tests/security), [attack_corpus.json](../../../../build/ch13/attack_corpus.json), [security_report.json](../../../../build/ch13/security_report.json)
- Authorization and capability enforcement: [src/policyops/security](../../../../src/policyops/security), [tests/security](../../../../tests/security), [mcp_authorization.json](../../../../build/ch13/mcp_authorization.json)
- Sandboxing, egress control, and containment: [src/policyops/security](../../../../src/policyops/security), [tests/security](../../../../tests/security), [sandbox_profile.json](../../../../build/ch13/sandbox_profile.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
