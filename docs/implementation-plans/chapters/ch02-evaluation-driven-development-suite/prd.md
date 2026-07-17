# Chapter 2 PRD: Create an Evaluation-Driven Development Suite

**Chapter:** Evaluation-Driven Development for LLM Systems
**Related design:** [Architecture](./architecture.md)
**Input checkpoint:** [Chapter 1 PolicyOps foundation](../ch01-policyops-foundation/prd.md)
**Implementation checkpoint:** `ed2-v1.0-ch02-start` to `work/ch02`

## Product context

Chapter 1 established provider-neutral request, answer, error, and trace contracts. This project defines the task, trial, grader, and outcome contracts that every later chapter will reuse. The suite is intentionally offline: it owns capability measurement, deterministic regression gates, protected holdouts, and fair trial diagnosis, while Chapter 12 will own production telemetry and trace-to-improvement workflows.

The starter includes 20 seed cases, deterministic replay outputs, expert labels, frozen rubric-grader replays, and deliberately broken graders. Readers add at least 10 meaningful cases and repair evaluator defects before drawing conclusions about model behavior.

## Problem statement

LLM teams frequently change prompts, models, data, or infrastructure before defining what success and failure mean. Ad hoc spot checks reward lucky runs, hide authorization regressions, and let broken graders blame the system under test. PolicyOps needs an executable release suite that separates hard capability exploration from near-perfect regression checks, reports stochastic distributions instead of one score, and preserves enough evidence to diagnose task, grader, fixture, and model failures fairly.

## Goals

- Establish versioned task, trial, trace, grader, outcome, and failure-taxonomy schemas.
- Maintain distinct capability, regression, adversarial, and protected-holdout collections.
- Add cases for answer structure, citations, authorization, tool arguments, abstention, and adversarial behavior.
- Track cost per successful outcome as a first-class comparison measure for later adaptation, inference, orchestration, and production-improvement chapters.
- Lead with deterministic graders and calibrate one rubric grader against expert labels.
- Run three trials for designated stochastic cases and report both first-try and repeated consistency metrics.
- Detect grader gaming and noisy-environment failures before judging a model candidate.
- Make schema, citation, authorization, and tool regressions block CI.

## Non-goals

- Instrumenting or sampling production traffic; Chapter 12 owns online observability.
- Comparing adaptation methods or training models; Chapter 3 owns those decisions.
- Building retrieval, tools, memory, or orchestration implementations.
- Making nondeterministic rubric grading a mandatory pull-request dependency.
- Treating aggregate score improvement as sufficient when a mandatory safety gate fails.

## Users

- **AI engineer:** creates cases and compares a candidate against a declared baseline.
- **Evaluator owner:** implements graders, verifies reference solutions, and maintains calibration evidence.
- **Domain expert:** supplies labels and resolves ambiguous requirements.
- **Release reviewer:** inspects gate results, uncertainty, cost, runtime, and failure causes.

## User stories

- As an AI engineer, I can run the same fixture suite locally and in CI and receive identical deterministic results.
- As a domain expert, I can review a compact case and grader explanation without reading framework-specific traces.
- As a release reviewer, I can distinguish a one-run success from repeatable production consistency.
- As an evaluator owner, I can quarantine a disputed case without silently rewriting historical results.

## Functional requirements

- **CH02-FR-001:** Define versioned `TaskCase`, `Trial`, `TraceRef`, `GraderResult`, `Outcome`, and `SuiteManifest` schemas with stable IDs and artifact hashes.
- **CH02-FR-002:** Partition cases into capability, regression, adversarial, and protected-holdout suites, with ownership, rationale, risk, expected outcome, and retirement metadata.
- **CH02-FR-003:** Load the supplied 20 cases and add at least 10 cases spanning answer schema, exact citation validity, tenant/actor authorization, typed tool-argument validation, sufficient-evidence abstention, and adversarial input.
- **CH02-FR-004:** Support deterministic graders for schema, citations, authorization, tool arguments, abstention conditions, and final environment state.
- **CH02-FR-005:** Support a rubric grader adapter with a frozen replay profile for mandatory runs and an optional hosted or local profile for calibration experiments.
- **CH02-FR-006:** Verify reference solutions and grader assertions before a case can become release-blocking.
- **CH02-FR-007:** Run a configurable number of independent trials; require three trials for cases marked stochastic and preserve seed, fixture, configuration, and environment identifiers.
- **CH02-FR-008:** Report pass rate, first-try pass, pass@k, pass^k, score distributions, uncertainty interval, latency, token usage, cost, and cost per successful outcome where meaningful; label unavailable measures explicitly.
- **CH02-FR-009:** Diagnose each failure as candidate, task ambiguity, grader defect, fixture/infrastructure noise, or unresolved; only candidate failures count against a release after adjudication rules are applied.
- **CH02-FR-010:** Detect grader gaming through a supplied candidate that satisfies superficial wording while violating deterministic state or citation checks.
- **CH02-FR-011:** Enforce CI thresholds and mandatory zero-tolerance gates while keeping nondeterministic grading outside required pull-request checks.
- **CH02-FR-012:** Emit a trial report, failure taxonomy, calibration report, and machine-readable evidence index for later chapter comparisons.
- **CH02-FR-013:** Schedule candidate and grader work through independent bounded pools with declared concurrency and request-rate budgets; honor provider throttling with `Retry-After` when present, bounded exponential backoff with jitter, and resumable trial IDs without duplicating evidence or changing release-gate semantics.

## Non-functional requirements

- **CH02-NFR-001:** Mandatory fixture results must be repeatable across two consecutive runs on the same manifest and environment.
- **CH02-NFR-002:** A full mandatory suite must fit ordinary pull-request CI and record runtime; expensive or stochastic extensions run separately.
- **CH02-NFR-003:** Cases, graders, and reports must be framework-neutral and serializable as documented JSON/JSONL.
- **CH02-NFR-004:** Historical result records are immutable; case or grader changes create new versions and hashes.
- **CH02-NFR-005:** One malformed case or grader crash must be isolated and reported without losing completed trial evidence.
- **CH02-NFR-006:** Suite output must be readable by humans and consumable by CI without parsing console prose.

## Security and privacy requirements

- **CH02-SEC-001:** Keep protected holdouts outside candidate-writable paths and expose only hashes and aggregate results during normal development.
- **CH02-SEC-002:** Prevent cases from weakening authorization context or selecting privileged fixture behavior through untrusted fields.
- **CH02-SEC-003:** Use synthetic or licensed fixtures with data-classification metadata; redact sensitive prompts and outputs from routine CI artifacts.
- **CH02-SEC-004:** Treat rubric-grader inputs and outputs as untrusted and validate them before score aggregation.
- **CH02-SEC-005:** Record grader identity and configuration without storing provider credentials or raw secrets.
- **CH02-SEC-006:** Fail the run if a candidate changes cases, graders, thresholds, or holdout hashes outside an explicitly authorized evaluation-maintenance change.

## Fixtures and data

`evals/cases/` contains versioned JSONL records. Each case includes task ID, suite, risk, input, authenticated context reference, expected final state, required evidence, forbidden behavior, graders, trial count, and tolerances. `evals/holdouts/` is read-only in candidate workflows. Expert labels include annotator role, label version, rationale, and adjudication state without unnecessary personal identifiers. Frozen rubric replays permit deterministic CI; live rubric calibration is optional.

The manuscript's human/domain-grader role is realized in this offline lab through versioned expert labels, adjudication, and calibration evidence rather than a blocking runtime human-grader service.

The tool-argument cases use a simulated future capability contract rather than a real Chapter 9 tool. They grade typed arguments and authorization intent only and therefore do not introduce tool execution into this chapter.

## External behavior and CLI

The evaluation runner accepts a suite manifest, candidate profile, baseline, trial policy, and evidence directory. It returns a non-zero exit code when a mandatory gate fails, a protected artifact changes, or the run is invalid. Representative commands are:

```text
uv run policyops eval run --suite regression --profile fixture
uv run policyops eval compare --baseline ch01 --candidate work/ch02
uv run policyops verify ch02 --profile fixture --junit build/ch02/junit.xml --evidence build/ch02
```

Human reports show suite-level gates first, then distributions, adjudicated failure categories, and outcome-cost summaries. Machine output carries schema version, manifest hashes, environment fingerprint, total runtime, grader costs, and cost-per-successful-outcome inputs when available.

## Acceptance criteria and traceability

| Criterion | Verification | Requirements |
|---|---|---|
| Task, trial, trace, grade, outcome, and suite-manifest records round-trip with stable IDs, versions, and artifact hashes. | Schema fixtures, canonical serialization, and invalid-version tests | CH02-FR-001 |
| Cases are assigned to exactly one declared suite class with owner, rationale, risk, expected outcome, and lifecycle metadata; protected holdouts remain separated. | Manifest partition and metadata coverage tests | CH02-FR-002 |
| No case becomes release-blocking until its reference solution succeeds and every declared grader passes integrity checks. | Seeded unsolvable-case and broken-grader admission tests | CH02-FR-006 |
| Deterministic graders produce identical results twice. | Repeated fixture run and canonical result diff | CH02-FR-004, CH02-NFR-001 |
| At least 30 total cases cover all six required risk areas. | Manifest coverage validator | CH02-FR-003 |
| Schema, citation, authorization, and tool regressions block CI. | Seeded failing candidates | CH02-FR-011 |
| Three-trial cases report distributions, pass@k, and pass^k. | Report schema and metric tests | CH02-FR-007, CH02-FR-008 |
| The gaming candidate fails deterministic outcome checks. | Adversarial grader test | CH02-FR-010 |
| A noisy trial is classified and repaired or quarantined before model judgment. | Adjudication workflow test | CH02-FR-009 |
| Rubric calibration records agreement, variance, latency, and cost. | Frozen replay required; live adapter optional | CH02-FR-005, CH02-FR-012 |
| Evaluation cost, runtime, and cost-per-successful-outcome inputs appear in evidence. | Report contract test | CH02-FR-008, CH02-NFR-006 |
| A seeded candidate or grader throttle never causes an unbounded retry storm, duplicated trial, or false release decision. | Deterministic 429/timeout replay, concurrency-bound assertion, interruption/resume test | CH02-FR-013, CH02-NFR-002, CH02-NFR-005 |

## Success metrics

- 100% deterministic repeatability for mandatory graders.
- 100% reference-solution verification before a case becomes release-blocking.
- Zero unauthorized mutation of holdouts, graders, or thresholds in candidate runs.
- Coverage of every declared Chapter 2 risk category with at least one positive and one negative case.
- All stochastic results include trial count and distribution; no single-run score is presented as consistency.
- CI fails on every seeded mandatory regression and passes the unchanged Chapter 1 baseline.

## Dependencies and prerequisites

The project consumes Chapter 1 domain contracts, deterministic adapter, traces, and error taxonomy. It uses Python 3.12+, `uv`, Pydantic, pytest, and optional containers. The core requires no external model or paid credential. Exact versions and fixture hashes are frozen when implementation begins.

Primary paths are `evals/cases`, `evals/graders`, `evals/holdouts`, `tests/evals`, and `.github/workflows/chapter-verify.yml`. The lab manifest is `labs/ch02/manifest.toml`.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Cases reward superficial wording. | Require deterministic schema, evidence, authorization, or environment checks where possible. |
| Holdout leakage inflates results. | Separate permissions, hash verification, contamination tests, and candidate read restrictions. |
| Rubric grader becomes the source of truth. | Calibrate against experts and keep deterministic gates authoritative. |
| Aggregate improvement hides severe regression. | Maintain zero-tolerance risk gates outside the weighted score. |
| Suite becomes too slow for CI. | Split compact regression gates from capability and live-grader jobs. |
| Broken infrastructure is blamed on the candidate. | Preserve trial evidence and require explicit failure classification. |
| Evaluation traffic overloads a model or grader endpoint. | Isolate candidate and grader pools, enforce rate and concurrency budgets, honor retry guidance, and resume stable trial IDs. |

## Delivery milestones

1. Define schemas, suite partitioning, and immutable manifest hashing.
2. Validate seed cases, reference solutions, and deliberately broken graders.
3. Implement deterministic graders and at least 10 new cases.
4. Implement trial execution, stochastic metrics, and failure diagnosis.
5. Add frozen rubric replay, expert calibration, reports, and CI gates.
6. Run gaming and noisy-environment drills; emit evidence and register schemas, holdout hashes, calibration, and CI results in `capstone/traceability.yaml`.

## Lab delivery contract

- **Starter:** `ed2-v1.0-ch02-start` with a supplied 20-case seed suite, replay fixtures, expert labels, and deliberately broken graders.
- **Task/drill:** add at least 10 answer, citation, authorization, tool-argument, abstention, and adversarial cases; run three trials where stochastic; calibrate one rubric grader; then detect one grader-gaming candidate and one noisy-environment trial.
- **Artifacts/acceptance:** versioned JSONL suite, deterministic and rubric graders, expert-label set, trial report, failure taxonomy, outcome-cost summary, and CI gate; deterministic graders repeat exactly, risk regressions block, distributions replace single stochastic scores, and runtime/cost are recorded.
- **Environment/repository:** Python 3.12+, `uv`, optional containers, no paid credential; `labs/ch02/manifest.toml`, `evals/cases`, `evals/graders`, `evals/holdouts`, `tests/evals`, and `.github/workflows/chapter-verify.yml`.
- **Lifecycle:** `uv sync --frozen`; `uv run policyops env up --lab ch02 --profile fixture`; `uv run policyops verify ch02 --profile fixture --junit build/ch02/junit.xml --evidence build/ch02`; `uv run policyops fault ch02 --scenario all`; `uv run policyops env down --lab ch02`.
- **Handoff:** compare `work/ch02` with `ed2-v1.0-ch02-solution` and register task/trial/grader schemas, trace/outcome records, holdout hash, calibration, test command, CI evidence, and rollback in `capstone/traceability.yaml`.

## Future extensions

Chapter 3 will use the suite to compare adaptation strategies. Every later chapter will add focused cases while retaining these contracts. Chapter 12 will ingest adjudicated production failures, correlate telemetry, and manage safe improvement loops; it must not rewrite protected Chapter 2 evidence during candidate optimization.
