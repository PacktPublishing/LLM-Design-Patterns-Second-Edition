# Chapter 1 Design: PolicyOps Foundation

**Sources:** [PRD](./prd.md) · [Architecture](./architecture.md)
**Status:** Implemented and fixture-verified (`pytest` 36 passed; `policyops verify/fault ch01`)
**Profile:** `fixture` (mandatory, offline, deterministic)

## Design summary

Build a modular-monolith FastAPI service with a provider-neutral `ModelClient` port, Pydantic domain contracts (`RunContext`, `ModelRequest`, `Answer`, `Citation`, `Usage`, typed failures), a deterministic replay adapter, validated configuration with a non-secret fingerprint, redacted OpenTelemetry spans, and a `policyops` CLI that runs `env up` / `verify` / `fault` / `env down` for lab `ch01`.

No database, retrieval, evaluation gates, routing, or tools. Later chapters extend these contracts; they do not fork them.

## Scaffold gap analysis (post-pull)

| Area | Latest PRD/Architecture | Scaffold (`50f95e2`) | Action |
|---|---|---|---|
| Domain contracts | Versioned envelope + semantic Answer rules | Present in `contracts/` | Keep; align error codes |
| Error taxonomy | `DEADLINE_EXCEEDED`, `MODEL_BAD_OUTPUT`, `MODEL_CAPACITY` | Still uses `MODEL_TIMEOUT` / `MODEL_OUTPUT_INVALID` / `MODEL_UPSTREAM_ERROR` | **Update contracts + mapping** |
| `ModelClient` port | `generate` + cancellation; readiness non-generative | `generate` + `ready` on protocol | Keep |
| Replay adapter | Hashed scenario resolution + faults | Missing | Implement |
| Answer service + API | `/v1/answer`, live/ready, identity headers | Missing | Implement |
| Telemetry | Redacted spans: `http.request`, `policyops.answer`, `model.generate`, `answer.validate` | Missing | Implement |
| CLI + labs/fixtures | Manifest-driven verify/fault/evidence | Missing (`policyops` entry points to absent CLI) | Implement |
| Tests + OpenAPI snapshot | Contract/API/fault/boundary gates | Missing | Implement |
| Container / Compose | Non-root, optional | Optional for fixture gate; add minimal Dockerfile | Implement smoke path |

## Design review findings

| ID | Finding | Severity | Resolution |
|---|---|---|---|
| DR-01 | Body-supplied `tenant_id` must not override authenticated headers | High | Identity from `X-Tenant-Id` / `X-Actor-Id` (+ roles/authz headers); body mismatch → 403 before adapter call |
| DR-02 | Replay faults must not be client-selectable in normal mode | High | Fault via `POLICYOPS_FAULT_SCENARIO` / fault CLI only |
| DR-03 | Timestamp drift breaks determinism | Medium | Fake clock helper; canonical JSON excludes wall-clock from hash assertions |
| DR-04 | Optional local adapter must share contract suite | Medium | Parametrize port tests over `replay` (+ `local` when enabled) |
| DR-05 | Secrets in readiness/config fingerprint | High | Fingerprint hashes non-secret keys only; `.env.example` placeholders only |
| DR-06 | Partial answers on invalid model output | High | Fail closed: `MODEL_BAD_OUTPUT` → 502, no partial payload |
| DR-07 | Provider SDK leakage | High | Import-boundary test forbids provider packages outside `adapters/` |
| DR-08 | Scaffold error codes diverge from architecture | High | Rename to `DEADLINE_EXCEEDED` (503), `MODEL_BAD_OUTPUT` (502), `MODEL_CAPACITY` (503); keep `VALIDATION_ERROR`/`UNAUTHORIZED`/`FORBIDDEN`/`CONFIG_INVALID`/`INTERNAL_ERROR` |
| DR-09 | `load_settings()` fails if fixtures absent before lab setup | Medium | CLI `env up` materializes fixture paths; API startup uses composition that tolerates test tmp packs |
| DR-10 | Port protocol needs `ready()` for non-generative readiness | Low | Keep `ready()` on `ModelClient` (architecture readiness invariant) |

## Error → HTTP mapping

| Code | Retry class | HTTP | When |
|---|---|---|---|
| `VALIDATION_ERROR` | none | 400 | Bad body / content-type |
| `UNAUTHORIZED` | none | 401 | Missing identity headers |
| `FORBIDDEN` | none | 403 | Tenant/actor conflict or insufficient scope |
| `MODEL_BAD_OUTPUT` | none | 502 | Invalid/malformed adapter output after parse |
| `DEADLINE_EXCEEDED` | caller | 503 | Deadline / timeout |
| `MODEL_CAPACITY` | upstream | 503 | Upstream unavailable / capacity |
| `CONFIG_INVALID` | config | 503 | Bad/missing secure config |
| `INTERNAL_ERROR` | none | 500 | Unexpected server fault (safe message only) |

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
  util/canonical.py   # canonical JSON + fake clock
labs/ch01/
  manifest.toml
  fixtures/           # tenants, actors, policy excerpt, replay scenarios
tests/contract/
tests/api/
tests/fault/
tests/boundary/
capstone/traceability.yaml
Dockerfile
.env.example
```

## Key interfaces

```python
class ModelClient(Protocol):
    async def generate(self, request: ModelRequest, context: RunContext) -> ModelResult: ...
    async def ready(self) -> bool: ...
```

`ModelResult` is a discriminated union: `success` with validated `Answer` + `Usage`, or `failure` with stable code, retry class, safe message, and correlation token.

HTTP:

| Endpoint | Behavior |
|---|---|
| `POST /v1/answer` | Validate identity + body → answer service → 200 / 4xx / 502 / 503 |
| `GET /health/live` | Process up |
| `GET /health/ready` | Config valid + adapter available (non-generative) |

## Implementation sequence completed

1. Align `ErrorCode` with architecture taxonomy (DR-08).
2. Fixtures + replay adapter + local stub.
3. Answer service, composition root, FastAPI app.
4. Telemetry facade + evidence writer.
5. CLI (`env`, `verify`, `fault`) + `labs/ch01/manifest.toml`.
6. Contract/API/fault/boundary tests + OpenAPI snapshot.
7. Chapter README (run instructions, teaching points, insights, reader questions).
8. Register checkpoint row in `capstone/traceability.yaml`.

## Verification gates (fixture)

1. Schema round-trips and required-field rejection
2. Replay success + fault scenarios (invalid JSON, schema-invalid, timeout, upstream/capacity)
3. Identity/tenant rejection with zero adapter calls
4. Health live/ready + OpenAPI snapshot
5. Import-boundary and secret scan
6. Canonical JSON determinism under fake clock
7. CLI `verify ch01 --profile fixture` exits 0 and writes `build/ch01/` evidence: JUnit, result JSON, scorecard, fixture/dependency/configuration fingerprints, and trace-redaction metadata

## Handoff to Chapter 2

Stable `RunContext`, answer/error shapes (`DEADLINE_EXCEEDED` / `MODEL_BAD_OUTPUT` / `MODEL_CAPACITY`), and baseline scorecard/trace attributes for evaluation-driven development.
