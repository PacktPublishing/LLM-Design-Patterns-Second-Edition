# Chapter 13 Design: Indirect Prompt-Injection Defense Lab

This implementation hardens the cumulative PolicyOps path against indirect prompt injection with deterministic fixture controls. The lab does not claim universal sandbox resistance. It proves the named structural controls in the supplied corpus: provenance labels, instruction/data separation, identity-first authorization, exact-preview approval, sandbox and egress boundaries, secret minimization, integrity and revocation checks, MCP authorization profile tests, incident containment, and residual-risk evidence.

## Reader-facing flow

1. Freeze a versioned threat model and attack corpus.
2. Wrap retrieved, recalled, web, tool, and extension content in provenance and trust metadata.
3. Ask the policy decision point to authorize the proposed action from authenticated context, not model text.
4. Bind human approval to an exact canonical preview and reject stale, replayed, forged, or changed approvals.
5. Issue a narrow capability grant only after authorization and approval.
6. Run the action in a non-root, read-only-root, default-deny sandbox.
7. Route outbound traffic through an egress policy point bound to the grant and destination.
8. Keep fixture secrets out of prompts, outputs, logs, traces, and reports.
9. Verify allowlists, signatures, SBOM records, and revocation before discovery and invocation.
10. Run stable and release-candidate MCP authorization checks as explicit profiles.
11. Quarantine the detected attack session, revoke capabilities, preserve redacted evidence, and create a regression record.

## Files

| Area | Path |
|---|---|
| Schemas | `src/policyops/security/schemas.py` |
| Runtime and verifier | `src/policyops/security/service.py` |
| Public API | `src/policyops/security/__init__.py` |
| Tests | `tests/security/test_security.py` |
| Lab guide | `labs/ch13/README.md` |
| Lab manifest | `labs/ch13/manifest.toml` |

## Key design decisions

- Treat untrusted content as evidence only; it cannot widen identity, authority, approval, destinations, or secret access.
- Keep policy decisions outside model output so authorization remains deterministic.
- Use exact-preview approval as a second check, not as the first security boundary.
- Combine sandbox denial and egress denial so the lethal trifecta loses at least one leg.
- Use profile-gated MCP authorization tests: the stable profile proves protected-resource discovery, PKCE, audience binding, and token-passthrough rejection; the release-candidate profile adds issuer and client binding checks.
- Record residual risk explicitly so fixture results are not overstated.

## Verification coverage

The Chapter 13 verifier covers:

- threat/control/test/residual-risk mapping;
- poisoned document and malicious observation handling;
- cross-tenant denial;
- stale, replayed, forged, and changed approval rejection;
- filesystem, process, network, and secret probes;
- egress redirect and destination denial;
- tampered and revoked extension handling;
- MCP stable and release-candidate authorization fixtures;
- prohibited-content safe failure and benign near-neighbor ceiling;
- incident quarantine, revocation, evidence preservation, and regression creation;
- SBOM, allowlist, security report, and redacted security event evidence.
