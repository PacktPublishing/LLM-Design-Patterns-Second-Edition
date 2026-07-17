# Chapter 14 Lab: Deploy and Recover the PolicyOps Service

This lab turns the cumulative PolicyOps implementation into an operable production-shaped system. The fixture verifier models the key reliability contracts locally so readers can test failure behavior without paid model credentials.

## What you build

- A declared API, worker, database, model gateway, sandbox, egress, ticket, telemetry, release, and backup topology.
- A bounded admission controller and durable queue.
- Worker claims with fencing and idempotent effect delivery.
- Retry classification, circuit breakers, provider fallback, and explicit degraded/unavailable modes.
- Liveness, startup, readiness, dependency, and safe-to-resume health reports.
- Migration, image, canary rollback, backup, restore, load, chaos, and runbook evidence.

## Run

```bash
uv run policyops verify ch14 --profile fixture --junit build/ch14/junit.xml --evidence build/ch14
uv run policyops fault ch14 --scenario all
```

## Evidence

The verification command writes:

- `topology.json`
- `admission_queue.json`
- `retry_breaker_policy.json`
- `model_route.json`
- `health_reports.json`
- `migration_reports.json`
- `image_records.json`
- `canary_report.json`
- `backup_catalogs.json`
- `restore_reports.json`
- `load_report.json`
- `chaos_results.json`
- `operator_runbooks.json`
- `deployment_scorecard.json`

## Production lesson

Production readiness is not a successful demo. The system must reject overload before it becomes durable work, preserve one business effect under redelivery, route degraded model behavior honestly, distinguish health from safe recovery, roll back bad images, and prove that backups restore before trusting them.
