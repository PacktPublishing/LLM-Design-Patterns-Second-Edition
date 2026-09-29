# Chapter 9 Lab: Build a Secure PolicyOps Extension Pack

This lab turns PolicyOps ticket creation into a governed capability pack. The typed tool is canonical; MCP, skills, plugins, and hooks add interoperability, guidance, distribution, and lifecycle controls without changing the final authorization boundary.

## GitHub evidence

- Source implementation: [src/policyops/extensions](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/extensions)
- Primary tests: [tests/extensions/test_secure_extension_pack.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/extensions/test_secure_extension_pack.py)
- Recorded verification evidence: [build/ch09](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch09) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch09/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch09/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch09/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch09-secure-extension-pack/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch09-secure-extension-pack/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch09-secure-extension-pack/design.md)

## What you build

- `preview_policy_ticket` and `create_policy_ticket` contracts with canonical effect hashes.
- Approval verification bound to actor, tenant, operation, audience, scope, expiry, nonce, and exact effect hash.
- Direct and MCP-style adapters that converge on the same secured `ToolPort`.
- Deterministic pre-action and post-action hooks.
- A signed plugin manifest with file hashes, compatibility, permission checks, rollback, and revocation behavior.
- A narrow Agent Skill activation benchmark.
- A safe `CapabilityContextSource` that exposes metadata but cannot invoke tools or leak approvals.

## Run

```bash
uv run policyops verify ch09 --profile fixture --junit build/ch09/junit.xml --evidence build/ch09
uv run policyops fault ch09 --scenario all
```

## Evidence

The verification command writes:

- `tool_contract.json`
- `activation_scorecard.json`
- `package_verification.json`
- `compatibility_report.json`
- `extension_scorecard.json`
- `audit_events.jsonl`

## Production lesson

Use the smallest capability surface that satisfies the requirement. Skills can teach; hooks can enforce bounded lifecycle checks; plugins can distribute versioned assets; MCP can provide interoperable discovery and invocation. None of them should bypass the same typed tool, exact-effect approval, idempotency, and audit boundary.
