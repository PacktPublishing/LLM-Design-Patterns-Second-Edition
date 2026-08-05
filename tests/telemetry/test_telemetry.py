"""Chapter 12 telemetry, privacy, experiment, and canary tests."""

from __future__ import annotations

from policyops.telemetry import (
    ActiveCanaryExistsError,
    AdjudicationRequest,
    ALLOWED_ATTRS,
    ArtifactRegistry,
    CanaryStopRequest,
    ExperimentDecision,
    ExperimentRunRequest,
    FailureClass,
    SamplingDecision,
    SpanKind,
    TelemetryRuntime,
    TelemetryPolicy,
    TraceImprovementPipeline,
    clear_spans,
    fixture_raw_events,
    recorded_spans,
    run_observability_faults,
    run_observability_verification,
    span,
)


def test_span_redacts_non_allowlisted_attributes() -> None:
    clear_spans()
    with span(
        "policyops.answer",
        {
            "tenant_id": "tenant_alpha",
            "actor_id": "actor_reader",
            "authorization_token": "sk-should-not-appear",
            "question": "raw user content that must not leak",
        },
    ):
        pass
    spans = [s for s in recorded_spans() if s["name"] == "policyops.answer"]
    assert spans, "expected the policyops.answer span to be recorded"
    attrs = spans[-1]["attributes"]
    assert attrs.get("tenant_id") == "tenant_alpha"
    assert "authorization_token" not in attrs
    assert "question" not in attrs
    assert set(attrs).issubset(ALLOWED_ATTRS)


def test_semantic_adapter_correlates_required_fixture_spans() -> None:
    pipeline = TraceImprovementPipeline()
    artifacts, spans = pipeline.correlated_trace()
    observed = {span.span_kind for span in spans}
    assert observed == set(SpanKind)
    assert {span.context.correlation_id for span in spans} == {"corr-policyops-1201"}
    assert all(span.context.artifact_set_id == artifacts.artifact_set_id for span in spans)
    assert set(artifacts.by_type()) >= {
        "prompt",
        "context_policy",
        "model_adapter",
        "index",
        "memory_policy",
        "tool",
        "protocol",
        "grader",
        "security_policy",
        "deployment_profile",
    }


def test_redaction_hashing_sampling_and_cardinality_are_applied_before_export() -> None:
    policy = TelemetryPolicy(cardinality_limit=2)
    redacted = [policy.normalize(event) for event in fixture_raw_events()]
    exported = "\n".join(span.model_dump_json() for span in redacted)
    assert "123-45-6789" not in exported
    assert "ken@example.com" not in exported
    assert "sk-not-a-real-secret" not in exported
    assert "tenant-alpha" not in exported
    assert {span.context.sampling_decision for span in redacted if span.span_kind == SpanKind.APPROVAL} == {
        SamplingDecision.REQUIRED
    }
    assert any("raw_prompt" in span.dropped_fields for span in redacted)
    assert any("authorization_token" in span.dropped_fields for span in redacted)


def test_only_expert_adjudicated_product_failure_can_graduate_to_eval_case() -> None:
    pipeline = TraceImprovementPipeline()
    _, spans = pipeline.correlated_trace()
    adjudication = pipeline.adjudicate(spans, failure_class=FailureClass.PRODUCT_FAILURE)
    case = pipeline.graduate_case(spans, adjudication)
    assert case.source_correlation_id == adjudication.correlation_id
    assert case.redacted_trace_hash.startswith("sha256:")
    noisy = pipeline.adjudicate(spans, failure_class=FailureClass.INFRASTRUCTURE_NOISE)
    assert noisy.may_graduate is False


def test_overfit_candidate_is_reverted_and_protected_hashes_are_unchanged() -> None:
    pipeline = TraceImprovementPipeline()
    trial_report = pipeline.experiment_trial_report(overfit=True)
    ledger = pipeline.run_experiment(overfit=True)
    assert ledger.decision == ExperimentDecision.REVERT
    assert ledger.protected_hashes_before == ledger.protected_hashes_after
    assert ledger.protected_hashes_before == trial_report["protected_hashes_before"]
    by_suite = {result.suite: result for result in ledger.results}
    assert by_suite["target"].candidate_score > by_suite["target"].baseline_score
    assert by_suite["holdout"].candidate_score < by_suite["holdout"].baseline_score
    assert len(trial_report["trials"]) == 18


def test_good_candidate_reports_cost_per_successful_outcome() -> None:
    pipeline = TraceImprovementPipeline()
    trial_report = pipeline.experiment_trial_report(overfit=False)
    ledger = pipeline.run_experiment(overfit=False)
    assert ledger.decision == ExperimentDecision.KEEP
    assert all(result.candidate_cost_per_success > 0 for result in ledger.results)
    assert ledger.manifest.candidate_hash == trial_report["candidate_hash"]
    assert all(result.candidate_score >= result.baseline_score for result in ledger.results)


def test_slo_records_cover_required_prd_areas_and_have_owners_and_windows() -> None:
    slos = TraceImprovementPipeline().slo_records()
    by_name = {record.name: record for record in slos}
    assert set(by_name) >= {
        "outcome_quality",
        "p95_latency",
        "error_rate",
        "cost_budget",
        "cost_per_successful_outcome",
        "recovery",
        "high_impact_action_success",
    }
    assert all(record.owner for record in slos)
    assert all(record.window for record in slos)
    assert all(record.measurement_query for record in slos)


def test_harness_retirement_adr_records_measured_benefit_and_rollback_path() -> None:
    adr = TraceImprovementPipeline().harness_retirement_adr()
    assert adr.measured_benefit
    assert adr.rollback_path
    assert adr.decision in {"keep", "retire"}


def test_behavior_canary_rolls_back_seeded_bad_release() -> None:
    pipeline = TraceImprovementPipeline()
    trial_report = pipeline.canary_trial_report(bad_release=True)
    report = pipeline.simulate_canary(bad_release=True)
    assert report.decision.value == "rollback"
    assert report.accepted_alias_after == report.baseline_alias_before
    assert report.metrics.safety_incidents == 1
    assert len(trial_report["requests"]) == 20
    assert report.metrics.p95_latency_ms > 2500
    assert report.metrics.candidate_success_rate < report.metrics.baseline_success_rate


def test_reconstruction_and_backend_outage_do_not_repeat_effects_or_fail_request() -> None:
    pipeline = TraceImprovementPipeline()
    _, spans = pipeline.correlated_trace()
    reconstruction = pipeline.reconstruct(spans)
    outage = pipeline.backend_outage_drill()
    assert reconstruction.external_calls_attempted == 0
    assert reconstruction.model_calls_attempted == 0
    assert reconstruction.tool_calls_attempted == 0
    assert outage["request_failures"] == 0
    assert outage["non_blocking"] is True


def test_observability_verifier_writes_required_evidence(tmp_path) -> None:
    payload = run_observability_verification(tmp_path)
    assert payload["gates_passed"] is True
    required = [
        "artifact_registry.json",
        "telemetry_policy_bundle.json",
        "trace_export.jsonl",
        "privacy_report.json",
        "slo_records.json",
        "adjudication.json",
        "eval_case_from_trace.json",
        "experiment_ledger.json",
        "experiment_trial_report.json",
        "accepted_candidate_ledger.json",
        "accepted_candidate_trial_report.json",
        "canary_report.json",
        "canary_trial_report.json",
        "reconstruction_report.json",
        "telemetry_outage.json",
        "harness_event_spans.json",
        "harness_retirement_adr.json",
        "observability_scorecard.json",
    ]
    for name in required:
        assert (tmp_path / name).exists(), name


def test_chapter_12_fault_drills_cover_required_scenarios(tmp_path) -> None:
    payload = run_observability_faults(tmp_path, "all")
    assert payload["passed"] is True
    assert payload["results"] == {
        "privacy": True,
        "overfit": True,
        "canary": True,
        "outage": True,
        "reconstruction": True,
    }


def test_artifact_registry_uses_sha256_digests() -> None:
    artifacts = ArtifactRegistry().fixture_artifacts()
    assert all(artifact.digest.startswith("sha256:") for artifact in artifacts.artifacts)


def test_telemetry_runtime_persists_operation_adjudication_experiment_and_canary(tmp_path) -> None:
    runtime = TelemetryRuntime(tmp_path / "runtime")
    operation = runtime.inspect_operation("corr-policyops-1201")
    assert operation.spans

    adjudication = runtime.adjudicate(
        AdjudicationRequest(
            correlation_id="corr-policyops-1201",
            failure_class=FailureClass.PRODUCT_FAILURE,
            expert_role="policy operations lead",
            expected_behavior="Answer should cite the current reimbursement policy and ask for approval before creating a ticket.",
        )
    )
    assert adjudication.evaluation_case is not None

    experiment = runtime.run_experiment(ExperimentRunRequest(candidate_profile="accepted"))
    assert experiment.active_canary_id == "canary-ch12-active"

    stopped = runtime.stop_canary(
        "canary-ch12-active",
        CanaryStopRequest(reason="operator stopped canary"),
    )
    assert stopped.decision.value == "rollback"
    assert stopped.rollback_reason == "operator stopped canary"


def test_only_one_active_canary_can_run_at_a_time(tmp_path) -> None:
    runtime = TelemetryRuntime(tmp_path / "runtime")
    experiment = runtime.run_experiment(ExperimentRunRequest(candidate_profile="accepted"))
    assert experiment.active_canary_id == "canary-ch12-active"
    try:
        runtime.run_experiment(ExperimentRunRequest(candidate_profile="accepted"))
    except ActiveCanaryExistsError:
        pass
    else:
        raise AssertionError("expected runtime to reject a second active canary")
