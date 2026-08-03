# Chapter 8 Lab: Add Governed Long-Term Memory

This lab adds governed memory to PolicyOps without turning remembered text into authority. The implementation uses one append-only ledger, typed views, explicit mutation decisions, scoped recall, correction, deletion receipts, and poisoning controls.

## GitHub evidence

- Source implementation: [src/policyops/memory](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/memory)
- Primary tests: [tests/memory/test_governed_memory.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/memory/test_governed_memory.py)
- Recorded verification evidence: [build/ch08](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch08) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch08/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch08/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch08/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch08-governed-long-term-memory/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch08-governed-long-term-memory/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch08-governed-long-term-memory/design.md)

## What you build

- A pure mutation authorizer for `ADD`, `UPDATE`, `DELETE`, and `NOOP` decisions.
- A fixture ledger that behaves like the durable repository port used in production.
- Governed recall filtered by tenant, subject, purpose, scope, sensitivity, status, and time.
- Correction, consolidation, fake-clock expiry, quarantine, export, and deletion receipts.
- A Chapter 5-compatible `MemoryContextSource` that labels memory as untrusted state.

## Run

```bash
uv run policyops verify ch08 --profile fixture --junit build/ch08/junit.xml --evidence build/ch08
uv run policyops fault ch08 --scenario all
```

## Evidence

The verification command writes:

- `memory_events.jsonl`
- `memory_views.json`
- `recall_report.json`
- `deletion_receipt.json`
- `memory_scorecard.json`
- standard fingerprints, trace-redaction evidence, and JUnit output

## Production lesson

Memory is useful state, not proof and not permission. The safe pattern is to put every write through deterministic governance, label every recalled item as untrusted, and prove that deletion, correction, quarantine, and tenant isolation work before the agent loop can depend on memory.
