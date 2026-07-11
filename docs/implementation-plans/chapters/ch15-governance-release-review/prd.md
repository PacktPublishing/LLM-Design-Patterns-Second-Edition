# Chapter 15 Project PRD: Conduct a Governance Release Review

This project implements the hands-on work for Chapter 15, **Governance, Responsible AI, and Human Oversight**. It indexes the technical artifacts and evidence produced in Chapters 1-14, assigns accountable decision rights, exercises correction and deletion, and makes a deterministic release recommendation. It does not recreate those technical controls. The companion [architecture](./architecture.md) defines the machine-readable governance package and release gate.

## Product proposal

Create a PolicyOps system inventory, risk and autonomy record, ownership and human-approval matrix, retention policy, transparency notice, and control-to-evidence graph. Connect every high risk to a current owner, technical control, executable test, trace or report, expiry, and review decision. Process a simulated correction and deletion request across primary and derived stores, then issue a documented `GO` or `NO-GO` recommendation.

## Problem

Production teams often have many controls but cannot answer who owns them, which current evidence proves they work, when that evidence expires, or what should happen when a user contests or deletes data. A release checklist can pass even when an owner has left, autonomy changed, a signature is invalid, a test result belongs to an old configuration, or a deleted memory remains in an index or cache. PolicyOps needs governance as an executable release policy: missing, stale, tampered, unsigned, or ownerless evidence must block release, and high-impact decisions must remain accountable to a valid human role.

## Goals

- Define the PolicyOps purpose, users, affected parties, system boundary, AI components, data, tools, integrations, owners, and non-goals.
- Classify risk, autonomy, reversibility, data sensitivity, communication reach, side effects, oversight, and prohibited uses.
- Assign accountable human authority for framing, exceptions, appeals, high-impact approval, and release.
- Track non-human identities, service accounts, agents, tools, credentials, and delegated work under human owners.
- Link every high risk to a control, test, evidence artifact, owner, validity period, review date, and release rule.
- Block material model, data, tool, skill, policy, autonomy, and deployment changes that lack current review evidence.
- Govern correction, export, deletion, retention, retirement, and credential revocation across primary and derived stores.
- Produce a transparent, reproducible, signed release or no-go record for the capstone.

## Non-goals

- Reimplementing authorization, approval binding, deletion, security, observability, backup, or deployment controls from earlier chapters.
- Automating legal conclusions or representing the package as legal advice.
- Encoding volatile regulatory effective dates as timeless facts; dated mappings require counsel review.
- Allowing an agent to approve its own exception or production release.
- Treating documentation alone as evidence when an executable test or operational record is required.
- Resolving every organization-specific risk framework in the core; one mapping is an extension.

## Users and accountable roles

- **System owner:** accountable for purpose, scope, resources, and final release decision.
- **Risk owner:** accepts or remediates a named risk and residual risk.
- **Control owner:** keeps a control and its evidence current.
- **Technical approver:** validates high-impact action and change evidence.
- **Privacy and user-rights lead:** owns correction, export, deletion, retention, and appeal obligations.
- **Operator/release engineer:** runs the gate and archives the immutable decision package.
- **Affected user or representative:** receives notice and can request correction, export, deletion, or contestation.

## User stories

- As a system owner, I can see every high risk, who owns it, how it is controlled, and whether current evidence supports release.
- As a privacy lead, I can submit a deletion request and verify primary, index, cache, graph, memory, trace, and backup-policy outcomes.
- As a release engineer, I receive a deterministic `NO-GO` when an owner is missing or evidence is stale, unsigned, or tampered.
- As an affected user, I can understand where AI is used, which sources and memory influence it, what actions it may take, and how to appeal.
- As an auditor, I can reproduce the release decision from versioned schemas, hashes, signatures, policy, and evidence references.

## Functional requirements

- **CH15-FR-001:** A versioned system inventory shall record purpose, intended users, affected parties, models, data, indexes, memory, tools, skills, plugins, hooks, agents, integrations, environments, owners, and explicit non-goals.
- **CH15-FR-002:** Each use case shall have a risk and autonomy record covering impact, failure cost, reversibility, data sensitivity, communication reach, side effects, oversight mode, prohibited use, and residual risk.
- **CH15-FR-003:** Ownership records shall assign a current human owner and backup for systems, risks, controls, models, agents, tools, service accounts, credentials, decisions, incidents, and delegated work.
- **CH15-FR-004:** An approval matrix shall map risk and change class to required approver role, separation-of-duties rule, evidence, expiry, and escalation path.
- **CH15-FR-005:** A control-to-evidence graph shall link risk, control, implementation artifact, executable test, trace or report, configuration and image hashes, owner, signature, generated time, expiry, and review status.
- **CH15-FR-006:** The evidence resolver shall verify existence, schema, hash, signature, signer authorization, configuration applicability, time validity, and required test result before marking evidence current.
- **CH15-FR-007:** A change classifier shall detect declared model, data, prompt, retriever, memory, tool, extension, policy, autonomy, deployment, owner, or retention changes and select the applicable review policy.
- **CH15-FR-008:** The release gate shall return `GO` only when every mandatory risk path reaches a current owner, effective control, passing test, current signed evidence, and valid approval; otherwise it shall return `NO-GO` with reason codes.
- **CH15-FR-009:** High-impact trace evidence shall name the valid accountable approver and exact action or decision scope.
- **CH15-FR-010:** Correction, export, and deletion requests shall be authenticated, tenant-scoped, time-bounded, appealable, and tracked through adapters to all declared primary and derived stores.
- **CH15-FR-011:** A deletion receipt shall enumerate each store, item or query scope, action, completion time, verifier result, exception, retention basis, and follow-up date.
- **CH15-FR-012:** A transparency notice shall explain AI involvement, sources, memory use, tools and actions, meaningful limits, human oversight, and correction, export, deletion, and appeal channels.
- **CH15-FR-013:** The final decision package shall include manifests, evidence graph, unresolved risks and exceptions, approver identity, policy version, configuration and image hashes, and immutable `GO` or `NO-GO` result.

## Non-functional requirements

- **CH15-NFR-001:** Governance records shall validate against versioned JSON Schemas and produce stable, machine-readable errors.
- **CH15-NFR-002:** The fixture profile shall run from a clean checkout without paid credentials and use local test identities and signing keys.
- **CH15-NFR-003:** Re-running the gate against identical inputs shall produce the same decision, reason ordering, and decision digest.
- **CH15-NFR-004:** Evidence verification shall fail closed when a store, signature, owner directory, clock, or policy dependency is unavailable.
- **CH15-NFR-005:** Human-readable reports shall be generated from the machine-readable source rather than maintained as divergent truth.
- **CH15-NFR-006:** The verifier shall emit JSON, JUnit, dependency, fixture, configuration, image, signature, rights-request, and release-decision evidence and exit non-zero on a mandatory failure.

## Security and privacy requirements

- **CH15-SEC-001:** Governance and rights-request records shall be tenant-scoped, role-restricted, minimally disclosed, and auditable.
- **CH15-SEC-002:** Test signing keys shall be fixture-only, stored outside committed content, and distinct by signer role.
- **CH15-SEC-003:** Signatures shall bind the artifact hash, schema version, configuration scope, issuer, issued time, expiry, and evidence purpose.
- **CH15-SEC-004:** No agent, service account, control owner, or evidence producer may serve as its own required release approver where separation of duties applies.
- **CH15-SEC-005:** Correction and deletion workflows shall protect against cross-tenant requests, unauthorized erasure, replay, incomplete derived-store coverage, and false success receipts.
- **CH15-SEC-006:** Archived release packages shall preserve required evidence without retaining unnecessary user content or secrets.

## Starter, fixtures, and data

Start from `ed2-v1.0-ch15-start`. The starter contains versioned schemas, incomplete ownership records, stale and tampered evidence, signed fixture evidence, a configuration change set, and simulated correction, export, and deletion requests. It consumes verified Chapter 14 artifacts and evidence indexes from all earlier chapters.

Primary paths are `src/policyops/governance`, `governance`, `tests/governance`, and `config/release_policy.yaml`. `labs/ch15/manifest.toml` records fixture hashes, identities, signing setup, services, commands, cleanup, artifacts, gates, and faults.

## External behavior and interfaces

The CLI exposes `policyops governance validate`, `evidence verify`, `release review`, `rights correct`, `rights export`, and `rights delete`. Release review accepts immutable manifest and change-set references and writes a decision record; it never mutates technical evidence to make a gate pass. An authenticated API may wrap the rights workflow for the fixture UI, but the CLI and schemas remain the canonical implementation surface. Every denial includes stable reason codes, affected record IDs, owner role, and required remediation without exposing restricted content.

## Required drill

Remove a required owner, expire one approval/evidence record, tamper with another artifact, change the autonomy tier, and submit correction plus deletion requests. The gate must produce `NO-GO` for each unresolved condition. After authorized remediation, repeat the review and verify derived-store coverage, signed receipt, valid high-impact approver, and deterministic decision digest.

## Required artifacts

Deliver the versioned governance package and schemas, system inventory, risk and autonomy records, ownership and approval matrix, control-to-evidence graph, retention and rights records, transparency notice, correction/export/deletion receipt, governance CI result, and immutable release decision package.

## Acceptance criteria and traceability

- **AC-01 (CH15-FR-001, CH15-FR-002, CH15-FR-003, CH15-FR-004, CH15-FR-005, CH15-FR-006):** Given every declared high risk, when the graph resolves, then it reaches a current owner, control, passing test, applicable artifact, and current authorized signature.
- **AC-02 (CH15-FR-006, CH15-FR-007, CH15-FR-008, CH15-NFR-004):** Given missing, stale, tampered, unsigned, wrong-configuration, or ownerless evidence, when review runs, then release returns `NO-GO` with stable reason codes.
- **AC-03 (CH15-FR-007, CH15-FR-008, CH15-FR-009, CH15-SEC-004):** Given an autonomy or high-impact action change, when review runs, then the correct independent human role and current scoped approval are required.
- **AC-04 (CH15-FR-010, CH15-FR-011, CH15-SEC-005):** Given authenticated correction and deletion requests, when processing completes, then the receipt enumerates and verifies primary and derived stores within the declared window; a missed store prevents completion.
- **AC-05 (CH15-FR-012):** Given the system inventory, when the notice is generated, then it accurately states AI involvement, evidence sources, memory, tools, limits, oversight, and rights paths.
- **AC-06 (CH15-FR-013, CH15-NFR-003):** Given unchanged inputs, when release review repeats, then the decision, ordered reasons, and decision digest match.
- **AC-07 (CH15-NFR-001, CH15-NFR-002, CH15-NFR-003, CH15-NFR-004, CH15-NFR-005, CH15-NFR-006, CH15-SEC-001, CH15-SEC-002, CH15-SEC-003):** Given a clean checkout, when `verify-ch15` runs, then schemas, signatures, roles, rights requests, and evidence outputs pass without paid credentials.

## Success metrics

- 100% of high risks resolve to a current human owner, control, executable test, current evidence, and approval or block release.
- 100% of supplied invalid-evidence cases produce `NO-GO`.
- 100% of high-impact fixture traces name an authorized, current, independent approver.
- Correction and deletion receipts cover every store in the system inventory within the declared fixture window.
- Identical inputs produce an identical decision digest.
- Generated transparency notice has zero fields that conflict with the machine-readable inventory.

## Execution contract

Core duration is **3-5 hours**. Prerequisites are verified Chapter 14 artifacts, a JSON Schema validator, signed evidence fixtures, local test keys, and simulated correction, export, and deletion requests.

```text
uv sync --frozen
uv run policyops env up --lab ch15 --profile fixture
uv run policyops verify ch15 --profile fixture --junit build/ch15/junit.xml --evidence build/ch15
uv run policyops fault ch15 --scenario all
uv run policyops env down --lab ch15
```

Pull requests run `verify-ch15` and all earlier regression gates. The extension maps the package to one organizational risk framework and signs the aggregate evidence bundle with a test key, proving that mapping adds accountability without replacing executable technical evidence.

## Dependencies and handoff

The project consumes accepted Chapter 14 image, migration, load, chaos, restore, and runbook evidence plus artifacts from Chapters 1-13. It produces the inventory, risk and autonomy records, ownership and approval matrix, control-to-evidence graph, transparency notice, correction/export/deletion evidence, signed decision record, and governance CI result. Register them in `capstone/traceability.yaml`, compare with `ed2-v1.0-ch15-solution`, and tag `ch15-complete`. [Chapter 16](../ch16-policyops-capstone/prd.md) begins from this accepted cumulative checkpoint and must close all 15 traceability rows.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Governance becomes paperwork detached from runtime | Require executable tests, configuration applicability, signatures, traces, and fresh evidence links. |
| Evidence is current but belongs to another build | Bind evidence to configuration, image, fixture, and policy hashes. |
| Deletion receipt reports success while a derived copy remains | Generate store coverage from the inventory and require independent verification per adapter. |
| Standards mapping becomes stale legal advice | Date every mapping, name its reviewer, and keep it optional to the core technical gate. |
| Agent approves its own work | Enforce role separation and independent approver identity in policy. |

## Delivery milestones

1. Freeze schemas, roles, decision policy, signature envelope, and deterministic reason codes.
2. Complete inventory, risk/autonomy, ownership, approval, retention, and transparency records.
3. Build evidence resolver, change classifier, control graph, and release gate.
4. Integrate correction, export, deletion adapters and verified receipt generation.
5. Run invalid-evidence drills, remediate, issue final decision package, and register capstone evidence.

## Future extensions

Map the package to an organizational risk framework, integrate a corporate identity directory, use hardware-backed signing, add scheduled evidence-expiry alerts, and automate retirement reviews. These extensions must retain the executable control graph and dated, reviewed mapping metadata.
