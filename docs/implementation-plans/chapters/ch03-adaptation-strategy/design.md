# Chapter 3 Design: Adaptation Strategy Decision Pipeline

**Sources:** [PRD](./prd.md) · [Architecture](./architecture.md)
**Upstream:** Chapter 2 evaluation suite
**Status:** Implemented and fixture-verified (`policyops verify ch03` passed)
**Profile:** `fixture` (no GPU; supplied adapter checksum only)

## Design summary

Offline manifest-driven pipeline: intake records with provenance/rights → deterministic splits → contamination checks → evaluate baseline / prompt / retrieval-replay / supplied adapter via Chapter 2 contracts → apply predeclared gates → emit ship/no-ship `ReleaseDecision` with rollback target.

## Design review findings

| ID | Finding | Severity | Resolution |
|---|---|---|---|
| DR-01 | Training on protected eval data | High | Entity-key splits + exact/normalized/near-dup contamination blockers |
| DR-02 | Average score overrides safety | High | Zero-tolerance gates cannot be outweighed by quality deltas |
| DR-03 | Adapter without hash/license | High | Artifact admission fails closed before eval |
| DR-04 | Peeking at protected test then changing candidate | High | Experiment version bump required; thresholds locked in manifest |
| DR-05 | “No adaptation” not treated as success | Medium | Baseline can win; decision explicitly records `selected=baseline` |

## Module layout

```text
src/policyops/adaptation/
  schemas.py
  intake.py
  splits.py
  contamination.py
  admission.py
  decision.py
  pipeline.py
labs/ch03/
evals/adaptation/
tests/adaptation/
```

## Verification

`uv run policyops verify ch03 --profile fixture` runs contamination drills, admission checks, and a deterministic decision producing evidence under `build/ch03/`.
