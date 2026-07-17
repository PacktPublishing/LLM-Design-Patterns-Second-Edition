# Chapter 8 Design: Governed Memory Lab

This implementation keeps the Chapter 8 project focused on the durable architectural pattern rather than on a specific memory product. The fixture path uses an in-process ledger, but the public seams match the production design: authorizer, repository/ledger, retriever, context-source adapter, deletion receipt, and verifier.

## Reader-facing flow

1. Propose a memory write with tenant, subject, purpose, scope, sensitivity, provenance, confidence, and optional consent.
2. Evaluate the proposal with a pure authorizer.
3. Persist only allowed mutations to the ledger.
4. Project active records into typed views by memory kind.
5. Recall task-relevant records through tenant, scope, purpose, sensitivity, time, and status filters.
6. Label recalled memory as untrusted state before it enters context.
7. Correct, consolidate, quarantine, export, or delete records with evidence.

## Files

| Area | Path |
|---|---|
| Schemas | `src/policyops/memory/schemas.py` |
| Service and verifier | `src/policyops/memory/service.py` |
| Public API | `src/policyops/memory/__init__.py` |
| Tests | `tests/memory/test_governed_memory.py` |
| Lab guide | `labs/ch08/README.md` |
| Lab manifest | `labs/ch08/manifest.toml` |

## Key design decisions

- Use one typed ledger and derive views from lifecycle state instead of creating separate memory stores.
- Make the authorizer pure so consent, scope, sensitivity, confidence, and poisoning decisions are reproducible.
- Enforce expiry at recall time so correctness does not depend on background cleanup.
- Treat recalled memory as untrusted state with no ability to grant tool authority, approvals, or system instructions.
- Keep deletion receipts content-free while preserving IDs and hashes for auditability.

## Verification coverage

The Chapter 8 verifier covers:

- consented and denied writes;
- poisoning quarantine and secret rejection;
- tenant, subject, scope, purpose, sensitivity, and time filtering;
- optimistic concurrency conflicts;
- correction through superseded records;
- consolidation with source links;
- deletion of derived records and content-free receipts;
- Chapter 5 `ContextSource` compatibility;
- fixture evidence and hard gates for isolation, authority, and deletion.
