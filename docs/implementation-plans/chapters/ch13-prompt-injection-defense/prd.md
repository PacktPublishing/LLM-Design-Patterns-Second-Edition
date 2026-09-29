# Chapter 13 Project PRD: Defend Against Indirect Prompt Injection

This project implements the hands-on work for Chapter 13, **Security and Guardrail Patterns**. Indirect prompt injection means adversarial instructions hidden in documents, tool results, web pages, memory, or other data that an agent reads. The project attacks the composed PolicyOps path from retrieval through approved action, then adds enforceable identity, capability, filesystem, network, secret, supply-chain, and revocation controls. See the companion [architecture](./architecture.md).

## Product proposal

Use a malicious policy document and a malicious web/tool observation that attempt unauthorized ticket creation and private-data exfiltration through an allowed communication capability. Add instruction-data separation, capability scoping, exact-preview approval, egress restrictions, browser/profile isolation, secret filtering, sandbox containment, signed extension checks, and revocation, then run the supplied attack harness.

## Problem

A model cannot reliably distinguish trusted instructions from hostile text by wording alone. Risk becomes acute when three conditions coexist: private data, untrusted content, and a way to communicate externally. This “lethal trifecta” lets a poisoned document request secret access and transmit the result through a tool that is legitimate in other contexts. Prompt filters do not enforce operating-system access, identity, destination policy, or approval binding. PolicyOps needs structural controls that make at least one leg unavailable, plus executable tests for tool, MCP, Agent Skill, memory, retrieval, sandbox, egress, duplicate-effect, and resource attacks.

## Goals

- Publish a concrete threat model covering assets, actors, trust boundaries, autonomy tiers, and attack paths.
- Treat retrieved content, memory, tool results, extension instructions, and copied text as untrusted data.
- Authenticate the principal before assigning tenant data, tools, sessions, sandboxes, or delegation rights.
- Authorize every capability by action, resource, tenant, destination, risk tier, and budget.
- Attack and harden Chapter 9's Propose-Preview-Approve-Execute-Verify flow.
- Enforce default-deny filesystem, process, network, credential, and egress constraints around tool execution.
- Verify signatures, hashes, allowlists, versions, and revocation for tools, MCP servers, Agent Skills, plugins, hooks, models, and dependencies.
- Produce a repeatable security report and incident playbook grounded in the supplied corpus.

## Non-goals

- Proving universal resistance to prompt injection or sandbox escape.
- Rebuilding Chapter 9's MCP, Agent Skill, plugin, hook, or tool interfaces.
- Replacing Chapter 12's telemetry and improvement pipeline; this project attacks it and asserts safe boundaries.
- Deploying a multi-node production platform or testing disaster recovery; Chapter 14 owns that scope.
- Providing legal or regulatory advice or making the governance release decision from Chapter 15.
- Depending on a hosted red-team model or paid API credential.

## Users

- **Security engineer:** defines policy, attack fixtures, containment, and residual risk.
- **AI engineer:** integrates untrusted-content labels and capability decisions into agent execution.
- **Platform engineer:** maintains sandbox, egress proxy, extension verification, and secret boundaries.
- **Application owner:** sets allowed policy workflows, benign-task false-positive ceiling, and incident response.
- **Release reviewer:** checks the security evidence and unresolved residual risks.

## User stories

- As a security engineer, I can submit a poisoned document and prove it cannot access private data and send it to an undeclared destination.
- As an approver, I can see the exact action and destination, and a changed, stale, replayed, or forged preview fails.
- As a platform engineer, I can revoke an extension or capability and observe that new and cached sessions stop using it.
- As an application owner, I can test a prohibited-content case and a benign near-neighbor without accepting unlimited over-refusal.
- As an incident responder, I can identify the principal, content provenance, policy decision, attempted access, and containment action without exposing the secret.

## Functional requirements

- **CH13-FR-001:** A versioned threat model shall enumerate assets, actors, entry points, trust boundaries, autonomy tiers, abuse cases, controls, test IDs, and residual risks.
- **CH13-FR-002:** Every retrieved, recalled, tool-returned, or extension-provided content item shall carry provenance, trust classification, tenant, and authority metadata separate from its text.
- **CH13-FR-003:** Untrusted content shall never create or widen system instructions, identity, capability scope, approval, destination allowlists, or secret access.
- **CH13-FR-004:** The policy decision point shall evaluate authenticated principal, tenant, action, resource, destination, data class, risk tier, approval, budget, extension identity, and runtime context.
- **CH13-FR-005:** High-impact action execution shall validate a current approval over an exact canonical preview and reject forged identity, stale or changed preview, replay, confused-deputy scope, and approval fatigue scenarios.
- **CH13-FR-006:** Tool sandboxes shall enforce non-root execution, read-only root filesystem, declared writable paths, process and resource limits, restricted syscalls, no inherited host credentials, and default-deny network access.
- **CH13-FR-007:** Outbound requests shall traverse an egress policy point that validates scheme, host, port, resolved address, method, data class, tenant, and action grant and blocks redirects or DNS changes that escape policy.
- **CH13-FR-008:** A secret broker shall issue only short-lived, capability-scoped fixture credentials directly to the authorized runtime and shall prevent secrets from entering prompts, tool results, logs, or telemetry.
- **CH13-FR-009:** Tools, MCP servers, Agent Skills, plugins, hooks, models, and dependencies shall be checked against an allowlist and integrity metadata; revoked or mismatched artifacts shall fail closed.
- **CH13-FR-010:** The attack harness shall run supplied injection, malicious web/tool observation, retrieval and memory poisoning, privilege escalation, exfiltration, extension tampering, duplicate-effect, resource exhaustion, prohibited-content, and benign near-neighbor cases.
- **CH13-FR-011:** Security events shall record redacted evidence for identity, authorization, approval, sandbox, egress, integrity, revocation, and postcondition decisions using Chapter 12's semantic fields.
- **CH13-FR-012:** The incident workflow shall support containment, capability revocation, session quarantine, evidence preservation, recovery, and promotion of confirmed failures into regression cases.
- **CH13-FR-013:** HTTP-based MCP authorization tests shall validate protected-resource discovery, authorization-code flow with PKCE, resource audience, and rejection of token passthrough under the stable `2025-11-25` profile. A separate opt-in `2026-07-28` release-candidate profile shall additionally validate authorization-server issuer (`iss`) and bind registered client credentials to that issuer without making release-candidate behavior a stable-profile requirement.

## Non-functional requirements

- **CH13-NFR-001:** The fixture profile shall run in Linux containers without paid credentials and use deterministic model and attack replays.
- **CH13-NFR-002:** Policy decisions for supplied actions shall be deterministic and explainable through stable reason codes.
- **CH13-NFR-003:** Security controls shall fail closed when identity, policy, integrity, revocation, approval, secret broker, or egress dependencies are unavailable.
- **CH13-NFR-004:** Container and policy bundles shall be reproducible from locked dependencies and generate a software bill of materials (SBOM), an inventory of included software components.
- **CH13-NFR-005:** The verifier shall emit JSON, JUnit, trace, dependency, fixture, configuration, image, and declared-hardware evidence and exit non-zero on any mandatory failure.
- **CH13-NFR-006:** The project shall declare which isolation properties were tested and shall not generalize beyond the supplied corpus and runtime.

## Security and privacy requirements

- **CH13-SEC-001:** Cross-tenant data, memory, traces, tools, approvals, sandboxes, and credentials shall remain inaccessible under all supplied attacks.
- **CH13-SEC-002:** Private data plus untrusted content shall never coexist with unrestricted external communication; at least one leg shall be structurally unavailable in each execution profile.
- **CH13-SEC-003:** Undeclared filesystem paths, network destinations, processes, syscalls, and environment secrets shall be inaccessible from the sandbox.
- **CH13-SEC-004:** Capability grants shall be least-privileged, short-lived, audience-bound, revocable, and non-transferable between principals or tenants.
- **CH13-SEC-005:** Logs, traces, reports, and model-visible content shall contain redacted values or fingerprints, not supplied secrets.
- **CH13-SEC-006:** The benign-task false-positive ceiling and prohibited-case safe-failure rule shall be declared before running the corpus.

## Starter, fixtures, and data

Start from `ed2-v1.0-ch13-start`. The starter supplies an attack corpus, malicious policy documents, malicious web/tool observation fixtures, poisoned memory and trace fixtures, malicious MCP and Agent Skill packages, a sandbox profile, policy engine, internal network, egress proxy, browser/profile fixture, non-root image, test identities, ephemeral fixture secrets, and pinned SBOM tooling. It uses the Chapter 9 capability boundary, Chapter 11 durable action protocol, and Chapter 12 semantic evidence.

Primary paths are `src/policyops/security`, `policies`, `tests/security`, `docs/threat-models`, and `build/ch13`. `labs/ch13/manifest.toml` declares hashes, services, network, test credentials, commands, cleanup, gates, and fault scenarios.

## External behavior and interfaces

The policy service accepts an `AuthorizationQuery` and returns `allow`, `deny`, or `require_approval` with stable reason codes and obligations. The egress proxy accepts only calls carrying a short-lived signed grant bound to the approved action and destination. The CLI exposes `policyops security test`, `policyops capability revoke`, `policyops session quarantine`, and `policyops incident collect`. Public API errors reveal a safe reason category, while detailed evidence remains restricted.

## Required drill

Use a malicious document and malicious web/tool observation to request private data exfiltration through an otherwise allowed communication tool. Attempt forged identity, cross-tenant retrieval, stale approval, preview substitution, malicious extension installation, browser/profile confusion, secret access, redirect or DNS-based egress escape, duplicate effect, and resource exhaustion. Include one prohibited-content or regulated-advice case and one benign near-neighbor. The evidence must show which leg of the lethal trifecta was made structurally unavailable.

## Required artifacts

Deliver the threat model, frozen attack corpus, authorization and egress policy bundle, Linux sandbox profile, SBOM, dependency and capability allowlists, integrity and revocation records, security report, residual-risk record, and incident playbook.

## Acceptance criteria and traceability

- **AC-01 (CH13-FR-002, CH13-FR-003, CH13-FR-004, CH13-SEC-001, CH13-SEC-002):** Given the poisoned document or malicious web/tool observation, when PolicyOps processes it, then its text cannot grant authority, private cross-tenant data remains unavailable, and undeclared exfiltration is denied.
- **AC-02 (CH13-FR-005, CH13-SEC-004):** Given forged, stale, replayed, changed, or wrong-tenant approval, when execution is attempted, then the action fails before an effect.
- **AC-03 (CH13-FR-006, CH13-FR-007, CH13-FR-008, CH13-SEC-003, CH13-SEC-004, CH13-SEC-005):** Given sandbox escape, filesystem, network, and secret probes, when the attack harness runs, then undeclared access fails and supplied secrets are absent from outputs and telemetry.
- **AC-04 (CH13-FR-009):** Given a tampered or revoked extension, when discovery or invocation occurs, then integrity or revocation policy blocks it, including in an already-open session.
- **AC-05 (CH13-FR-010, CH13-SEC-006):** Given the frozen corpus, when security verification runs, then no high-impact attack creates an unauthorized effect, prohibited cases fail safely, and the benign false-positive ceiling holds.
- **AC-06 (CH13-FR-011, CH13-FR-012):** Given a detected attack, when containment runs, then the session is quarantined, capability is revoked, redacted evidence is preserved, and a regression record is produced.
- **AC-07 (CH13-NFR-001, CH13-NFR-002, CH13-NFR-003, CH13-NFR-004, CH13-NFR-005, CH13-NFR-006):** Given a clean checkout, when the fixture verifier runs, then it requires no paid credentials, produces the declared evidence, and states only the tested isolation claims.
- **AC-08 (CH13-FR-013, CH13-SEC-004):** Given stable and release-candidate MCP authorization fixtures, wrong resource audience and token passthrough always fail; issuer mismatch and issuer-bound client-credential substitution additionally fail only in the explicitly selected release-candidate profile.
- **AC-08 (CH13-FR-001):** Given the versioned threat model, every supplied attack and benign neighbor resolves to an asset, actor, entry point, trust boundary, autonomy tier, abuse case, control, test ID, result, and residual-risk owner; an unmapped high-impact case fails the security gate.

## Success metrics

- Zero unauthorized high-impact effects across the supplied attack corpus.
- Zero supplied secret values in prompts, outputs, logs, traces, or reports.
- 100% denial of undeclared filesystem and network probes.
- Revocation prevents every subsequent supplied invocation, including cached-session attempts.
- Prohibited cases fail safely while the predeclared benign false-positive ceiling holds.
- Every attack result links to a threat, control, test, evidence record, and residual-risk statement.

## Execution contract

Core duration is **4-6 hours**. Prerequisites are Linux containers, a non-root image, a syscall restriction profile, internal network, egress proxy, policy engine, attack fixtures, and pinned SBOM tooling.

```text
uv sync --frozen
uv run policyops env up --lab ch13 --profile fixture
uv run policyops verify ch13 --profile fixture --junit build/ch13/junit.xml --evidence build/ch13
uv run policyops fault ch13 --scenario all
uv run policyops env down --lab ch13
```

Pull requests run `verify-ch13` and all earlier gates. The extension repeats the corpus against a Kind sandbox or cloud workload-identity profile and documents residual differences without weakening identity, egress, secret, revocation, or supply-chain gates.

## Dependencies and handoff

The project consumes accepted Chapter 9 capability contracts, Chapter 11 action and approval records, Chapter 12 telemetry controls, and prior tenant and data boundaries. It produces the threat model, attack corpus, policy and sandbox bundles, SBOM, dependency and capability allowlists, security report, incident playbook, and residual-risk record. Register them in `capstone/traceability.yaml`, compare with `ed2-v1.0-ch13-solution`, and tag `ch13-complete`. [Chapter 14](../ch14-policyops-deployment-recovery/prd.md) exercises the same controls under load, failure, upgrade, and restore conditions.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Passing a fixed corpus creates false confidence | Declare tested properties, retain residual risks, and avoid universal security claims. |
| Egress allowlist is bypassed by redirect or name resolution | Resolve and pin policy-approved addresses per request, block redirects, and revalidate connections. |
| Approval dialogs train users to approve everything | Default to structural policy; reserve focused approval for bounded high-impact exceptions. |
| Secret filtering becomes the only control | Keep secrets outside prompts and sandboxes; filtering is a final detection layer. |
| Security policy blocks benign work | Freeze a near-neighbor corpus and a false-positive ceiling before tuning controls. |

## Delivery milestones

1. Freeze threat model, attack IDs, safety thresholds, benign ceiling, and residual-risk format.
2. Implement content authority labels, identity-first policy queries, and capability obligations.
3. Implement sandbox, egress, credential, integrity, allowlist, and revocation enforcement.
4. Attack approval binding, cross-tenant paths, extensions, resources, and telemetry.
5. Produce SBOM, report, incident drill, regression records, and capstone evidence.

## Future extensions

Repeat the corpus on Kind or a cloud workload-identity profile, add browser/computer-use containment, test an independently hosted MCP server, and integrate signed transparency logs. Extensions must report environment-specific residual risk rather than implying equivalent isolation.
