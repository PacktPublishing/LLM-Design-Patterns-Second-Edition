# Chapter 13 Lab: Defend Against Indirect Prompt Injection

This lab attacks the composed PolicyOps system with malicious documents, malicious web/tool observations, poisoned memory, approval attacks, egress probes, sandbox probes, revoked extensions, MCP authorization mistakes, and benign near-neighbors.

## GitHub evidence

- Source implementation: [src/policyops/security](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/security)
- Primary tests: [tests/security/test_security.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/security/test_security.py)
- Recorded verification evidence: [build/ch13](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch13) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch13/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch13/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch13/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch13-prompt-injection-defense/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch13-prompt-injection-defense/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch13-prompt-injection-defense/design.md)

## What you build

- A versioned threat model and frozen attack corpus.
- Provenance and trust metadata for untrusted content.
- An identity-first policy decision point.
- Exact-preview approval verification.
- Capability, sandbox, egress, secret, integrity, and revocation controls.
- Stable and release-candidate MCP authorization tests.
- A redacted security report, residual-risk record, and incident playbook.

## Run

```bash
uv run policyops verify ch13 --profile fixture --junit build/ch13/junit.xml --evidence build/ch13
uv run policyops fault ch13 --scenario all
```

## Evidence

The verification command writes:

- `threat_model.json`
- `attack_corpus.json`
- `authorization_policy.json`
- `security_policy_bundle.json`
- `sandbox_profile.json`
- `sbom.json`
- `integrity_allowlist.json`
- `security_report.json`
- `mcp_authorization.json`
- `incident_playbook.json`
- `residual_risks.json`
- `security_events.json`

## Production lesson

Prompt injection defense is not a better prompt. The production pattern is to separate instructions from data, authenticate identity outside the model, authorize capabilities outside the model, bind approval to exact effects, deny undeclared filesystem and network access, keep secrets out of model-visible channels, and treat every security claim as scoped evidence.
