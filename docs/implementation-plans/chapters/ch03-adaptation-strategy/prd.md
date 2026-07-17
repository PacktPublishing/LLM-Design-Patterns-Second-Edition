# Chapter 3 PRD: Choose the Right Adaptation Strategy

**Chapter:** Data and Model Adaptation Patterns
**Related design:** [Architecture](./architecture.md)
**Input checkpoint:** [Chapter 2 evaluation suite](../ch02-evaluation-driven-development-suite/prd.md)
**Implementation checkpoint:** `ed2-v1.0-ch03-start` to `work/ch03`

## Product context

PolicyOps now has a stable service boundary and an offline release suite. This project uses that evidence to decide whether prompting, a supplied retrieval replay, or a supplied lightweight adapter is justified. The correct outcome may be to retain the simplest baseline. The required path evaluates existing artifacts and therefore needs no GPU; retraining the adapter from the same manifest is an optional extension.

This chapter owns data quality, rights and provenance, protected split integrity, adaptation-specific lineage, regression analysis, and the release/no-release decision. It does not build the production retrieval system from Chapter 6 or the serving gateway from Chapter 4.

## Problem statement

Teams often fine-tune before measuring a baseline, mix evaluation examples into training data, lose source rights, or ship a checkpoint because its average quality improved despite safety or subgroup regressions. PolicyOps needs a small reproducible adaptation experiment that traces each record and artifact, detects contamination, compares interventions against predeclared gates, and records a defensible decision including “no adaptation.”

## Goals

- Build a small real-plus-synthetic classification dataset with provenance, rights, sensitivity, ownership, and deletion metadata.
- Create protected train, validation, and test splits and prove zero protected-split overlap.
- Detect exact, normalized, and near-duplicate contamination.
- Establish the unchanged Chapter 2 baseline before evaluating interventions.
- Compare prompt-only, supplied retrieval-replay, and supplied adapter candidates under one evaluation contract.
- Verify checkpoint hash, declared license, base-model identity, and compatibility.
- Gate release on quality, safety, subgroup behavior, calibration, latency, cost, and rollback readiness.
- Emit data/model cards, manifests, reports, and an explicit ship/no-ship decision.

## Non-goals

- Building an ingestion, index, reranker, or citation service; the retrieval candidate is a supplied deterministic replay.
- Training a foundation model or requiring accelerator hardware.
- Optimizing online routing, batching, quantization, or provider failover.
- Claiming that a small lab dataset demonstrates broad fairness or real-world safety.
- Choosing an intervention after seeing protected-test results without recording a new experiment version.
- Implementing preference/outcome optimization or a broad multi-model selection scorecard in the core lab; those patterns are discussed in the chapter, while the hands-on comparison is limited to baseline, prompt, retrieval replay, and the supplied lightweight adapter.

## Users

- **ML engineer:** prepares data, runs candidates, and optionally retrains the adapter.
- **AI engineer:** compares interventions through the Chapter 2 suite.
- **Data steward:** verifies provenance, rights, sensitivity, retention, and deletion obligations.
- **Release reviewer:** applies predeclared gates and approves either adaptation or no adaptation.

## User stories

- As a data steward, I can trace every record to a source and rights basis or exclude it automatically.
- As an ML engineer, I can reproduce a supplied checkpoint evaluation from a locked manifest without a GPU.
- As a release reviewer, I can see why a higher average score still failed a safety, subgroup, latency, or cost gate.
- As an operator, I can identify the base model, adapter, rollback target, and configuration hashes for any candidate result.

## Functional requirements

- **CH03-FR-001:** Define versioned `DataRecord`, `DatasetManifest`, `SplitManifest`, `AdaptationCandidate`, `ModelArtifact`, `ExperimentRun`, and `ReleaseDecision` schemas.
- **CH03-FR-002:** Require each record to include source reference, provenance chain, rights/license basis, consent where relevant, sensitivity, owner, creation time, retention/deletion metadata, and content hash.
- **CH03-FR-003:** Build a small mixture of reviewed real fixtures and synthetic candidates; retain generator configuration, filters, review status, and parent references for synthetic records.
- **CH03-FR-004:** Create deterministic train, validation, and protected-test splits by stable entity/group keys rather than random row assignment alone.
- **CH03-FR-005:** Run exact-hash, normalized-text, and near-duplicate contamination checks across training data, Chapter 2 cases, and protected test data; block the experiment on prohibited overlap.
- **CH03-FR-006:** Run the Chapter 2 baseline unchanged and persist its candidate, suite, fixture, grader, and environment hashes.
- **CH03-FR-007:** Evaluate prompt-only, supplied retrieval-replay, and supplied adapter candidates through the same task, trial, grader, and outcome contracts.
- **CH03-FR-008:** Verify the supplied adapter's cryptographic hash, declared license, base-model compatibility, architecture metadata, and loading behavior before evaluation.
- **CH03-FR-009:** Calculate candidate deltas for mandatory quality, safety, subgroup, calibration, latency, token, and cost measures without allowing weighted averages to override zero-tolerance gates.
- **CH03-FR-010:** Produce a release decision that names the selected candidate or baseline, gate evidence, approver role, rollback target, residual risks, and expiration/review condition.
- **CH03-FR-011:** Support an optional training command that uses the same dataset and training manifest, records declared GPU hardware, and produces a separately hashed checkpoint.
- **CH03-FR-012:** Run drills that inject a duplicate protected example and a safety regression and prove each blocks release.

## Non-functional requirements

- **CH03-NFR-001:** The core comparison must complete without GPU, hosted model, or paid credential.
- **CH03-NFR-002:** Re-running a manifest with the same immutable inputs must reproduce split membership, contamination results, candidate configuration, and deterministic fixture scores.
- **CH03-NFR-003:** Artifacts must be content-addressed and reports must retain all input hashes and environment details needed for audit.
- **CH03-NFR-004:** Data validation errors identify record IDs and rule codes without exposing sensitive content in ordinary logs.
- **CH03-NFR-005:** Candidate adapters share one inference/evaluation interface and cannot customize graders or thresholds.
- **CH03-NFR-006:** The core lab must remain implementable in 3–4 hours; optional retraining is isolated to an additional declared 3–6 hour path.

## Security and privacy requirements

- **CH03-SEC-001:** Exclude records lacking a supported rights basis, provenance, or required consent.
- **CH03-SEC-002:** Keep protected splits read-only during candidate development and verify hashes before and after runs.
- **CH03-SEC-003:** Prevent synthetic generation or preprocessing from copying secrets or personal data into derived artifacts.
- **CH03-SEC-004:** Validate checkpoint type, size, hash, source, license, and loading policy; do not execute arbitrary code from an untrusted model artifact.
- **CH03-SEC-005:** Ensure candidates cannot alter Chapter 2 cases, graders, thresholds, or protected data.
- **CH03-SEC-006:** Define deletion lineage so a source deletion request identifies derived dataset versions and future retraining obligations.

## Fixtures and data

The starter supplies reviewed candidate records, a protected split, deterministic retrieval outputs, baseline responses, and a checksummed lightweight adapter. The project creates a compact classification dataset representative of PolicyOps routing or policy-topic categorization, not the later answer-generation corpus. At least two declared subgroups are present solely to demonstrate disaggregated reporting. Synthetic examples are clearly marked and never presented as real user data.

Dataset and training manifests record inputs, transforms, seed, code revision, library lock hash, output hashes, and declared hardware. Data and model cards summarize intended use, prohibited use, known limitations, rights, safety results, and rollback.

## External behavior and CLI

The workflow exposes manifest-oriented commands:

```text
uv run policyops data validate data/manifests/ch03-dataset.yaml
uv run policyops adaptation contamination --manifest data/manifests/ch03-dataset.yaml
uv run policyops adaptation compare --suite regression --profile fixture
uv run policyops verify ch03 --profile fixture --junit build/ch03/junit.xml --evidence build/ch03
```

The optional training command is disabled unless a separate GPU profile and hardware declaration are supplied. `compare` outputs a candidate matrix and does not mutate the active Chapter 1 model configuration. `decide` or the verifier produces an immutable recommendation; applying it to production is outside scope.

## Acceptance criteria and traceability

| Criterion | Verification | Requirements |
|---|---|---|
| Data, dataset, split, candidate, artifact, run, and decision records round-trip and reject missing versions, hashes, or lineage fields. | Schema contract and invalid-manifest tests | CH03-FR-001 |
| Every synthetic record retains generator configuration, parent references, filter results, and human review status. | Synthetic-lineage manifest coverage test | CH03-FR-003 |
| The optional trainer consumes the locked manifest, requires a declared GPU profile, and publishes a new independently hashed candidate. | Training dry-run/config rejection and artifact-identity tests | CH03-FR-011 |
| Dataset and split manifests reproduce with zero protected overlap. | Two-run hash check and split validator | CH03-FR-004, CH03-FR-005, CH03-NFR-002 |
| Every record has required provenance and rights metadata. | Schema and policy validation | CH03-FR-002, CH03-SEC-001 |
| Supplied checkpoint hash, license, and compatibility verify. | Artifact admission tests | CH03-FR-008, CH03-SEC-004 |
| Prompt, retrieval replay, adapter, and baseline use one suite and interface. | Candidate contract and manifest comparison | CH03-FR-006, CH03-FR-007, CH03-NFR-005 |
| A seeded duplicate stops the experiment before scoring. | Contamination drill | CH03-FR-005, CH03-FR-012 |
| A seeded safety regression blocks release despite average gain. | Gate-policy drill | CH03-FR-009, CH03-FR-012 |
| Candidate ships only when all declared gates pass; otherwise baseline/no adaptation is recorded. | Release-decision schema and policy test | CH03-FR-010 |
| Core workflow runs without accelerator or paid service. | Clean fixture-profile CI | CH03-NFR-001 |

## Success metrics

- 100% records pass provenance and rights validation; invalid records are excluded with reason codes.
- Zero prohibited overlap between training, Chapter 2 release cases, and protected test data.
- 100% candidate results bind model/data/configuration/suite hashes and rollback target.
- Every mandatory gate has a predeclared threshold and explicit pass/fail evidence.
- The decision is reproducible from the evidence pack and may validly select no adaptation.
- Seeded contamination and safety failures produce non-zero verification status.

## Dependencies and prerequisites

The project requires the Chapter 2 suite, supplied candidate records, protected split, replay fixtures, and checksummed adapter. It uses Python 3.12+, `uv`, Pydantic, pytest, and adapter/evaluation contracts from Chapters 1–2. No PostgreSQL or Redis is needed. Primary paths are `src/policyops/adaptation`, `data/manifests`, `models/cards`, `tests/adaptation`, and `docs/adrs`.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Small sample leads to exaggerated conclusions. | Report uncertainty and limitations; frame the lab as decision mechanics, not universal model ranking. |
| Synthetic data overwhelms real distribution. | Track origin, cap mixture ratios, and report results by source type. |
| Near-duplicate detector misses semantic leakage. | Combine exact, normalized, and similarity checks with protected entity/group splits. |
| Adapter artifact executes unsafe code. | Use approved serialization/loading, hash and type checks, and isolated loading tests. |
| Team moves gates after seeing results. | Bind thresholds into the experiment manifest and version any exception. |
| “No adaptation” appears like project failure. | Make it a first-class valid decision with documented evidence and rollback simplicity. |

## Delivery milestones

1. Define schemas, source policies, and deterministic split strategy.
2. Curate real-plus-synthetic records and create data/split manifests.
3. Implement contamination and artifact-admission checks.
4. Run and lock the Chapter 2 baseline.
5. Evaluate prompt, retrieval-replay, and adapter candidates; produce cards and disaggregated reports.
6. Run contamination and safety drills, issue the release decision, and register lineage, reports, rollback target, and command evidence in `capstone/traceability.yaml`.

## Lab delivery contract

- **Starter:** `ed2-v1.0-ch03-start` with a protected split, supplied checksummed adapter checkpoint, candidate records, and optional GPU extension.
- **Task/drill:** build provenance-tracked real-plus-synthetic data, run exact/normalized/similarity contamination checks, establish the Chapter 2 baseline, compare prompting/retrieval replay/supplied adapter, then seed a duplicate evaluation item and safety regression that must block release.
- **Artifacts/acceptance:** dataset/model cards, source/split/training manifests, rights metadata, contamination and safety reports, artifact hash/license verification, subgroup/quality/latency/cost gates, and a rollback or evidence-backed no-adaptation decision.
- **Environment/repository:** Python 3.12+, `uv`, no GPU in core and no paid credential; `labs/ch03/manifest.toml`, `src/policyops/adaptation`, `data/manifests`, `models/cards`, `tests/adaptation`, and `docs/adrs`.
- **Lifecycle:** `uv sync --frozen`; `uv run policyops env up --lab ch03 --profile fixture`; `uv run policyops verify ch03 --profile fixture --junit build/ch03/junit.xml --evidence build/ch03`; `uv run policyops fault ch03 --scenario all`; `uv run policyops env down --lab ch03`.
- **Handoff:** compare `work/ch03` with `ed2-v1.0-ch03-solution` and register lineage, contamination/safety evidence, adaptation decision, test command, selected profile, and rollback target in `capstone/traceability.yaml`.

## Future extensions

Optionally retrain the adapter on declared hardware using the same manifest, then treat it as a new candidate rather than replacing supplied evidence. Chapter 4 will evaluate the selected profile under inference budgets. Chapter 6 may implement retrieval if this decision identifies it as the smallest justified intervention. Chapter 12 will place all resulting artifacts in the system-wide registry.
