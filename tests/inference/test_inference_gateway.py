"""Chapter 4 adaptive inference gateway tests."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from policyops.contracts import AuthorizationContext, Budget, ModelRequest, RunContext
from policyops.inference import (
    AdaptiveInferenceGateway,
    CacheEntry,
    FailureReason,
    GatewayClock,
    InferenceBudget,
    InferenceRequest,
    ResponseCache,
    RiskTier,
    TaskClass,
    benchmark_gateway,
    fixture_profiles,
    run_gateway_verification,
)


def _request(**overrides) -> InferenceRequest:
    base = dict(
        request_id="req-ch04",
        tenant_id="tenant_alpha",
        actor_id="actor_reader",
        authorization_fingerprint="authz:reader",
        configuration_hash="sha256:gateway-fixture",
        policy_version="policy-v1",
        question="How many remote days are allowed?",
    )
    base.update(overrides)
    return InferenceRequest(**base)


def _context(**overrides) -> RunContext:
    base = dict(
        request_id="req_gateway_fixture",
        trace_id="trace_gateway_fixture",
        tenant_id="tenant_alpha",
        actor_id="actor_reader",
        roles=["policy-reader"],
        purpose="policy-question",
        configuration_id="sha256:gateway-test",
        configuration_versions={"model": "gateway-fixture", "policy": "policy-v1"},
        deadline_at=datetime(2030, 1, 1, 0, 0, 5, tzinfo=UTC),
        budget=Budget(max_input_tokens=2048, max_output_tokens=512),
        authorization_context=AuthorizationContext(
            scopes=["policy:read"], decision_id="authz-gateway-fixture"
        ),
    )
    base.update(overrides)
    return RunContext(**base)


def test_easy_request_exits_after_first_verified_candidate() -> None:
    gateway = AdaptiveInferenceGateway()
    result = gateway.run(_request())
    assert result.selected is not None
    assert result.selected.profile_id == "small-fast"
    assert result.early_exit is True
    assert len(result.candidates) == 1
    assert result.route == ["small-fast"]


def test_ambiguous_request_escalates_after_small_profile_fails_verifier() -> None:
    gateway = AdaptiveInferenceGateway()
    result = gateway.run(_request(question="Ambiguous exception for remote work approval?"))
    assert result.selected is not None
    assert [candidate.profile_id for candidate in result.candidates] == ["small-fast", "standard"]
    assert result.selected.profile_id == "standard"
    assert "missing_required_citation" in result.candidates[0].verifier_reasons


def test_high_risk_request_starts_with_stronger_profile_and_bypasses_cache() -> None:
    gateway = AdaptiveInferenceGateway()
    result = gateway.run(
        _request(
            request_id="req-high",
            question="Can I approve a confidential payroll policy exception?",
            risk_tier=RiskTier.HIGH,
            data_classification="confidential",
        )
    )
    assert result.selected is not None
    assert result.route == ["standard"]
    assert result.cache_status == "bypass"
    assert result.selected.reasoning_effort.value == "high"


def test_candidate_budget_limits_escalation() -> None:
    gateway = AdaptiveInferenceGateway()
    result = gateway.run(
        _request(
            question="Ambiguous exception for remote work approval?",
            budget=InferenceBudget(max_candidates=1, min_quality=0.8),
        )
    )
    assert result.selected is None
    assert result.failure_reason == FailureReason.NO_VERIFIED_CANDIDATE
    assert len(result.candidates) == 1


def test_time_budget_rejects_work_before_model_call() -> None:
    gateway = AdaptiveInferenceGateway()
    result = gateway.run(
        _request(budget=InferenceBudget(max_duration_ms=10, max_spend_units=25, max_candidates=3))
    )
    assert result.selected is None
    assert result.failure_reason == FailureReason.DEADLINE_EXCEEDED
    assert result.candidates == []


def test_spend_budget_rejects_unsafe_route() -> None:
    gateway = AdaptiveInferenceGateway()
    result = gateway.run(_request(budget=InferenceBudget(max_spend_units=0.01, max_candidates=3)))
    assert result.selected is None
    assert result.failure_reason == FailureReason.BUDGET_EXHAUSTED
    assert result.budget_exhausted is True


def test_cache_hit_is_tenant_and_configuration_scoped() -> None:
    cache = ResponseCache()
    gateway = AdaptiveInferenceGateway(cache=cache)
    first = gateway.run(_request(request_id="req-cache-1"))
    assert first.cache_status == "miss"
    warm = gateway.run(_request(request_id="req-cache-2"))
    assert warm.cache_status == "hit"
    other_tenant = gateway.run(_request(request_id="req-cache-3", tenant_id="tenant_beta"))
    assert other_tenant.cache_status == "miss"
    other_config = gateway.run(
        _request(request_id="req-cache-4", configuration_hash="sha256:new-config")
    )
    assert other_config.cache_status == "miss"


def test_expired_or_corrupt_cache_is_rejected_and_revalidated() -> None:
    clock = GatewayClock()
    cache = ResponseCache(ttl_ms=5)
    gateway = AdaptiveInferenceGateway(cache=cache, clock=clock)
    request = _request(request_id="req-cache-expire")
    first = gateway.run(request)
    assert first.selected is not None
    key = gateway.cache_key(request, "small-fast")
    entry = CacheEntry(
        key=key,
        candidate=first.selected.model_copy(update={"valid": False}),
        created_ms=0,
        expires_ms=100,
    )
    cache.inject(entry)
    rejected = gateway.run(request)
    assert rejected.cache_status == "rejected"
    assert rejected.selected is not None
    clock.advance(10)
    expired = gateway.run(request)
    assert expired.cache_status in {"miss", "rejected"}


def test_schema_or_validator_mismatched_cache_entry_is_rejected() -> None:
    clock = GatewayClock()
    cache = ResponseCache(ttl_ms=100)
    gateway = AdaptiveInferenceGateway(cache=cache, clock=clock)
    request = _request(request_id="req-cache-validator")
    first = gateway.run(request)
    assert first.selected is not None
    key = gateway.cache_key(request, "small-fast")
    cache.inject(
        CacheEntry(
            key=key,
            candidate=first.selected,
            created_ms=0,
            expires_ms=100,
            validator_version="verifier-v1",
        ).model_copy(update={"validator_version": "verifier-v0"})
    )
    result = gateway.run(request.model_copy(update={"request_id": "req-cache-validator-2"}))
    assert result.cache_status == "rejected"
    assert result.selected is not None


def test_confidential_requests_do_not_populate_cache() -> None:
    cache = ResponseCache()
    gateway = AdaptiveInferenceGateway(cache=cache)
    req = _request(
        request_id="req-confidential",
        data_classification="confidential",
        risk_tier=RiskTier.HIGH,
    )
    first = gateway.run(req)
    second = gateway.run(req.model_copy(update={"request_id": "req-confidential-2"}))
    assert first.cache_status == "bypass"
    assert second.cache_status == "bypass"


def test_classification_route_can_use_quantized_profile_when_quality_floor_allows() -> None:
    gateway = AdaptiveInferenceGateway()
    result = gateway.run(
        _request(
            request_id="req-classify",
            task_class=TaskClass.CLASSIFICATION,
            require_citations=False,
            budget=InferenceBudget(min_quality=0.70),
        )
    )
    assert result.selected is not None
    assert result.selected.profile_id == "quantized-small"
    assert fixture_profiles()["quantized-small"].quantized is True


def test_benchmark_is_reproducible_and_selects_profile_that_clears_floor(tmp_path: Path) -> None:
    report_one = benchmark_gateway(tmp_path / "one")
    report_two = benchmark_gateway(tmp_path / "two")
    assert report_one.model_dump(mode="json") == report_two.model_dump(mode="json")
    selected_rows = [row for row in report_one.rows if row.profile == report_one.selected_profile]
    assert selected_rows
    assert all(row.success for row in selected_rows)
    assert "routed-warm" in report_one.pareto_profiles


def test_gateway_verification_writes_evidence(tmp_path: Path) -> None:
    payload = run_gateway_verification(tmp_path)
    assert payload["passed"] is True
    assert (tmp_path / "benchmark_rows.jsonl").exists()
    assert (tmp_path / "inference_report.json").exists()
    assert (tmp_path / "serving_adr.json").exists()
    assert (tmp_path / "benchmark_summary.json").exists()
    summary = json.loads((tmp_path / "benchmark_summary.json").read_text(encoding="utf-8"))
    assert summary["selected_profile"] in summary["pareto_profiles"]
    assert summary["objective_improvements"]


@pytest.mark.asyncio
async def test_gateway_implements_chapter_one_model_client_port() -> None:
    gateway = AdaptiveInferenceGateway()
    result = await gateway.generate(
        ModelRequest(question="How many remote days are allowed?"),
        _context(),
    )
    assert result.kind == "success"
    assert result.answer.citations
    assert result.usage.adapter.startswith("gateway:")
