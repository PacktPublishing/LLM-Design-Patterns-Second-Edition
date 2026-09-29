# Chapter 5 Lab: Context Planner

This lab replaces a monolithic prompt with a deterministic current-call context
planner. The planner treats authority, trust, provenance, sensitivity, token
budget, compaction, and stable-prefix layout as explicit engineering concerns.

Run it with:

```powershell
uv run policyops verify ch05 --profile fixture --junit build/ch05/junit.xml --evidence build/ch05
uv run policyops fault ch05 --scenario all
```

Evidence is written under `build/ch05/`: rendered fixture context, redacted
manifest, token report, fault drill results, JUnit, fingerprints, and the shared
trace-redaction sample. The mandatory path is offline and does not require a
hosted model, vector database, memory store, or capability protocol.

## GitHub evidence

- Source implementation: [src/policyops/context](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/context)
- Primary tests: [tests/context/test_context_planner.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/context/test_context_planner.py)
- Recorded verification evidence: [build/ch05](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch05) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch05/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch05/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch05/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch05-context-planner/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch05-context-planner/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch05-context-planner/design.md)
