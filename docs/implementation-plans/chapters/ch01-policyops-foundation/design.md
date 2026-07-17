# Chapter 1 Design: PolicyOps Foundation

**Sources:** [PRD](./prd.md) · [Architecture](./architecture.md)  
**Status:** Design reviewed and accepted for fixture-profile implementation  
**Profile:** `fixture` (mandatory, offline, deterministic)

## Design summary

Build a modular-monolith FastAPI service with a provider-neutral `ModelClient` port, Pydantic domain contracts (`RunContext`, `ModelRequest`, `Answer`, `Citation`, `Usage`, typed failures), a deterministic replay adapter, validated configuration with a non-secret fingerprint, redacted OpenTelemetry spans, and a `policyops` CLI that runs `env up` / `verify` / `fault` / `env down` for lab `ch01`.

No database, retrieval, evaluation gates, routing, or tools. Later chapters extend these contracts; they do not fork them.

## Design review findings

| ID | Finding | Severity | Resolution |
|---|---|---|---|
| DR-01 | Body-supplied `tenant_id` must not override authenticated headers | High | Identity comes from `X-Tenant-Id` / `X-Actor-Id` headers only; body mismatches → 403 before adapter call |
| DR-02 | Replay faults must not be client-selectable in production mode | High | Fault scenario selected only via composition/`POLICYOPS_FAULT_SCENARIO` in test/fault CLI |
| DR-03 | Timestamp drift breaks determinism | Medium | Fake clock + canonical JSON helpers exclude wall-clock fields from hash assertions |
| DR-04 | Optional local adapter must share contract suite | Medium | Same pytest parametrization over `replay` (and optional adapters when enabled) |
| DR-05 | Secrets in readiness/config fingerprint | High | Fingerprint hashes non-secret config keys only; `.env.example` never holds real credentials |
| DR-06 | Partial answers on invalid model output | High | Fail closed: `MODEL_OUTPUT_INVALID` → 502, no partial payload |
| DR-07 | Provider SDK leakage | High | Import-boundary test: forbid provider packages outside `adapters/` |

## Module layout

```text
src/policyops/
  contracts/          # RunContext, ModelRequest, Answer, errors, ModelClient protocol
  config/             # load, validate, fingerprint
  adapters/replay/    # deterministic fixture adapter
  adapters/local/     # optional stub behind same port
  services/answer.py  # application service
  api/                # FastAPI routes, identity deps, error mapping
  telemetry/          # redacted span helpers
  cli/                # policyops env/verify/fault commands
labs/ch01/
  manifest.toml
  fixtures/           # tenants, actors, policy excerpt, replay scenarios
tests/contract/
tests/api/
tests/fault/
capstone/traceability.yaml
```

## Key interfaces

```python
class ModelClient(Protocol):
    async def generate(self, request: ModelRequest, context: RunContext) -> ModelResult: ...
```

`ModelResult` is a discriminated union: `success` with validated `Answer` + `Usage`, or `failure` with stable code, retry class, safe message, and correlation token.

HTTP:

| Endpoint | Behavior |
|---|---|
| `POST /v1/answer` | Validate identity + body → answer service → 200 / 4xx / 502 / 503 |
| `GET /health/live` | Process up |
| `GET /health/ready` | Config valid + adapter available (non-generative) |

## Verification gates (fixture)

1. Schema round-trips and required-field rejection  
2. Replay success + fault scenarios (invalid JSON, schema-invalid, timeout, upstream error)  
3. Identity/tenant rejection with zero adapter calls  
4. Health live/ready + OpenAPI snapshot  
5. Import-boundary and secret scan  
6. Canonical JSON determinism under fake clock  
7. CLI `verify ch01 --profile fixture` exits 0 and writes `build/ch01/` evidence  

## Handoff to Chapter 2

Stable `RunContext`, answer/error shapes, and baseline scorecard/trace attributes for evaluation-driven development.
