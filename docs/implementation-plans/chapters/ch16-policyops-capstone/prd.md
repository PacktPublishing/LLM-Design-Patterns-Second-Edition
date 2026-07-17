# Capstone PRD: Integrate and Release the PolicyOps Agent

**Book context:** Chapter 16, *Capstone: Secure, Observable Knowledge-and-Action Agent*
**Architecture:** [Capstone architecture](./architecture.md)
**Implementation input:** Accepted Chapter 1-15 checkpoints and their evidence
**Mandatory verification:** `uv run policyops verify ch16 --profile fixture --all --junit build/ch16/junit.xml --evidence build/ch16`

## Product summary

PolicyOps is a multi-tenant knowledge-and-action service that answers questions from a versioned policy corpus and, with explicit authority and approval, creates a policy-support ticket. The capstone integrates the patterns developed in Chapters 1-15 into one deployable service. It proves normal behavior, adversarial behavior, degraded operation, recovery, user-rights workflows, and accountable release decision-making.

This project introduces no new design pattern. Every selected component must trace to a chapter artifact, executable check, evidence record, rollback path, and owner. A pattern may be omitted only when a measured architecture decision shows that the workload does not justify it. Failed mandatory gates produce a **NO-GO** decision rather than a weakened release.

## Problem statement

Individual LLM patterns can work in isolation while the assembled application fails at their boundaries. Identity may disappear between retrieval and tools. A cached answer may bypass a policy update. Replayed execution may duplicate a ticket. Memory may preserve a deleted or poisoned instruction. An apparently healthy deployment may lack evidence that its controls still work.

The capstone must demonstrate that the complete PolicyOps system preserves its invariants across these boundaries and under failure. It must also leave future implementers with a reproducible repository, one verification command, operator runbooks, and a machine-readable record explaining why the system is or is not releasable.

## Goals

1. Assemble the accepted Chapter 1-15 components behind stable, provider-neutral contracts.
2. Answer current policy questions with tenant-safe retrieval, exact citations, and explicit abstention.
3. Create a support ticket only after an exact preview is bound to current approval, authorization, and an idempotency key.
4. Resume interrupted work without repeating an externally visible effect.
5. Preserve consent, provenance, correction, expiry, export, and deletion across primary and derived memory stores.
6. Produce correlated, redacted telemetry, track cost per successful outcome, and convert adjudicated failures into controlled evaluation changes.
7. Survive the declared dependency failures, load profile, bad release, rollback, backup, and restore scenarios.
8. Close all chapter-to-capstone traceability rows and produce a signed release or no-go evidence bundle.
9. Run the mandatory fixture profile from a clean checkout without paid credentials.

## Non-goals

- A general-purpose autonomous assistant, unrestricted browser agent, or arbitrary code-execution product.
- Training a foundation model or requiring GPU hardware for the core path.
- Claiming universal safety, universal prompt-injection prevention, or sandbox escape resistance.
- Replacing organizational legal, compliance, privacy, security, or release authorities.
- Benchmarking every model, vector database, orchestration framework, agent protocol, or cloud platform.
- Making graph retrieval, independent multi-agent control, hosted models, remote MCP transport, A2A, or Kubernetes mandatory when measured evidence supports a simpler configuration. The governed memory and local extension paths remain mandatory fixture implementations because the capstone must exercise their lifecycle and security invariants.
- Adding a second capstone implementation separate from Chapter 16.

## Component decision classes

| Class | Components | Capstone rule |
|---|---|---|
| Mandatory invariant | Identity propagation, tenant isolation, context authority, grounded citations/abstention, approval binding, idempotent effects, bounded execution, security controls, deletion, evidence, release policy | Must be implemented and pass; no no-use decision is allowed |
| Mandatory fixture implementation | Provider-neutral replay model, hybrid retrieval, governed memory, typed ticket tool, local MCP server, Agent Skill, one-host plugin, pre/post hooks, the accepted Chapter 10 topology behind the Chapter 11 durable harness, a deterministic comparison/fallback path, telemetry, Compose deployment, governance package | Must run in the credential-free fixture profile so the corresponding chapter handoff is exercised end to end |
| Optional with measured no-use ADR | Adapted model instead of baseline, graph route for workloads that show no gain, orchestrator-worker topology instead of simpler flow, independent A2A runtime, hosted/local live model, remote MCP transport, Kind/Helm deployment | May be disabled only when a versioned ADR links workload evidence, evaluation results, selected simpler path, owner, and rollback/revisit trigger |

## Users and stakeholders

| Role | Need |
|---|---|
| Policy reader | Current, authorized answers with citations or a clear abstention |
| Support requester | A visible ticket preview, explicit approval, and verifiable result |
| AI/application engineer | Reproducible components, typed boundaries, tests, traces, and rollback paths |
| Platform/SRE engineer | Health signals, bounded resource use, failure recovery, deployment and restore runbooks |
| Security engineer | Trust boundaries, default-deny capabilities, attack corpus, revocation, and incident evidence |
| Privacy/governance owner | Consent, correction, export, deletion, control ownership, current evidence, and release authority |
| Release reviewer | One traceability manifest and an unambiguous GO/NO-GO result |

## User stories

- As a policy reader, I can ask a temporal or multi-hop question and receive only claims supported by accessible, current evidence with resolvable citations.
- As a policy reader, I receive an abstention when evidence is insufficient, conflicting, stale, deleted, or unauthorized.
- As a support requester, I can preview the exact ticket mutation, approve it, and receive one ticket even if execution is retried after a crash.
- As a user, I can inspect, correct, export, and delete consented memory and receive a receipt covering derived stores.
- As an operator, I can trace one request across model, context, retrieval, graph, memory, orchestration, and tool spans without exposing sensitive content.
- As an operator, I can put the system into a declared degraded mode, roll back a bad release, and restore durable state.
- As a security reviewer, I can execute the supplied attack corpus and prove that unauthorized high-impact effects do not occur within the declared test boundary.
- As a release reviewer, I can map every high risk to a current owner, control, test, and signed evidence item before making a decision.

## Functional requirements

### Integration and release control

- **CAP-FR-001 - Traceability closure:** The repository shall maintain `capstone/traceability.yaml` with exactly one row for each Chapter 1-15 handoff. Each row shall declare its decision class and implemented component or structured no-use ADR; source checkpoint; artifact and configuration hashes; exact executable test command; evidence path, hash, signature, production time, and expiry; owner; rollback path; and status.
- **CAP-FR-002 - Reproducible entry point and CI parity:** A clean checkout shall create the locked fixture environment, deploy the service, run all mandatory gates and game-day scenarios, collect evidence, and tear down through documented `policyops` commands. `.github/workflows/capstone-game-day.yml` shall call those same commands, retain the evidence bundle, and include a test proving that a seeded mandatory-gate failure makes the workflow and release decision fail.
- **CAP-FR-003 - Release decision:** A machine-readable release policy shall evaluate mandatory gates and emit `GO` only when every required condition passes. Any missing, stale, tampered, unsigned, or failed mandatory item shall emit `NO-GO` with reasons.

### Knowledge and answer path

- **CAP-FR-004 - Authenticated request envelope:** Every request shall carry request and trace IDs, tenant, actor, roles, data classification, configuration identity/versions, deadline, budget, authorization context, and optional approval and idempotency identifiers across all component calls.
- **CAP-FR-005 - Model and inference policy:** The service shall use the provider-neutral model boundary, selected adaptation decision, bounded routing, deterministic verification, safe fallback, and tenant/configuration/freshness-aware caching from Chapters 1, 3, and 4.
- **CAP-FR-006 - Context assembly:** The context planner shall rank instruction authority, label provenance and sensitivity, enforce token budgets, compact history, preserve required facts, and refuse silent truncation.
- **CAP-FR-007 - Versioned retrieval:** The service shall ingest structured and supplied scanned-page fixtures, perform tenant-filtered lexical/vector retrieval and reranking, enforce freshness and deletion, and route eligible multi-hop or corpus-level questions to the graph component when its ADR enables that route.
- **CAP-FR-008 - Grounded answer:** Each answer claim shall reference a current accessible source version and exact text span or supplied page coordinate. The service shall abstain on insufficient, conflicting, stale, deleted, or unauthorized evidence.

### Memory and action path

- **CAP-FR-009 - Governed memory:** Working, episodic, semantic, and procedural views shall derive from a provenance-preserving ledger. Writes require policy and consent where applicable. Recall shall honor tenant scope, purpose, TTL, quarantine, correction, and deletion, and shall never grant tool authority.
- **CAP-FR-010 - Capability surfaces:** The mandatory fixture shall expose the ticket capability through one typed local tool and one local MCP server, include a focused Agent Skill that teaches the safe workflow, package it as a plugin for one reference host, and run a fail-closed pre-action hook plus a bounded post-action evidence hook. All surfaces shall share one canonical contract and policy decision. The required MCP gate shall use stable `2025-11-25`; the announced breaking `2026-07-28` release candidate shall remain an opt-in compatibility profile with version-gated transport/session behavior, Tasks/Apps, sampling/logging, schemas, and authorization, while application state remains explicit in both profiles.
- **CAP-FR-010A - Browser/computer-use path:** The mandatory fixture shall include the Chapter 10 mock approval-form path through a secured computer-use adapter, with DOM/screen observations treated as untrusted data and final mutation still routed through the Chapter 9 approval-bound `ToolPort`.
- **CAP-FR-011 - Approval-bound mutation:** Before ticket creation, the system shall produce the canonical Chapter 9 `EffectPreview` whose `effect_hash` is bound to actor, tenant, capability, arguments, policy/configuration versions, expiry, and idempotency key. Changed, stale, missing, revoked, or out-of-scope approval shall fail closed.
- **CAP-FR-012 - Bounded control flow:** The accepted Chapter 10 topology shall run over its canonical state graph behind the Chapter 11 durable harness. Known rules shall execute deterministically. Model decisions shall be bounded by declared state, tools, steps, time, tokens, and spend. Delegation shall carry signed identity and scope; independent A2A execution is optional and requires an approved ADR.
- **CAP-FR-013 - Durable execution:** Sessions shall use append-only events, checkpoints, leases with fencing, a transactional outbox, idempotency records, and reconciliation so all declared crash windows resume without duplicate business effects.

### Evidence, security, and operations

- **CAP-FR-014 - Evaluation and improvement:** The system shall run component, trajectory, outcome, adversarial, consistency, outcome-cost, and calibrated rubric evaluations. One adjudicated trace shall become a versioned case; a bounded candidate shall be compared with the baseline and immutable holdout, then canaried or reverted.
- **CAP-FR-015 - Correlated observability:** The Chapter 1 trace ID shall join all major spans and evidence, with request and run IDs for local lookup. Telemetry shall include artifact and configuration versions, authorization and approval decisions, budgets, outcomes, and error classes while applying redaction, sampling, and cardinality policy.
- **CAP-FR-016 - Security verification:** The test harness shall exercise prompt injection, malicious web/tool observations, poisoned retrieval/graph/memory, extension tampering, privilege escalation, confused-deputy paths, secret extraction, unauthorized egress/filesystem access, replay, duplicate effects, and resource exhaustion.
- **CAP-FR-017 - Deployment and recovery:** The core Docker Compose profile shall deploy API, worker, database, model gateway, telemetry, ticket stub, and fault proxy with health checks, bounded queues, retry classification, circuit breaking, backpressure, digest-pinned images, migrations, rollback, backup, and restore.
- **CAP-FR-018 - User rights and governance:** The system shall execute correction, export, and deletion across primary and derived stores; maintain inventory, risks, autonomy, ownership, approval, retention, and evidence records; and preserve an accountable human release decision.
- **CAP-FR-019 - Ordered game day:** One automation entry point shall run the numbered production game day defined below in order and retain scenario-level prerequisites, inputs, expected and actual results, traces, artifacts, operator identity, mandatory-gate decision, and cleanup status.

## Non-functional requirements

- **CAP-NFR-001 - Determinism:** Mandatory fixture gates shall produce repeatable decisions and stable machine-readable artifacts for fixed inputs. Stochastic trials shall declare seeds where supported and report distributions rather than a single score.
- **CAP-NFR-002 - Isolation:** Tenant data, caches, retrieval, graph, memory, traces, approvals, and effects shall remain isolated under normal, adversarial, replay, and recovery paths.
- **CAP-NFR-003 - Boundedness:** Every request shall have maximum steps, tokens, wall time, spend, tool calls, result size, queue age, and retry count. Exhaustion shall fail or degrade predictably.
- **CAP-NFR-004 - Reliability:** The declared core profile shall meet recorded availability, latency, error-rate, recovery-time, and recovery-point objectives under the supplied workload and hardware profile.
- **CAP-NFR-005 - Portability:** Core verification shall require Python 3.12+, `uv`, Git, Docker Compose, and 12-16 GB RAM, but no GPU, cloud account, hosted model, or paid credential.
- **CAP-NFR-006 - Evolvability:** Provider, model, embedding, reranker, MCP transport, orchestration, storage, and deployment choices shall sit behind versioned ports and contract tests.
- **CAP-NFR-007 - Auditability:** Evidence shall be content-addressed, timestamped, linked to configuration and code identity, and immutable after release-bundle finalization.
- **CAP-NFR-008 - Operability:** All stateful services shall expose liveness and readiness, and every failure drill shall have detection, containment, recovery, and verification instructions.

## Security and privacy requirements

- **CAP-SEC-001:** Authentication and authorization shall occur at ingress and again at every sensitive data or capability boundary; downstream services shall not trust model claims of identity or authority.
- **CAP-SEC-002:** Tool, MCP, plugin, skill, and hook packages shall be allowlisted, versioned, integrity-checked, least-privileged, disableable, and revocable. Untrusted metadata remains data, not instruction.
- **CAP-SEC-003:** Secrets shall be injected at runtime, excluded from source, fixtures, prompts, memory, output, traces, and evidence, and scoped to the minimum service identity and destination.
- **CAP-SEC-004:** Sandboxed workers shall run non-root with restricted filesystem, process, network, credential, and egress access. The documented claim is limited to the properties exercised by the supplied corpus.
- **CAP-SEC-005:** Approval shall authorize only the exact canonical mutation preview and shall expire. Preview changes, identity changes, configuration changes, or policy changes require re-approval.
- **CAP-SEC-006:** Memory and telemetry shall apply purpose limitation, minimization, consent, retention, redaction, access logging, correction, export, and deletion.
- **CAP-SEC-007:** Every externally visible mutation shall carry an idempotency key and be reconciled against the ticket service before uncertain retries.
- **CAP-SEC-008:** Builds shall produce an SBOM and verify dependency, image, fixture, model, extension, policy, and configuration hashes before release.
- **CAP-SEC-009:** Security test results shall state tested assumptions and residual risks; passing the corpus shall not be described as proof against all attacks.

## Fixtures and evidence inputs

The mandatory profile uses two isolated tenants, three roles, current and superseded policy versions, a scanned-page/table fixture with coordinates, contradictory temporal claims, an inaccessible record, deleted content, a consented memory history, a poisoned memory candidate, a mock ticket service, a mock approval-form browser fixture, deterministic model/retrieval/reranker replays, test signing keys, a development-only token issuer, malicious document and web/tool attack cases, a fake clock, fault proxy profiles, a hashed holdout, and a corrupt backup fixture.

The implementation must not depend on live external data. Every fixture has a manifest entry containing origin, rights, checksum, schema version, expected tenant/purpose scope, and deletion behavior. Evidence outputs include JSON summaries, JUnit, traces, metrics snapshots, test reports, decisions, receipts, hashes, and operator-approved release records.

## External behavior

The minimum API surface is:

- `POST /v1/answer` for grounded answer or typed abstention, preserving the Chapter 1 contract. A plural alias requires a versioned compatibility ADR and regression tests.
- `POST /v1/tickets/preview` to create the canonical proposed mutation.
- `POST /v1/tickets/execute` to execute an approved preview idempotently.
- `GET /v1/runs/{run_id}` to inspect bounded execution state and outcome.
- `GET /v1/memory` plus correction, export, and deletion operations for the authenticated subject.
- `/health/live`, `/health/ready`, and version/configuration metadata endpoints that expose no secrets, preserving the Chapter 1 health contract.

The CLI provides environment lifecycle, verification, fault injection, replay, evidence finalization, and release-decision commands. API and CLI errors use stable machine-readable codes such as `INSUFFICIENT_EVIDENCE`, `APPROVAL_REQUIRED`, `APPROVAL_STALE`, `POLICY_DENIED`, `BUDGET_EXHAUSTED`, `DEPENDENCY_UNAVAILABLE`, and `RUN_RECOVERING`.

## Acceptance criteria and traceability

| Acceptance gate | Requirements | Pass condition |
|---|---|---|
| Clean-room reproducibility | CAP-FR-001-003, CAP-NFR-005 | A fresh checkout and `.github/workflows/capstone-game-day.yml` run the same commands without external credentials; all 15 traceability rows close; a seeded mandatory failure makes CI and release fail |
| Grounded answers | CAP-FR-004-008 | Authorized current claims have exact citations; poisoned, deleted, stale, conflicting, inaccessible, and insufficient cases abstain |
| Memory lifecycle | CAP-FR-009, CAP-FR-018, CAP-SEC-006 | Consent, TTL, conflict, quarantine, correction, export, deletion, and cross-tenant cases pass with complete receipts |
| Controlled action | CAP-FR-010-013, CAP-SEC-001-005, CAP-SEC-007 | Approved exact preview creates one ticket; stale, changed, forged, revoked, duplicated, browser/computer-use bypass, or alternate-path attempts create none |
| Crash recovery | CAP-FR-013, CAP-NFR-004 | Every supplied crash window resumes to the expected state with one or zero intended business effects and no ambiguous record |
| Evaluation and telemetry | CAP-FR-014-015 | One trace ID joins spans; PII/cardinality tests pass; cost per successful outcome is reported; overfit candidate fails holdout; bad canary reverts |
| Security | CAP-FR-016, CAP-SEC-001-009 | No supplied high-impact attack creates unauthorized effect; secrets do not appear; malicious web/tool observations cannot grant authority; undeclared egress/filesystem access fails |
| Reliability and recovery | CAP-FR-017, CAP-NFR-003-004, CAP-NFR-008 | Load/SLO evidence records declared results; outage, bad image, rollback, corrupt backup rejection, and valid restore pass |
| Governance and rights | CAP-FR-018, CAP-NFR-007 | Each high risk maps to current owner/control/test/evidence; rights workflows complete; invalid evidence blocks release |
| Final game day | CAP-FR-019 | All ordered scenarios record expected/actual outcomes and cleanup; decision engine emits GO only if every mandatory gate passes |

## Ordered production game day

The runner executes these scenarios in sequence against a freshly deployed, locked fixture profile. A failed mandatory expectation stops release eligibility but does not skip evidence collection or safe cleanup for later independent recovery checks.

| Step | Scenario and prerequisite | Injection/action | Expected result and mandatory evidence | Cleanup/checkpoint |
|---:|---|---|---|---|
| 1 | Baseline release candidate loaded | Verify lineage, rights, split integrity, hashes, and the unsafe supplied adaptation candidate | Unsafe candidate is rejected; selected baseline/adapter and rollback target are recorded | Restore selected model profile |
| 2 | Current, superseded, scanned, and contradictory policies indexed | Ask the supplied multimodal temporal and multi-hop questions | Only authorized current claims appear with exact span/page coordinates; graph route or no-use ADR is recorded | Save answer/citation evidence |
| 3 | User has consented memory plus a poisoned candidate | Recall both records during a follow-up question | Consented memory improves context; poison is quarantined/ignored; memory grants no authority | Record memory decision and version |
| 4 | Ticket proposal can be previewed | Approve the exact preview and execute it | One ticket is created with matching effect, approval, and idempotency evidence | Retain ticket reference for recovery |
| 5 | Ticket effect committed but acknowledgement withheld | Crash the worker after external effect and before acknowledgement, then resume | Reconciliation finds the existing ticket; no duplicate is created | Restore worker and close run |
| 6 | Second tenant plus malicious policy and web/tool observations loaded | Attempt cross-tenant retrieval, injected tool use, browser/profile confusion, secret access, and unauthorized egress | No protected data or effect escapes; policy, sandbox, browser/profile, and egress denials are traced | Revoke attack credentials and clear sandbox |
| 7 | A policy correction and user deletion request are pending | Correct source/memory data and delete the subject across primary/derived stores | Retrieval/graph/memory/caches update; signed receipt enumerates every store; deleted data is not recalled | Re-index affected fixtures and retain minimized receipt |
| 8 | Normal model path active | Fail the selected model/provider adapter | Quality-preserving fallback runs only if configured; otherwise typed failure/abstention occurs within budget | Restore provider and verify readiness |
| 9 | Retrieval path active | Fail lexical/vector retrieval and graph dependency | No unsupported answer is produced; valid scoped cache may serve only if freshness and authorization match | Restore stores and verify index versions |
| 10 | Declared hardware profile stable | Apply workload spike and slow ticket/model dependencies | Admission, bounded queues, backpressure, deadlines, and circuit breakers hold; SLO/budget results are recorded | Drain queues and prove no orphan run/effect |
| 11 | One adjudicated trace graduated to an eval | Submit an overfit prompt/routing candidate | Target case may improve, but immutable holdout regression rejects the candidate | Restore baseline configuration |
| 12 | Behavior and deployment canaries enabled | Deploy seeded bad behavior/configuration and bad image/schema candidate | Canary detects both classes at their owned boundaries and rolls back to the known-good versions | Verify configuration, binary, and schema hashes |
| 13 | Verified and corrupt backups available | Attempt corrupt restore, then fail the active durable store | Corrupt backup is rejected; no release evidence is overwritten | Select last verified recovery point |
| 14 | Active service unavailable | Restore database, events, outbox, indexes, memory, and governance state | Integrity, no-duplicate-effect, RTO, and RPO checks pass on the declared profile | Reconcile all pending runs/effects |
| 15 | Restored subject and evidence registry available | Export the user record and release evidence index | Export is complete, authorized, minimized, and hash-verifiable | Revoke temporary export access |
| 16 | All prior steps have immutable results | Re-run traceability and governance release policy | `GO` only if all mandatory gates pass; otherwise `NO-GO` lists exact failed/expired/missing items | Finalize and sign bundle; tear down environment |

## Success metrics

- 15 of 15 traceability rows closed with no orphan artifact or missing rollback path.
- 100% of mandatory contract, authorization, isolation, citation, abstention, approval, idempotency, deletion, security, and governance cases pass.
- Zero unauthorized high-impact effects and zero duplicate tickets across the supplied normal, adversarial, and crash-window suite.
- Zero cross-tenant result, cache, graph, memory, telemetry, approval, or effect leakage in the supplied tests.
- 100% of answer citations resolve to the expected version and span/coordinate; all designated unanswerable cases abstain.
- 100% of primary and declared derived stores appear in the deletion receipt within the configured test window.
- The declared latency, error, budget, cost-per-successful-outcome, queue, RTO, and RPO thresholds pass on the recorded hardware profile.
- All release evidence verifies by hash and signature; a seeded stale or tampered item forces NO-GO.

## Dependencies and prerequisites

The capstone begins from accepted Chapter 1-15 solution tags, a complete fixture and attack pack, frozen release thresholds, an incomplete traceability manifest, deployment profiles, game-day matrix, and evidence templates. The core environment requires Python 3.12+, `uv`, Git, Docker Compose, Linux-container support, and 12-16 GB RAM. Exact dependencies and container images are pinned and hashed when implementation begins.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Integration becomes an unfinishable rewrite | Preserve chapter ports, integrate one vertical slice at a time, and permit evidence-backed no-use decisions for optional patterns |
| Fixture success hides real provider behavior | Separate deterministic release gates from labeled hosted/local/Kubernetes evidence and retain contract parity tests |
| Complex orchestration masks ownership | Keep known rules deterministic, require topology ADRs, and bind every delegated task to identity, scope, budget, and join policy |
| Approval UI becomes security theater | Hash the exact canonical preview, expire it, re-check policy at execution, and test alternate action paths |
| Replay repeats effects | Use outbox, idempotency, reconciliation, and crash-window tests against the mock service |
| Evidence is voluminous but unactionable | Enforce a schema linking risk, control, test, evidence, owner, version, expiry, and decision |
| Security claims exceed evidence | State threat-model assumptions and residual risks; limit claims to tested isolation properties |
| Deletion misses derived data | Maintain a data-store registry, tombstone/invalidation protocol, and store-by-store signed receipt |

## Delivery milestones

1. **Repository lock and traceability import:** Verify all accepted tags, manifests, artifact/configuration hashes, schemas, CI workflow command parity, and baseline gates.
2. **Read-only vertical slice:** Integrate request envelope, inference, context, retrieval/graph, grounded answer, citations, and abstention.
3. **State and action slice:** Integrate memory, capability surfaces, approval, orchestration, durable session, idempotent effect, and recovery.
4. **Evidence and containment slice:** Integrate telemetry, evaluation, trace-to-eval change, policy, sandbox, extension integrity, and attack suite.
5. **Operations and rights slice:** Complete Compose deployment, load/fault tests, rollback, backup/restore, governance, correction, export, and deletion.
6. **Game day and release review:** Freeze configuration, run the ordered game day locally and through `.github/workflows/capstone-game-day.yml`, prove a seeded gate failure blocks release, finalize immutable evidence, and record GO or NO-GO.

Each milestone must leave the mandatory fixture path green and produce a rollback target. The core project is sized for 10-14 focused hours over two or three sessions after all chapter checkpoints exist; optional hosted-model, remote MCP, independent A2A, and Kubernetes profiles are separately timed extensions.

## Future extensions

- Compare a hosted model and a pinned local model with the deterministic baseline while retaining the same contracts and gates.
- Exercise remote MCP transport with production identity and certificate management.
- Deploy an independently owned reviewer through A2A when the responsibility and trust boundary justifies it.
- Run the digest-pinned system on Kind/Helm and then a managed Kubernetes platform.
- Add independent red-team cases, larger tenant/load profiles, and externally reviewed governance mappings.
- Replace optional components only through contract tests, migration/rollback plans, and new traceability evidence.
