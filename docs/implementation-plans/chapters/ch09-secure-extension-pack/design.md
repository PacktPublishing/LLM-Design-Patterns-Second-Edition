# Chapter 9 Design: Secure Extension Pack Lab

This implementation keeps the lab focused on extension architecture rather than on a specific marketplace or host. The fixture uses direct Python objects instead of a live MCP daemon, but the boundaries match the production architecture: typed tool, MCP-style adapter, skill activation, plugin verification, pre-action hook, post-action audit hook, lifecycle registry, and compatibility report.

## Reader-facing flow

1. Draft a ticket input.
2. Preview the canonical ticket effect and effect hash.
3. Bind approval to the exact actor, tenant, operation, scope, audience, expiry, nonce, and effect hash.
4. Execute through the secured `ToolPort`.
5. Run the pre-action hook before any repository write.
6. Create one ticket per idempotency key.
7. Run the post-action hook to write redacted audit evidence.
8. Verify package provenance, activation, rollback, and revocation behavior.

## Files

| Area | Path |
|---|---|
| Schemas | `src/policyops/extensions/schemas.py` |
| Runtime and verifier | `src/policyops/extensions/service.py` |
| Public API | `src/policyops/extensions/__init__.py` |
| Tests | `tests/extensions/test_secure_extension_pack.py` |
| Lab guide | `labs/ch09/README.md` |
| Lab manifest | `labs/ch09/manifest.toml` |

## Key design decisions

- Keep the typed tool as the business boundary; MCP and plugins adapt access but do not own policy.
- Bind approvals to exact canonical effects so preview drift invalidates permission.
- Use fail-closed pre-action hooks and bounded, degradable post-action hooks.
- Treat skill/plugin/MCP metadata as untrusted context.
- Keep the `2026-07-28` MCP release-candidate profile opt-in and fail closed unless selected explicitly.

## Verification coverage

The Chapter 9 verifier covers:

- direct preview/create contracts;
- MCP-style adapter convergence on the same `ToolPort`;
- missing, stale, mismatched, and replayed approvals;
- one ticket per idempotency key;
- pre-hook timeout and revocation denial;
- post-hook evidence degradation without duplicate mutation;
- signed manifest verification, tamper detection, permission checks, and revoked-package refusal;
- skill activation precision/recall and explicit-invocation rules;
- safe capability context with no approvals, grants, tokens, or invocation side effects.
