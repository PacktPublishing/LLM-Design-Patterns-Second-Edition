# Chapter 9 Lab: Build a Secure PolicyOps Extension Pack

This lab turns PolicyOps ticket creation into a governed capability pack. The typed tool is canonical; MCP, skills, plugins, and hooks add interoperability, guidance, distribution, and lifecycle controls without changing the final authorization boundary.

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
