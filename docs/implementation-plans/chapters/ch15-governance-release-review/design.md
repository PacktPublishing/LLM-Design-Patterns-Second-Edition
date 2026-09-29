# Chapter 15 Design: Governance Release Review Lab

This implementation turns governance into an executable release gate. It indexes the accepted technical evidence from the earlier chapters, verifies owners and signatures, checks high-risk paths through a typed control graph, processes correction/deletion receipts across declared stores, generates a transparency notice from the inventory, and emits a deterministic `GO` or `NO-GO` package.

## Reader-facing flow

1. Define the system inventory, high-risk use cases, owners, approval matrix, controls, and evidence records.
2. Bind evidence signatures to artifact hash, schema, configuration scope, issuer role, issued time, expiry, and purpose.
3. Build a control-to-evidence graph from risks to owners, controls, tests, and current evidence.
4. Classify material changes such as autonomy and deployment changes.
5. Run invalid-evidence drills for ownerless, stale, tampered, failed, self-approved, and partial-rights cases.
6. Process correction and deletion requests across every primary and derived store in the inventory.
7. Generate the transparency notice from machine-readable source records.
8. Produce a deterministic signed release decision package after remediation.

## Files

| Area | Path |
|---|---|
| Schemas | `src/policyops/governance/schemas.py` |
| Runtime and verifier | `src/policyops/governance/service.py` |
| Public API | `src/policyops/governance/__init__.py` |
| Tests | `tests/governance/test_governance.py` |
| Lab guide | `labs/ch15/README.md` |
| Lab manifest | `labs/ch15/manifest.toml` |

## Key design decisions

- Treat structured records as the source of truth and generated reports as views.
- Fail closed when owners, signatures, evidence freshness, configuration scope, or rights coverage is invalid.
- Keep technical controls in earlier chapters; Chapter 15 verifies and governs their evidence.
- Enforce separation of duties so an agent or evidence producer cannot approve its own release.
- Make identical immutable inputs produce identical reason ordering and decision digest.

## Verification coverage

The Chapter 15 verifier covers:

- inventory, risk, owner, approval, control, evidence, rights, and decision schemas;
- current human owner coverage for high risks and controls;
- evidence hash, signature, issuer role, scope, expiry, and passing-result checks;
- `NO-GO` decisions for missing owner, stale evidence, tampered evidence, failed tests, self-approval, and missed derived stores;
- correction and deletion receipts across every declared store;
- transparency notice consistency with the inventory;
- deterministic final `GO` decision digest and immutable decision evidence.
