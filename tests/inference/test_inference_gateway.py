"""Chapter 4 adaptive inference gateway tests."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from policyops.contracts import AuthorizationContext, Budget, ModelRequest, RunContext
from policyops.inference import (
    AdaptiveInferenceGateway,
    CacheEntry,
    FailureReason,
    FixtureLoadError,
    GatewayClock,
    InferenceBudget,
    InferenceRequest,
    ResponseCache,
    RiskTier,
    RouteProfile,
    TaskClass,
    benchmark_gateway,
    fixture_profiles,
    hard_gate,
    load_and_validate_cases,
    quality_gate,
    route_profiles,
    run_gateway_verification,
)
from policyops.inference.fixtures import EXPECTED_RISK_COUNTS, EXPECTED_SUITE_COUNTS
from policyops.inference.gateway import (
    _classify_pair,
    _dominance,
    _matched_pair_comparison,
    _percentile,
    _profile_aggregates,
    _verdict,
)
from policyops.inference.schemas import BenchmarkRow, ProfileAggregate


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


def test_classification_route_uses_direct_baseline_profile() -> None:
    # Route policy change (Change 1): classification requests now route through the
    # `direct-baseline` route profile (single cheap call, no escalation), which resolves to
    # `small-fast`, rather than an ad-hoc `quantized-small`-first list.
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
    assert result.selected.profile_id == "small-fast"
    assert result.route == ["small-fast"]
    assert fixture_profiles()["quantized-small"].quantized is True


def test_benchmark_is_reproducible_and_selects_profile_that_clears_floor(tmp_path: Path) -> None:
    report_one = benchmark_gateway(tmp_path / "one")
    report_two = benchmark_gateway(tmp_path / "two")
    assert report_one.model_dump(mode="json") == report_two.model_dump(mode="json")
    selected_rows = [row for row in report_one.rows if row.profile == report_one.selected_profile]
    assert selected_rows
    assert all(row.success for row in selected_rows)
    assert "routed-with-escalation" in report_one.pareto_profiles


def test_gateway_verification_writes_evidence(tmp_path: Path) -> None:
    payload = run_gateway_verification(tmp_path)
    assert payload["passed"] is True
    assert (tmp_path / "benchmark_rows.jsonl").exists()
    assert (tmp_path / "inference_report.json").exists()
    assert (tmp_path / "serving_adr.json").exists()
    assert (tmp_path / "benchmark_summary.json").exists()
    assert (tmp_path / "matched_pair_comparison.json").exists()
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


# --- Change 1: route profiles as data --------------------------------------------------


def test_exactly_three_route_profiles_are_defined_with_explicit_budgets() -> None:
    profiles = route_profiles()
    assert set(profiles) == {
        "direct-baseline",
        "enhanced-with-candidates",
        "routed-with-escalation",
    }
    for name, profile in profiles.items():
        assert isinstance(profile, RouteProfile)
        assert profile.profile_id == name
        assert profile.model_sequence
        assert profile.max_candidates >= 1
        assert profile.max_model_calls >= 1
        assert profile.max_output_tokens >= 1
        assert profile.max_spend_units >= 0.0


def test_direct_baseline_is_a_single_call_with_no_escalation() -> None:
    profile = route_profiles()["direct-baseline"]
    assert profile.model_sequence == ["small-fast"]
    assert profile.max_candidates == 1


def test_enhanced_with_candidates_samples_one_tier_without_escalation() -> None:
    profile = route_profiles()["enhanced-with-candidates"]
    assert len(set(profile.model_sequence)) == 1
    assert len(profile.model_sequence) > 1


def test_routed_with_escalation_ladders_across_tiers() -> None:
    profile = route_profiles()["routed-with-escalation"]
    assert profile.model_sequence == ["small-fast", "standard", "reasoned"]


def test_plan_route_delegates_to_a_route_profile() -> None:
    gateway = AdaptiveInferenceGateway()
    assert gateway.plan_route(_request()) == route_profiles()["routed-with-escalation"].model_sequence
    assert (
        gateway.plan_route(_request(task_class=TaskClass.CLASSIFICATION))
        == route_profiles()["direct-baseline"].model_sequence
    )


def test_forced_route_overrides_selection_without_monkeypatching() -> None:
    gateway = AdaptiveInferenceGateway(forced_route=["draft-reasoned"])
    result = gateway.run(_request())
    assert result.route == ["draft-reasoned"]
    assert result.selected is not None
    assert result.selected.profile_id == "draft-reasoned"


# --- Change 2: hard gate vs. quality gate ------------------------------------------------


def test_hard_gate_denies_unauthorized_requests_non_recoverably() -> None:
    result = hard_gate(_request(authorized=False))
    assert result.passed is False
    assert result.gate == "hard"
    assert result.recoverable is False
    assert "authorization_denied" in result.reasons


def test_unauthorized_request_is_denied_before_any_model_call() -> None:
    gateway = AdaptiveInferenceGateway()
    result = gateway.run(_request(authorized=False))
    assert result.selected is None
    assert result.failure_reason == FailureReason.AUTHORIZATION_DENIED
    assert result.candidates == []
    assert result.route == []


def test_authorization_failure_does_not_escalate_across_the_route() -> None:
    # Unlike a quality-gate failure, an authorization failure must never try another model.
    gateway = AdaptiveInferenceGateway(forced_route=["small-fast", "standard", "reasoned"])
    result = gateway.run(_request(authorized=False))
    assert result.selected is None
    assert len(result.candidates) == 0
    assert result.failure_reason == FailureReason.AUTHORIZATION_DENIED


def test_quality_gate_failure_is_recoverable_and_reports_evidence_alignment_reason() -> None:
    profile = fixture_profiles()["small-fast"]
    request = _request(question="Ambiguous exception for remote work approval?")
    result = quality_gate(profile, request, citations=[])
    assert result.passed is False
    assert result.gate == "quality"
    assert result.recoverable is True
    assert "missing_required_citation" in result.reasons


def test_hard_gate_passes_when_request_is_authorized_and_safe() -> None:
    result = hard_gate(_request())
    assert result.passed is True
    assert result.recoverable is False
    assert result.gate == "hard"


# --- Change 3: Chapter 2 fixture loader ---------------------------------------------------


def test_fixture_loader_matches_expected_suite_and_risk_distribution() -> None:
    cases = load_and_validate_cases()
    assert len(cases) == 31
    assert EXPECTED_SUITE_COUNTS == {"capability": 10, "regression": 15, "adversarial": 6}
    assert EXPECTED_RISK_COUNTS == {
        "authorization": 10,
        "answer_schema": 9,
        "tool_arguments": 7,
        "abstention": 2,
        "citation": 2,
        "adversarial": 1,
    }
    suite_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for case in cases:
        suite_counts[case.suite.value] = suite_counts.get(case.suite.value, 0) + 1
        risk_counts[case.risk.value] = risk_counts.get(case.risk.value, 0) + 1
    assert suite_counts == EXPECTED_SUITE_COUNTS
    assert risk_counts == EXPECTED_RISK_COUNTS


def test_fixture_loader_fails_closed_when_a_suite_is_missing(tmp_path: Path) -> None:
    (tmp_path / "capability").mkdir()
    (tmp_path / "capability" / "cases.jsonl").write_text("", encoding="utf-8")
    # "regression" and "adversarial" suite directories are intentionally absent.
    with pytest.raises(FixtureLoadError):
        load_and_validate_cases(tmp_path)


def test_fixture_loader_fails_closed_when_a_suite_is_empty(tmp_path: Path) -> None:
    for suite in ("capability", "regression", "adversarial"):
        (tmp_path / suite).mkdir()
    (tmp_path / "capability" / "cases.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "regression" / "cases.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "adversarial" / "cases.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(FixtureLoadError):
        load_and_validate_cases(tmp_path)


def test_fixture_adapted_requests_line_up_authorization_risk_with_hard_gate() -> None:
    from policyops.inference.fixtures import load_gateway_workload

    requests = load_gateway_workload()
    assert len(requests) == 31
    unauthorized = [r for r in requests if not r.authorized]
    assert len(unauthorized) == 10
    gateway = AdaptiveInferenceGateway()
    for request in unauthorized:
        result = gateway.run(request)
        assert result.selected is None
        assert result.failure_reason == FailureReason.AUTHORIZATION_DENIED


# --- route policy manifest evidence --------------------------------------------------------


def test_gateway_verification_writes_route_policy_manifest(tmp_path: Path) -> None:
    run_gateway_verification(tmp_path)
    manifest_path = tmp_path / "route_policy_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest["route_profiles"]) == {
        "direct-baseline",
        "enhanced-with-candidates",
        "routed-with-escalation",
    }
    for profile in manifest["route_profiles"].values():
        assert profile["model_sequence"]
        assert profile["max_candidates"] >= 1
        assert profile["max_model_calls"] >= 1
        assert profile["max_output_tokens"] >= 1
        assert profile["max_spend_units"] >= 0.0


# --- Change 4: benchmark matrix, percentiles, aggregate-only dominance -------------------


_FORBIDDEN_PROFILE_NAMES = {"direct-small", "routed-cold", "routed-warm", "quantized", "speculative"}


def _row(
    *,
    request_id: str,
    profile: str,
    cache_state: str = "cold",
    success: bool = True,
    quality: float = 0.9,
    latency_ms: int = 10,
    spend_units: float = 1.0,
    cost_per_successful_outcome: float | None = 1.0,
    selected_profile: str | None = "standard",
    failure_reason: FailureReason = FailureReason.NONE,
) -> BenchmarkRow:
    return BenchmarkRow(
        request_id=request_id,
        profile=profile,
        cache_state=cache_state,
        success=success,
        quality=quality,
        latency_ms=latency_ms,
        spend_units=spend_units,
        cost_per_successful_outcome=cost_per_successful_outcome,
        selected_profile=selected_profile,
        failure_reason=failure_reason,
    )


def test_benchmark_matrix_is_the_three_route_profiles_crossed_with_cache_state() -> None:
    report = benchmark_gateway()
    cells = {(row.profile, row.cache_state) for row in report.rows}
    assert cells == {
        ("direct-baseline", "cold"),
        ("direct-baseline", "warm"),
        ("enhanced-with-candidates", "cold"),
        ("enhanced-with-candidates", "warm"),
        ("routed-with-escalation", "cold"),
        ("routed-with-escalation", "warm"),
    }
    # Cache state is its own axis: every route profile appears with BOTH cache states, not
    # baked into a combined profile name.
    for profile in {"direct-baseline", "enhanced-with-candidates", "routed-with-escalation"}:
        assert {row.cache_state for row in report.rows if row.profile == profile} == {"cold", "warm"}


def test_invented_profile_names_no_longer_appear_in_source() -> None:
    # Matched as quoted string literals (not substrings) so this doesn't false-positive on
    # the unrelated `"quantized-small"` MODEL profile id, which legitimately still exists.
    for source_path in Path("src").rglob("*.py"):
        text = source_path.read_text(encoding="utf-8")
        for forbidden in _FORBIDDEN_PROFILE_NAMES:
            assert f'"{forbidden}"' not in text, f"{forbidden!r} found in {source_path}"
            assert f"'{forbidden}'" not in text, f"{forbidden!r} found in {source_path}"


def test_percentile_uses_documented_linear_interpolation() -> None:
    # Known input: [10, 20, 30, 40, 50]. Linear interpolation between closest ranks (numpy's
    # default "linear" method / Excel PERCENTILE.INC): rank = (n - 1) * p.
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile(values, 0.0) == 10.0
    assert _percentile(values, 0.5) == 30.0
    assert _percentile(values, 1.0) == 50.0
    # p95 -> rank = 4 * 0.95 = 3.8 -> interpolate between index 3 (40) and 4 (50).
    assert _percentile(values, 0.95) == pytest.approx(48.0)
    # p99 -> rank = 4 * 0.99 = 3.96 -> interpolate between index 3 (40) and 4 (50).
    assert _percentile(values, 0.99) == pytest.approx(49.6)
    assert _percentile([], 0.5) == 0.0
    assert _percentile([7.0], 0.95) == 7.0


def test_benchmark_report_carries_p50_p95_p99_per_profile() -> None:
    report = benchmark_gateway()
    assert len(report.aggregates) == 3
    for aggregate in report.aggregates:
        assert aggregate.p50_latency_ms >= 0
        assert aggregate.p95_latency_ms >= aggregate.p50_latency_ms
        assert aggregate.p99_latency_ms >= aggregate.p95_latency_ms


def test_dominance_is_computed_on_aggregates_not_raw_rows() -> None:
    # BenchmarkRow no longer carries a `dominated` field at all: dominance is only a
    # per-profile-aggregate concept now, so constructing a row with it must fail closed
    # (StrictModel, extra="forbid").
    with pytest.raises(ValidationError):
        BenchmarkRow(
            request_id="r1",
            profile="fast",
            cache_state="cold",
            success=True,
            quality=0.9,
            latency_ms=10,
            spend_units=1.0,
            cost_per_successful_outcome=1.0,
            selected_profile="small-fast",
            dominated=False,
        )


def test_dominance_bug_is_locked_out_cross_request_rows_never_compared() -> None:
    # Regression test for the fixed bug: the OLD implementation compared every row against
    # every other row, so a single fast row for one request ("r1") could mark a row for a
    # completely unrelated request ("r3", different profile) as dominated. The fixed
    # implementation only ever compares per-profile AGGREGATES.
    rows = [
        _row(request_id="r1", profile="fast", latency_ms=10, spend_units=1.0, cost_per_successful_outcome=1.0),
        _row(request_id="r2", profile="fast", latency_ms=1000, spend_units=1.0, cost_per_successful_outcome=1.0),
        _row(request_id="r3", profile="slow", latency_ms=50, spend_units=1.0, cost_per_successful_outcome=1.0),
    ]
    aggregates = _profile_aggregates(rows, quality_floor=0.8)
    dominated = _dominance(aggregates)
    fast_agg = next(a for a in dominated if a.profile == "fast")
    slow_agg = next(a for a in dominated if a.profile == "slow")
    # "fast"'s aggregate blends r1 (latency 10) and r2 (latency 1000), giving it a p95 latency
    # far worse than "slow"'s single row (latency 50). If dominance were (buggily) computed by
    # comparing r1 directly against r3 instead of the aggregates, "slow" would incorrectly be
    # marked dominated by r1's fast single-row latency. The fix must not do that.
    assert fast_agg.p95_latency_ms > slow_agg.p95_latency_ms
    assert slow_agg.dominated is False


def test_dominance_prefers_strictly_better_aggregate_on_all_three_axes() -> None:
    aggregates = _profile_aggregates(
        [
            _row(request_id="r1", profile="better", latency_ms=10, spend_units=1.0, cost_per_successful_outcome=1.0),
            _row(request_id="r1", profile="worse", latency_ms=100, spend_units=5.0, cost_per_successful_outcome=5.0),
        ],
        quality_floor=0.8,
    )
    dominated = {a.profile: a.dominated for a in _dominance(aggregates)}
    assert dominated == {"better": False, "worse": True}


# --- Change 4: Pareto frontier axes (p95 latency, cost/success, success rate) -------------


def test_pareto_frontier_reports_p95_cost_and_success_rate_per_profile() -> None:
    report = benchmark_gateway()
    for profile in report.pareto_profiles:
        aggregate = next(a for a in report.aggregates if a.profile == profile)
        assert aggregate.p95_latency_ms >= 0.0
        assert aggregate.success_rate == pytest.approx(1.0) or aggregate.success_rate < 1.0
        # cost_per_successful_outcome may be None only when a profile has zero successes;
        # every pareto-eligible profile in this fixture workload has at least one success.
        assert aggregate.cost_per_successful_outcome is not None


def test_raw_rows_are_kept_alongside_aggregates() -> None:
    report = benchmark_gateway()
    assert len(report.rows) == 186  # 3 profiles x 2 cache states x 31 fixture cases
    assert len(report.aggregates) == 3


# --- Change 5: matched-pair comparison ----------------------------------------------------


def test_verdict_definition_is_success_or_failure_reason() -> None:
    assert _verdict(_row(request_id="r1", profile="p", success=True)) == "success"
    assert (
        _verdict(
            _row(
                request_id="r1",
                profile="p",
                success=False,
                quality=0.0,
                cost_per_successful_outcome=None,
                selected_profile=None,
                failure_reason=FailureReason.NO_VERIFIED_CANDIDATE,
            )
        )
        == "no_verified_candidate"
    )


def test_classify_pair_taxonomy() -> None:
    assert _classify_pair("success", "success") == "agreement"
    assert _classify_pair("no_verified_candidate", "no_verified_candidate") == "agreement"
    assert _classify_pair("success", "no_verified_candidate") == "reversal"
    assert _classify_pair("no_verified_candidate", "budget_exhausted") == "disagreement"


def test_matched_pair_comparison_includes_at_least_one_true_reversal() -> None:
    rows = [
        _row(request_id="r1", profile="a", success=True),
        _row(
            request_id="r1",
            profile="b",
            success=False,
            quality=0.0,
            cost_per_successful_outcome=None,
            selected_profile=None,
            failure_reason=FailureReason.NO_VERIFIED_CANDIDATE,
        ),
        _row(request_id="r2", profile="a", success=True),
        _row(request_id="r2", profile="b", success=True),
    ]
    comparison = _matched_pair_comparison(rows, workload_id="test-workload")
    assert comparison.reversal_count == 1
    assert comparison.agreement_count == 1
    assert len(comparison.reversals) == 1
    reversal = comparison.reversals[0]
    assert reversal.request_id == "r1"
    assert reversal.classification == "reversal"
    assert {reversal.verdict_a, reversal.verdict_b} == {"success", "no_verified_candidate"}


def test_matched_pair_comparison_uses_only_cold_cache_rows() -> None:
    # A warm-cache row must never change a verdict comparison: only "cold" rows are compared.
    rows = [
        _row(request_id="r1", profile="a", cache_state="cold", success=True),
        _row(request_id="r1", profile="b", cache_state="cold", success=True),
        _row(request_id="r1", profile="a", cache_state="warm", success=False, quality=0.0, cost_per_successful_outcome=None, selected_profile=None, failure_reason=FailureReason.NO_VERIFIED_CANDIDATE),
        _row(request_id="r1", profile="b", cache_state="warm", success=True),
    ]
    comparison = _matched_pair_comparison(rows, workload_id="test-workload")
    assert len(comparison.outcomes) == 1
    assert comparison.outcomes[0].classification == "agreement"


def test_real_workload_matched_pair_comparison_has_a_reversal(tmp_path: Path) -> None:
    run_gateway_verification(tmp_path)
    comparison = json.loads((tmp_path / "matched_pair_comparison.json").read_text(encoding="utf-8"))
    assert comparison["reversal_count"] >= 1
    assert len(comparison["reversals"]) == comparison["reversal_count"]
    for reversal in comparison["reversals"]:
        assert reversal["classification"] == "reversal"
        assert "success" in (reversal["verdict_a"], reversal["verdict_b"])


# --- Change 6: decision record ------------------------------------------------------------


def test_serving_adr_contains_conditions_rollback_and_limitations(tmp_path: Path) -> None:
    run_gateway_verification(tmp_path)
    adr = json.loads((tmp_path / "serving_adr.json").read_text(encoding="utf-8"))
    assert adr["selected_profile"] in {
        "direct-baseline",
        "enhanced-with-candidates",
        "routed-with-escalation",
    }
    assert isinstance(adr["conditions_for_choice"], list) and adr["conditions_for_choice"]
    assert isinstance(adr["rollback_plan"], list) and adr["rollback_plan"]
    assert isinstance(adr["not_proven_by_this_benchmark"], list) and adr["not_proven_by_this_benchmark"]
    limitations_text = " ".join(adr["not_proven_by_this_benchmark"])
    assert "31" in limitations_text
    assert "authorization" in limitations_text.lower()
    assert adr["objective_improvements"]
