# Validation README: PolicyOps Capstone

## Status

- Validation verdict: READY
- Specs reviewed: [prd.md](prd.md), [architecture.md](architecture.md), [design.md](design.md)
- Chapter lab companion: [labs/ch16/README.md](../../../../labs/ch16/README.md)
- Repo-wide regression check on August 6, 2026: full suite `289 passed, 1 warning` via `uv run pytest -q`
- Chapter verification on August 6, 2026: fixture verifier `208 passed` via `uv run policyops verify ch16 --profile fixture --junit build/ch16/junit.xml --evidence build/ch16`

## Verified commands

- `uv run policyops verify ch16 --profile fixture --all --junit build/ch16/junit.xml --evidence build/ch16`
- `uv run pytest tests/capstone/test_capstone.py -q`
- `uv run pytest -q`

## Implementation links

- Source directories: [src/policyops/capstone](../../../../src/policyops/capstone)
- Test directories: [tests/capstone](../../../../tests/capstone)
- Evidence artifacts: [junit.xml](../../../../build/ch16/junit.xml), [result.json](../../../../build/ch16/result.json), [capstone_scorecard.json](../../../../build/ch16/capstone_scorecard.json), [game_day_results.json](../../../../build/ch16/game_day_results.json), [game_day_measurements.json](../../../../build/ch16/game_day_measurements.json), [seeded_failure_decision.json](../../../../build/ch16/seeded_failure_decision.json), [release_bundle.json](../../../../build/ch16/release_bundle.json)

## Coverage map

- End-to-end game day execution: [src/policyops/capstone](../../../../src/policyops/capstone), [tests/capstone](../../../../tests/capstone), [game_day_results.json](../../../../build/ch16/game_day_results.json), [game_day_measurements.json](../../../../build/ch16/game_day_measurements.json)
- Seeded failure proving NO-GO behavior: [src/policyops/capstone](../../../../src/policyops/capstone), [tests/capstone](../../../../tests/capstone), [seeded_failure_decision.json](../../../../build/ch16/seeded_failure_decision.json)
- Signed release bundle and capstone scorecard: [src/policyops/capstone](../../../../src/policyops/capstone), [tests/capstone](../../../../tests/capstone), [release_bundle.json](../../../../build/ch16/release_bundle.json), [capstone_scorecard.json](../../../../build/ch16/capstone_scorecard.json)

## Notes

- This README records the implementation and test evidence reviewed against the chapter specs. It is code-facing validation, not manuscript content.
