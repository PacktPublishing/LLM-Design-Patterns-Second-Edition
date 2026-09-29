# Chapter 1 — PolicyOps Foundation

Hands-on lab for the PolicyOps service shell: provider-neutral model contracts, deterministic replay, FastAPI identity boundary, and fixture verification.

## GitHub evidence

- Source implementation: [src/policyops/contracts](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/contracts), [src/policyops/adapters](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/adapters), [src/policyops/api](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/api)
- Primary tests: [tests/contract/test_contracts.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/contract/test_contracts.py), [tests/api/test_api.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/api/test_api.py), [tests/boundary/test_boundary.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/boundary/test_boundary.py), [tests/fault/test_faults.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/fault/test_faults.py), [tests/config/test_config.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/config/test_config.py)
- Recorded verification evidence: [build/ch01](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch01) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch01/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch01/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch01/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch01-policyops-foundation/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch01-policyops-foundation/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch01-policyops-foundation/design.md)

## What this code teaches

- Keep probabilistic generation behind a typed `ModelClient` port so application code never imports provider SDKs.
- Carry tenant, actor, trace, configuration, deadline, budget, and authorization on every model call via `RunContext`.
- Treat model output as untrusted: schema + semantic validation, fail closed (`MODEL_BAD_OUTPUT` → 502).
- Prefer a deterministic replay adapter for CI and reader labs; optional adapters must pass the same contract suite.
- Reject missing/conflicting identity **before** any adapter call.

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (or `pip install uv`)

No paid API keys, GPUs, or model downloads for the fixture profile.

## Run

From the repository root:

```bash
uv sync --extra dev
uv run policyops env up --lab ch01 --profile fixture
uv run policyops verify ch01 --profile fixture --junit build/ch01/junit.xml --evidence build/ch01
uv run policyops fault ch01 --scenario all
uv run policyops env down --lab ch01
```

Or run pytest directly:

```bash
uv run pytest tests -q
```

Start the API locally (replay adapter):

```bash
uv sync --extra dev
set POLICYOPS_FIXTURE_PACK=labs/ch01/fixtures
uv run uvicorn policyops.api:app --host 127.0.0.1 --port 8080
```

Example request:

```bash
curl -s http://127.0.0.1:8080/v1/answer ^
  -H "Content-Type: application/json" ^
  -H "X-Tenant-Id: tenant_alpha" ^
  -H "X-Actor-Id: actor_reader" ^
  -d "{\"question\":\"How many remote days are allowed?\"}"
```

## Insights

1. **Ports beat SDKs in the core.** Provider types stay in `adapters/`; domain code stays portable.
2. **Identity is a header concern.** Body fields cannot redefine tenant/actor; conflicts return 403 with zero model calls.
3. **Replay is honesty, not quality.** Fixture latency and answers are not claims about real models—Chapter 2 adds evaluation gates.
4. **Error taxonomy is product surface.** Stable codes (`DEADLINE_EXCEEDED`, `MODEL_BAD_OUTPUT`, `MODEL_CAPACITY`) matter more than raw exception text.
5. **Readiness must be cheap.** `/health/ready` checks config + adapter availability without generating billable tokens.

## Reader questions

1. If a new vendor SDK is added, where should its types be allowed to appear, and which tests prove the boundary?
2. Why map deadline exhaustion to `503 DEADLINE_EXCEEDED` with `retry_class=caller` instead of a generic 500?
3. What would break later chapters if `RunContext` silently dropped `configuration_id` or `authorization_context`?
4. When is it wrong to treat replay success as evidence that a production model is ready to ship?
5. How would you extend the fault CLI to inject a misconfigured secure-mode startup without putting secrets in git?
