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
