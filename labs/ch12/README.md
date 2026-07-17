# Chapter 12 Lab: Turn a Production Trace into a Safe Improvement

This lab builds the LLMOps loop for PolicyOps. It starts with a correlated, redacted production trace and ends with evidence that one proposed behavior improvement was either kept or reverted safely.

## What you build

- A behavior-affecting artifact registry.
- A semantic telemetry adapter for model, retrieval, memory, agent, browser/computer-use, approval, tool, sandbox, external-effect, and outcome spans.
- Pre-export redaction, tenant hashing, sampling, and cardinality controls.
- SLO records, including cost per successful outcome.
- Expert trace adjudication and trace-to-evaluation graduation.
- A bounded experiment over one writable routing surface.
- Protected grader, holdout, and evidence hashes.
- A behavior canary that rolls back a seeded bad release.
- Non-executing reconstruction that cannot call a model, tool, or external effect.

## Run

```bash
uv run policyops verify ch12 --profile fixture --junit build/ch12/junit.xml --evidence build/ch12
uv run policyops fault ch12 --scenario all
```

## Evidence

The verification command writes:

- `artifact_registry.json`
- `trace_export.jsonl`
- `privacy_report.json`
- `slo_records.json`
- `adjudication.json`
- `eval_case_from_trace.json`
- `experiment_ledger.json`
- `accepted_candidate_ledger.json`
- `canary_report.json`
- `reconstruction_report.json`
- `telemetry_outage.json`
- `harness_event_spans.json`
- `harness_retirement_adr.json`
- `observability_scorecard.json`

## Production lesson

Observability is not the same thing as improvement. A safe loop must first protect telemetry, then separate product failures from noise, freeze the evaluation evidence, measure cost and quality together, and prove that bad behavior changes roll back automatically.
