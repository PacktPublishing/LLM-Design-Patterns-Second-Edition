"""Chapter 11 resumable agent-loop tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from policyops.harness import (
    BudgetSnapshot,
    EffectAttemptedDuringReplay,
    EventStore,
    EventType,
    FailureClass,
    FaultScenario,
    FenceError,
    OutboxDispatcher,
    ResumableLoop,
    ReviewHarness,
    SessionPhase,
    SessionRunRequest,
    SessionRuntime,
    classify_failure,
    run_harness_verification,
)


def test_review_harness_accepts_allowlisted_change_and_rejects_unrelated_paths() -> None:
    harness = ReviewHarness()
    plan = harness.plan()
    accepted = harness.review(
        plan,
        ["src/policyops/harness/service.py", "tests/harness/test_resumable_loop.py"],
    )
    rejected = harness.review(plan, ["src/policyops/extensions/service.py"])
    assert accepted.accepted is True
    assert rejected.accepted is False
    assert rejected.findings == ["out_of_scope:src/policyops/extensions/service.py"]


def test_append_only_events_include_identity_configuration_and_fence() -> None:
    loop = ResumableLoop()
    state = loop.run_once("session-events")
    assert state.state == SessionPhase.VERIFIED
    events = loop.store.events[state.session_id]
    assert events
    assert all(event.tenant_id == "tenant_alpha" for event in events)
    assert all(event.request_id for event in events)
    assert all(event.trace_id for event in events)
    assert all(event.configuration_id for event in events)
    assert all(event.fencing_token >= 1 for event in events)


def test_lease_fencing_rejects_stale_worker_writes() -> None:
    loop = ResumableLoop()
    state, old_lease = loop.create_session("session-lease", owner_id="worker-a")
    loop.store.acquire_lease("session-lease", "worker-b")
    with pytest.raises(FenceError, match="STALE_FENCE"):
        loop._append(state, EventType.PLAN_RECORDED, state.state, SessionPhase.PLANNED, old_lease)


@pytest.mark.parametrize(
    "scenario",
    [
        FaultScenario.BEFORE_EFFECT,
        FaultScenario.AFTER_EFFECT_BEFORE_ACK,
        FaultScenario.AFTER_CHECKPOINT,
        FaultScenario.LEASE_CONTENTION,
    ],
)
def test_crash_windows_resume_without_duplicate_ticket(scenario: FaultScenario) -> None:
    loop = ResumableLoop()
    interrupted = loop.run_once(f"session-{scenario.value}", fault=scenario)
    resumed = loop.resume(interrupted.session_id)
    assert resumed.state == SessionPhase.VERIFIED
    receipts = list(loop.store.receipts.values())
    assert len({receipt.external_reference for receipt in receipts}) == len(receipts)
    assert len(receipts) == 1


def test_replay_reconstructs_state_without_external_effects() -> None:
    loop = ResumableLoop()
    state = loop.run_once("session-replay")
    replayed = loop.replay_no_effects(state.session_id)
    assert replayed.state in {SessionPhase.VERIFIED, SessionPhase.EFFECT_DELIVERED}
    dispatcher = OutboxDispatcher(EventStore(), replay=True)
    with pytest.raises(EffectAttemptedDuringReplay):
        dispatcher.deliver("missing")


def test_budget_exhaustion_stops_with_typed_reason_and_no_effect() -> None:
    loop = ResumableLoop()
    state = loop.run_once("session-budget", budget=BudgetSnapshot(iteration_limit=0))
    assert state.state == SessionPhase.STOPPED
    assert state.terminal_reason == FailureClass.BUDGET
    assert not loop.store.outbox
    assert not loop.store.receipts


def test_failure_classifier_selects_declared_actions() -> None:
    assert classify_failure("timeout") == FailureClass.TRANSIENT
    assert classify_failure("bad_json") == FailureClass.SEMANTIC
    assert classify_failure("policy_denied") == FailureClass.POLICY
    assert classify_failure("approval_expired") == FailureClass.AUTHORIZATION
    assert classify_failure("postcondition_mismatch") == FailureClass.VERIFICATION
    assert classify_failure("unknown") == FailureClass.PERMANENT


def test_checkpoint_is_recovery_cursor_not_alternate_history() -> None:
    loop = ResumableLoop()
    state = loop.run_once("session-checkpoint")
    checkpoint = loop.store.checkpoints[state.session_id]
    replayed = loop.reducer.replay(loop.store.events[state.session_id])
    assert checkpoint.event_sequence <= replayed.version
    assert checkpoint.state_hash.startswith("sha256:")
    assert checkpoint.state.approval_reference == "fixture-approval"


def test_sqlite_store_persists_session_history_across_fresh_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "harness.sqlite3"
    first = ResumableLoop(EventStore(db_path))
    state = first.run_once("session-persisted")

    second_store = EventStore(db_path)
    rebuilt = second_store.current_state(state.session_id)

    assert rebuilt.state == SessionPhase.VERIFIED
    assert rebuilt.version == state.version
    assert second_store.receipts[f"{state.session_id}:ticket"].external_reference == state.ticket_id


def test_after_checkpoint_fault_resumes_from_durable_checkpoint_without_duplicate_ticket() -> None:
    loop = ResumableLoop()
    interrupted = loop.run_once("session-after-checkpoint", fault=FaultScenario.AFTER_CHECKPOINT)

    assert interrupted.state == SessionPhase.EFFECT_DELIVERED

    resumed = loop.resume(interrupted.session_id)

    assert resumed.state == SessionPhase.VERIFIED
    assert resumed.ticket_id == loop.store.receipts[f"{interrupted.session_id}:ticket"].external_reference
    assert len(loop.store.receipts) == 1


def test_resume_uses_stored_approval_expiry_before_effect_delivery() -> None:
    loop = ResumableLoop()
    interrupted = loop.run_once("session-expired-approval", fault=FaultScenario.BEFORE_EFFECT)
    loop.dispatcher.tool_port.approval_store.now += 120

    resumed = loop.resume(interrupted.session_id)

    receipt = loop.store.receipts[f"{interrupted.session_id}:ticket"]
    assert resumed.state == SessionPhase.VERIFIED
    assert receipt.status == "failed"
    assert resumed.approval_reference == "fixture-approval"


def test_fixture_verification_writes_harness_evidence(tmp_path: Path) -> None:
    result = run_harness_verification(tmp_path)
    assert result["gates_passed"] is True
    assert (tmp_path / "review_bundle.json").exists()
    assert (tmp_path / "fault_results.json").exists()
    assert (tmp_path / "replay_result.json").exists()
    assert (tmp_path / "approval_denial.json").exists()
    assert (tmp_path / "runbook.json").exists()
    assert (tmp_path / "harness_scorecard.json").exists()
    fault_results = __import__("json").loads((tmp_path / "fault_results.json").read_text(encoding="utf-8"))
    assert {record["scenario"] for record in fault_results} == {
        FaultScenario.BEFORE_EFFECT.value,
        FaultScenario.AFTER_EFFECT_BEFORE_ACK.value,
        FaultScenario.AFTER_CHECKPOINT.value,
        FaultScenario.LEASE_CONTENTION.value,
    }
    scorecard = __import__("json").loads((tmp_path / "harness_scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["crash_cases_recovered"] == 4
    assert scorecard["approval_mismatch_denials"] == 1


def test_session_runtime_uses_durable_sqlite_database(tmp_path: Path) -> None:
    runtime = SessionRuntime(tmp_path / "runtime")
    runtime.run(
        "runtime-db-session",
        request=SessionRunRequest(expected_version=0, owner_id="worker-a", fault=FaultScenario.BEFORE_EFFECT),
        tenant_id="tenant_alpha",
        actor_id="actor_reader",
        configuration_id="fixture-config",
        request_id="req-runtime-db",
        trace_id="trace-runtime-db",
    )

    assert (tmp_path / "runtime" / "session-runtime.sqlite3").exists()
