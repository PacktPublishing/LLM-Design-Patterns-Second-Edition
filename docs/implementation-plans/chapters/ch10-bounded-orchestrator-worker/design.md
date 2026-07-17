# Chapter 10 Design: Bounded Orchestration Lab

This implementation keeps the orchestration pattern framework-neutral. It does not ask readers to learn a specific agent framework before they understand the state, delegation, merge, browser, approval, and evaluation boundaries that make orchestration safe.

## Reader-facing flow

1. Start one PolicyOps triage run with a selected topology.
2. Load a canonical `TaskState` and run-local budget.
3. Execute deterministic, single-agent, browser/computer-use, or worker fan-out behavior.
4. Validate every model, browser, or worker output as untrusted typed data.
5. Merge worker findings deterministically.
6. Preserve pause, resume, cancel, and review states for Chapter 11.
7. Send final ticket creation through the Chapter 9 secured ToolPort.
8. Compare topology results and accept the least complex option that clears the declared threshold.

## Files

| Area | Path |
|---|---|
| Schemas | `src/policyops/orchestration/schemas.py` |
| Runtime and verifier | `src/policyops/orchestration/service.py` |
| Public API | `src/policyops/orchestration/__init__.py` |
| Tests | `tests/orchestration/test_bounded_orchestration.py` |
| Lab guide | `labs/ch10/README.md` |
| Lab manifest | `labs/ch10/manifest.toml` |

## Key design decisions

- Keep the state graph outside topology adapters.
- Use in-process signed delegation before adding any optional independent runtime.
- Treat browser DOM/screen observations as untrusted fixture data.
- Reserve full fan-out capacity before spawning workers.
- Prefer a no-use A2A ADR unless the fixture demonstrates a real ownership, trust, deployment, or interoperability boundary.

## Verification coverage

The Chapter 10 verifier covers:

- deterministic agreement across variants;
- zero model calls for known-rule workflow/browser/worker paths;
- Chapter 9 approval and idempotency on final mutation;
- signed, narrow, traceable delegation;
- replayed, expired, widened, and malformed delegation rejection;
- deterministic merge and collision detection;
- browser profile mismatch containment;
- no partial worker spawn on insufficient capacity;
- pause, resume, and cancel transition snapshots;
- topology comparison and A2A no-use ADR evidence.
