# Chapter 14 Design: Deployment and Recovery Lab

This implementation models the production reliability concerns from the chapter in a deterministic fixture path. It does not require Docker Compose for the mandatory verifier, but the code mirrors the Compose topology that readers would operate: API, database-backed queue, stateless workers, model gateway, sandbox, egress proxy, ticket service, telemetry, release controller, and backup/restore job.

## Reader-facing flow

1. Define process and network boundaries for the production-shaped topology.
2. Propagate the execution envelope across service boundaries.
3. Reject infeasible or overloaded work before it enters the durable queue.
4. Claim queued work with durable ownership and fencing.
5. Preserve one-business-effect idempotency under redelivery.
6. Classify retries and open circuit breakers before failures amplify.
7. Route model traffic only to quality-compliant fallback providers.
8. Distinguish liveness, startup, readiness, dependency health, and safe-to-resume state.
9. Gate migrations, digest-pinned images, and bad-image canaries.
10. Reject corrupt backups and validate valid restores in isolation.
11. Run load and chaos scenarios with runbook references and SLO evidence.

## Files

| Area | Path |
|---|---|
| Schemas | `src/policyops/deployment/schemas.py` |
| Runtime and verifier | `src/policyops/deployment/service.py` |
| Public API | `src/policyops/deployment/__init__.py` |
| Tests | `tests/deployment/test_deployment.py` |
| Lab guide | `labs/ch14/README.md` |
| Lab manifest | `labs/ch14/manifest.toml` |

## Key design decisions

- Use a PostgreSQL-shaped durable queue in the core model so session, claim, and outbox correctness remain transactional.
- Treat service-entry admission as the first reliability boundary; rejected overload creates no durable work row.
- Keep behavior canaries in Chapter 12 and image/schema canaries in Chapter 14.
- Restore backups into isolation before any promotion plan.
- Bind all load and recovery claims to fixture workload, declared hardware, thresholds, and evidence.

## Verification coverage

The Chapter 14 verifier covers:

- topology and network-zone declaration;
- bounded queue admission and typed `429` rejection;
- worker claim fencing and acknowledgement;
- duplicate-effect redelivery through a stable idempotency key;
- retry classification, breaker state, provider fallback, and degraded/unavailable modes;
- health/readiness distinction and safe-to-resume gating;
- migration preflight, image evidence, canary rollback, backup rejection, valid restore, RTO/RPO checks;
- load, chaos, runbook coverage, secret/network probes, and final deployment scorecard evidence.
