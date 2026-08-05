"""Chapter 10 bounded orchestration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from policyops.extensions import fixture_context, fixture_ticket
from policyops.orchestration import (
    BudgetLedger,
    DelegationIssuer,
    Finding,
    FindingKind,
    ResultMerger,
    RunStatus,
    TerminalReason,
    TopologyVariant,
    TriageEngine,
    TriageControlRequest,
    TriageRunRequest,
    TriageRuntime,
    Worker,
    principal_from_context,
    run_orchestration_verification,
    run_topology_comparison,
)
from policyops.orchestration.service import _sign_payload


def test_known_rule_variants_reach_same_expected_state_with_model_only_for_single_agent() -> None:
    engine = TriageEngine()
    workflow = engine.start(TopologyVariant.WORKFLOW)
    single = engine.start(TopologyVariant.SINGLE_AGENT)
    browser = engine.start(TopologyVariant.BROWSER)
    worker = engine.start(TopologyVariant.ORCHESTRATOR_WORKER)
    assert {workflow.status, single.status, browser.status, worker.status} == {RunStatus.SUCCEEDED}
    assert workflow.model_calls == 0
    assert browser.model_calls == 0
    assert worker.model_calls == 0
    assert single.model_calls == 1
    assert all(state.ticket_id for state in [workflow, single, browser, worker])


def test_final_mutation_still_uses_chapter_nine_toolport_approval_and_idempotency() -> None:
    engine = TriageEngine()
    state = engine.start(TopologyVariant.WORKFLOW)
    assert state.ticket_id is not None
    assert "chapter9_toolport_create" in state.trace
    duplicate = engine.tool_port.repository.create_once(
        engine.tool_port.preview_policy_ticket(fixture_ticket(), fixture_context()),
        fixture_context(),
        f"{state.run_id}-ticket",
    )
    assert duplicate.ticket_id == state.ticket_id


def test_delegated_tasks_are_signed_narrow_and_traceable() -> None:
    engine = TriageEngine()
    state = engine.start(TopologyVariant.ORCHESTRATOR_WORKER)
    assert state.status == RunStatus.SUCCEEDED
    assert len(engine.issued_tasks) == 2
    assert engine.transition_events_for(state.run_id)
    assert engine.budget_entries_for(state.run_id)
    assert state.budget.consumed_tokens == 200
    assert state.budget.consumed_spend_cents >= 1
    for task in engine.issued_tasks:
        assert task.principal.tenant_id == "tenant_alpha"
        assert "ticket:create" not in task.tool_allowlist
        assert task.signature.startswith("sha256:")
        assert task.evidence_allowlist


def test_scope_widened_expired_or_replayed_delegations_are_rejected() -> None:
    issuer = DelegationIssuer()
    principal = principal_from_context(fixture_context())
    seen: set[str] = set()
    valid = issuer.issue(
        run_id="run-x",
        principal=principal,
        worker_id="retrieve_worker",
        objective="retrieve",
        evidence_allowlist=["policy_remote:v2"],
        tool_allowlist=["retrieval:read"],
        nonce="n1",
    )
    assert issuer.verify(valid, expected_run_id="run-x", seen_nonces=seen) is True
    assert issuer.verify(valid, expected_run_id="run-x", seen_nonces=seen) is False
    widened = valid.model_copy(update={"tool_allowlist": ["retrieval:read", "ticket:create"], "nonce": "n2"})
    assert issuer.verify(widened, expected_run_id="run-x", seen_nonces=set()) is False
    expired = issuer.issue(
        run_id="run-x",
        principal=principal,
        worker_id="validate_worker",
        objective="validate",
        evidence_allowlist=["policy_remote:v2"],
        tool_allowlist=[],
        nonce="expired",
        expires_at=1,
    )
    assert issuer.verify(expired, expected_run_id="run-x", seen_nonces=set()) is False


def test_worker_result_validation_rejects_evidence_substitution_and_merge_collision() -> None:
    issuer = DelegationIssuer()
    principal = principal_from_context(fixture_context())
    task = issuer.issue(
        run_id="run-y",
        principal=principal,
        worker_id="retrieve_worker",
        objective="retrieve",
        evidence_allowlist=["policy_remote:v2:span_remote_approval"],
        tool_allowlist=["retrieval:read"],
        nonce="n3",
    )
    result = Worker().execute(task)
    merger = ResultMerger()
    assert merger.verify_result(task, result) is True
    substituted = result.model_copy(update={"evidence_refs": ["other_tenant:secret"]})
    assert merger.verify_result(task, substituted) is False
    conflict = result.model_copy(
        update={
            "result_id": "conflict",
            "findings": [
                Finding(
                    finding_id=result.findings[0].finding_id,
                    kind=FindingKind.EVIDENCE,
                    text="Different payload under same merge key.",
                )
            ],
        }
    )
    conflict.signature = _sign_payload(conflict.model_dump(exclude={"signature"}, mode="json"))
    _, reason = merger.merge([task, task], [result, conflict])
    assert reason == TerminalReason.MERGE_COLLISION


def test_capacity_unavailable_spawns_no_partial_workers_and_releases_reservations() -> None:
    engine = TriageEngine()
    state = engine.start(TopologyVariant.ORCHESTRATOR_WORKER, budget=BudgetLedger(worker_limit=1))
    assert state.status == RunStatus.AWAITING_REVIEW
    assert state.terminal_reason == TerminalReason.CAPACITY_UNAVAILABLE
    assert state.delegated_task_ids == []
    assert state.budget.reserved_workers == 0


def test_browser_profile_mismatch_cannot_bypass_tool_boundary() -> None:
    engine = TriageEngine()
    state = engine.start(TopologyVariant.BROWSER, browser_profile="wrong-profile")
    assert state.status == RunStatus.AWAITING_REVIEW
    assert state.terminal_reason == TerminalReason.BROWSER_PROFILE_MISMATCH
    assert state.ticket_id is None
    assert not engine.tool_port.repository.tickets


def test_pause_resume_cancel_preserve_versioned_snapshot_for_chapter_eleven() -> None:
    engine = TriageEngine()
    state = engine.start(TopologyVariant.ORCHESTRATOR_WORKER, budget=BudgetLedger(worker_limit=1))
    paused = engine.pause(state.run_id, expected_version=state.version)
    assert paused.status == RunStatus.PAUSED
    resumed = engine.resume(state.run_id, expected_version=paused.version)
    assert resumed.status == RunStatus.AWAITING_REVIEW
    cancelled = engine.cancel(state.run_id, expected_version=resumed.version)
    assert cancelled.status == RunStatus.CANCELLED
    with pytest.raises(RuntimeError, match="STATE_VERSION_CONFLICT"):
        engine.pause(state.run_id, expected_version=1)


def test_topology_comparison_prefers_simpler_path_when_gain_threshold_not_met() -> None:
    engine = TriageEngine()
    states = [
        engine.start(TopologyVariant.WORKFLOW),
        engine.start(TopologyVariant.SINGLE_AGENT),
        engine.start(TopologyVariant.BROWSER),
        engine.start(TopologyVariant.ORCHESTRATOR_WORKER),
    ]
    comparison = run_topology_comparison(states)
    assert comparison.selected_variant == TopologyVariant.WORKFLOW
    assert "No-use ADR" in comparison.a2a_decision
    metrics = {metric.variant: metric for metric in comparison.metrics}
    assert metrics[TopologyVariant.WORKFLOW].risk_events == 0
    assert metrics[TopologyVariant.SINGLE_AGENT].model_calls == 1
    assert metrics[TopologyVariant.BROWSER].browser_actions == 2
    assert metrics[TopologyVariant.ORCHESTRATOR_WORKER].worker_calls == 2
    assert metrics[TopologyVariant.WORKFLOW].latency_ms < metrics[TopologyVariant.ORCHESTRATOR_WORKER].latency_ms
    assert metrics[TopologyVariant.WORKFLOW].cost_per_successful_outcome_cents == metrics[TopologyVariant.WORKFLOW].estimated_cost_cents


def test_fixture_verification_writes_orchestration_evidence(tmp_path: Path) -> None:
    result = run_orchestration_verification(tmp_path)
    assert result["gates_passed"] is True
    assert (tmp_path / "state_graph_runs.json").exists()
    assert (tmp_path / "topology_comparison.json").exists()
    assert (tmp_path / "delegation_contract.json").exists()
    assert (tmp_path / "worker_results.json").exists()
    assert (tmp_path / "transition_events.json").exists()
    assert (tmp_path / "budget_ledger.json").exists()
    assert (tmp_path / "invalid_delegation.json").exists()
    assert (tmp_path / "a2a_no_use_adr.json").exists()
    assert (tmp_path / "orchestration_scorecard.json").exists()
    invalid = __import__("json").loads((tmp_path / "invalid_delegation.json").read_text(encoding="utf-8"))
    scorecard = __import__("json").loads((tmp_path / "orchestration_scorecard.json").read_text(encoding="utf-8"))
    comparison = __import__("json").loads((tmp_path / "topology_comparison.json").read_text(encoding="utf-8"))
    assert invalid["rejected"] is True
    assert scorecard["invalid_delegations_rejected"] == 1
    workflow = next(metric for metric in comparison["metrics"] if metric["variant"] == "workflow")
    worker = next(metric for metric in comparison["metrics"] if metric["variant"] == "orchestrator_worker")
    assert workflow["risk_events"] == 0
    assert worker["worker_calls"] == 2
    assert worker["latency_ms"] > workflow["latency_ms"]


def test_triage_runtime_persists_run_snapshots_and_idempotency(tmp_path: Path) -> None:
    runtime = TriageRuntime(tmp_path / "runtime")
    first = runtime.create(
        TriageRunRequest(
            scenario_id="policy-triage-default",
            variant=TopologyVariant.ORCHESTRATOR_WORKER,
            idempotency_key="same-run",
        ),
        context=fixture_context(),
    )
    again = runtime.create(
        TriageRunRequest(
            scenario_id="policy-triage-default",
            variant=TopologyVariant.ORCHESTRATOR_WORKER,
            idempotency_key="same-run",
        ),
        context=fixture_context(),
    )
    assert first.run.run_id == again.run.run_id
    inspected = runtime.inspect(first.run.run_id)
    assert inspected.delegated_tasks
    assert inspected.worker_results
    assert (tmp_path / "runtime" / "triage-runtime.sqlite3").exists()


def test_triage_runtime_rejects_idempotency_key_reuse_with_different_request(tmp_path: Path) -> None:
    runtime = TriageRuntime(tmp_path / "runtime")
    runtime.create(
        TriageRunRequest(
            scenario_id="policy-triage-default",
            variant=TopologyVariant.ORCHESTRATOR_WORKER,
            idempotency_key="same-run",
        ),
        context=fixture_context(),
    )

    with pytest.raises(RuntimeError, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"):
        runtime.create(
            TriageRunRequest(
                scenario_id="policy-triage-default",
                variant=TopologyVariant.WORKFLOW,
                idempotency_key="same-run",
            ),
            context=fixture_context(),
        )


def test_triage_runtime_persists_transition_events_and_budget_entries(tmp_path: Path) -> None:
    runtime = TriageRuntime(tmp_path / "runtime")
    created = runtime.create(
        TriageRunRequest(
            scenario_id="policy-triage-default",
            variant=TopologyVariant.ORCHESTRATOR_WORKER,
            idempotency_key="persist-journal",
        ),
        context=fixture_context(),
    )
    reloaded_engine = runtime._load_engine(created.run.run_id)
    assert reloaded_engine.transition_events_for(created.run.run_id)
    assert reloaded_engine.budget_entries_for(created.run.run_id)
    assert reloaded_engine.transition_events_for(created.run.run_id)[0].trace_code == "start"


def test_triage_runtime_controls_update_persisted_state(tmp_path: Path) -> None:
    runtime = TriageRuntime(tmp_path / "runtime")
    created = runtime.create(
        TriageRunRequest(
            scenario_id="policy-triage-default",
            variant=TopologyVariant.ORCHESTRATOR_WORKER,
            budget=BudgetLedger(worker_limit=1),
        ),
        context=fixture_context(),
    )
    paused = runtime.pause(
        created.run.run_id,
        TriageControlRequest(expected_version=created.run.version),
    )
    assert paused.run.status == RunStatus.PAUSED
    resumed = runtime.resume(
        created.run.run_id,
        TriageControlRequest(expected_version=paused.run.version),
    )
    assert resumed.run.status == RunStatus.AWAITING_REVIEW
    cancelled = runtime.cancel(
        created.run.run_id,
        TriageControlRequest(expected_version=resumed.run.version),
    )
    assert cancelled.run.status == RunStatus.CANCELLED
