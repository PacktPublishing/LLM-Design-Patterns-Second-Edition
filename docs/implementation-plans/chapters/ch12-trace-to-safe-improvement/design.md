# Chapter 12 Design: Trace-to-Safe-Improvement Lab

This implementation turns a deterministic production trace into bounded improvement evidence. It keeps the mandatory path local and fixture-based while preserving the production semantics readers need: semantic telemetry, pre-export minimization, artifact lineage, expert adjudication, protected evaluation graduation, immutable experiments, cost-per-successful-outcome reporting, behavior canary rollback, and non-executing reconstruction.

## Reader-facing flow

1. Register the behavior-affecting artifacts used by the fixture run.
2. Normalize provider/framework events into a stable semantic span schema.
3. Apply tenant hashing, field allowlists, redaction, sampling, and cardinality limits before export.
4. Correlate request, model, retrieval, memory, agent, browser/computer-use, approval, tool, sandbox, external-effect, and outcome spans under one correlation ID.
5. Have a domain expert adjudicate a redacted failure trace.
6. Graduate only the reviewed product failure into a versioned evaluation case.
7. Run a bounded experiment over one writable configuration surface with protected holdout and grader hashes.
8. Reject an overfit candidate, report cost per successful outcome, and roll back a seeded bad behavior canary.
9. Reconstruct the incident with rejecting adapters that prove no model, tool, or external effect was invoked.

## Files

| Area | Path |
|---|---|
| Schemas | `src/policyops/telemetry/schemas.py` |
| Runtime and verifier | `src/policyops/telemetry/service.py` |
| Public API | `src/policyops/telemetry/__init__.py` |
| Tests | `tests/telemetry/test_telemetry.py` |
| Lab guide | `labs/ch12/README.md` |
| Lab manifest | `labs/ch12/manifest.toml` |

## Key design decisions

- Keep a small internal semantic schema behind OpenTelemetry-compatible vocabulary.
- Treat the deterministic file exporter as CI truth; dashboards are optional reader extensions.
- Redact and drop fields before data crosses the application telemetry boundary.
- Require human adjudication before a trace can redefine evaluation behavior.
- Allow one writable prompt or routing surface per experiment.
- Mount graders, holdouts, safety cases, and evidence as hash-protected read-only assets.
- Separate behavior canaries from Chapter 14 deployment canaries.
- Use non-executing reconstruction with rejecting model, tool, and effect adapters.

## Verification coverage

The Chapter 12 verifier covers:

- artifact registry digests for all behavior-affecting components;
- full correlation coverage across all required span kinds;
- PII, secret, raw prompt, and high-cardinality field protection;
- tenant pseudonymization and required sampling for approval/effect evidence;
- expert-only trace-to-evaluation graduation;
- protected-hash experiment execution and overfit rejection;
- cost-per-successful-outcome reporting;
- seeded behavior-canary rollback;
- backend outage non-blocking behavior;
- no-effect reconstruction;
- harness-retirement ADR evidence.
