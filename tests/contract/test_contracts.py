"""Contract tests for domain schemas and ModelClient port."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from policyops.adapters import LocalModelClient, ReplayModelClient
from policyops.contracts import (
    Answer,
    AuthorizationContext,
    Budget,
    ModelRequest,
    RunContext,
)
from policyops.util import canonical_json

FIXTURES = Path("labs/ch01/fixtures")


def _context(**overrides) -> RunContext:
    base = dict(
        request_id="req_fixture_001",
        trace_id="trace_fixture_001",
        tenant_id="tenant_alpha",
        actor_id="actor_reader",
        roles=["policy-reader"],
        purpose="policy-question",
        configuration_id="sha256:test",
        configuration_versions={"model": "replay-v1", "policy": "policy-v1"},
        deadline_at=datetime(2030, 1, 1, 0, 0, 5, tzinfo=UTC),
        budget=Budget(max_input_tokens=2048, max_output_tokens=512),
        authorization_context=AuthorizationContext(
            scopes=["policy:read"], decision_id="authz-fixture-1"
        ),
    )
    base.update(overrides)
    return RunContext(**base)


def test_run_context_round_trip() -> None:
    ctx = _context()
    data = ctx.model_dump(mode="json")
    again = RunContext.model_validate(data)
    assert again.tenant_id == "tenant_alpha"
    assert "request_id" in canonical_json(data)


def test_answer_rejects_abstain_without_reason() -> None:
    with pytest.raises(Exception):
        Answer(answer_type="abstain", text="unknown")


def test_answer_rejects_direct_with_reason() -> None:
    with pytest.raises(Exception):
        Answer(answer_type="direct", text="ok", abstention_reason="x")


def test_model_request_rejects_extra_fields() -> None:
    with pytest.raises(Exception):
        ModelRequest.model_validate({"question": "hi", "provider_raw": {}})


@pytest.mark.parametrize("client_factory", [ReplayModelClient, LocalModelClient])
@pytest.mark.asyncio
async def test_adapter_success_contract(client_factory) -> None:
    client = client_factory(FIXTURES)
    assert await client.ready() is True
    result = await client.generate(
        ModelRequest(question="How many remote days are allowed?"),
        _context(),
    )
    assert result.kind == "success"
    assert result.answer.citations
    assert result.usage.input_tokens >= 0


@pytest.mark.asyncio
async def test_replay_timeout_fault() -> None:
    client = ReplayModelClient(FIXTURES, fault_scenario="timeout")
    result = await client.generate(ModelRequest(question="x"), _context())
    assert result.kind == "failure"
    assert result.failure.code.value == "DEADLINE_EXCEEDED"


@pytest.mark.asyncio
async def test_replay_bad_output_fault() -> None:
    client = ReplayModelClient(FIXTURES, fault_scenario="invalid_json")
    result = await client.generate(ModelRequest(question="x"), _context())
    assert result.kind == "failure"
    assert result.failure.code.value == "MODEL_BAD_OUTPUT"


@pytest.mark.asyncio
async def test_local_adapter_tags_usage_adapter() -> None:
    client = LocalModelClient(FIXTURES)
    result = await client.generate(
        ModelRequest(question="How many remote days are allowed?"), _context()
    )
    assert result.kind == "success"
    assert result.usage.adapter == "local"


@pytest.mark.asyncio
async def test_local_adapter_supports_abstain_without_replay() -> None:
    client = LocalModelClient(FIXTURES)
    result = await client.generate(
        ModelRequest(question="What is the parental leave rule?"),
        _context(),
    )
    assert result.kind == "success"
    assert result.answer.answer_type == "abstain"
    assert result.answer.abstention_reason == "policy_excerpt_missing_fact"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fault", "code"),
    [
        ("timeout", "DEADLINE_EXCEEDED"),
        ("invalid_json", "MODEL_BAD_OUTPUT"),
        ("schema_invalid", "MODEL_BAD_OUTPUT"),
        ("upstream_error", "MODEL_CAPACITY"),
    ],
)
async def test_local_adapter_faults_map_to_typed_failures(fault: str, code: str) -> None:
    client = LocalModelClient(FIXTURES, fault_scenario=fault)
    result = await client.generate(ModelRequest(question="x"), _context())
    assert result.kind == "failure"
    assert result.failure.code.value == code


@pytest.mark.asyncio
async def test_local_adapter_ready_fails_closed_when_policy_missing(tmp_path: Path) -> None:
    client = LocalModelClient(tmp_path)
    assert await client.ready() is False


@pytest.mark.asyncio
async def test_replay_unknown_scenario_reports_capacity() -> None:
    client = ReplayModelClient(FIXTURES, fault_scenario="does_not_exist")
    result = await client.generate(ModelRequest(question="x"), _context())
    assert result.kind == "failure"
    assert result.failure.code.value == "MODEL_CAPACITY"


@pytest.mark.asyncio
async def test_replay_adapter_fails_closed_on_configuration_mismatch() -> None:
    client = ReplayModelClient(FIXTURES, configuration_id="sha256:expected")
    result = await client.generate(
        ModelRequest(question="How many remote days are allowed?"),
        _context(configuration_id="sha256:different"),
    )
    assert result.kind == "failure"
    assert result.failure.code.value == "CONFIG_INVALID"


@pytest.mark.asyncio
async def test_replay_timeout_honors_context_deadline_without_waiting_full_delay() -> None:
    client = ReplayModelClient(FIXTURES, fault_scenario="timeout")
    result = await client.generate(
        ModelRequest(question="x"),
        _context(deadline_at=datetime(2030, 1, 1, 0, 0, 0, 5_000, tzinfo=UTC)),
    )
    assert result.kind == "failure"
    assert result.failure.code.value == "DEADLINE_EXCEEDED"


@pytest.mark.asyncio
async def test_service_fails_closed_on_expired_deadline() -> None:
    from policyops.contracts import DomainError
    from policyops.services import AnswerService

    client = ReplayModelClient(FIXTURES)
    service = AnswerService(client)
    before = client.call_count
    expired = _context(deadline_at=datetime(2020, 1, 1, tzinfo=UTC))
    with pytest.raises(DomainError) as exc:
        await service.answer(ModelRequest(question="x"), expired)
    assert exc.value.code.value == "DEADLINE_EXCEEDED"
    assert exc.value.http_status == 503
    # Deadline is enforced before any model invocation.
    assert client.call_count == before
