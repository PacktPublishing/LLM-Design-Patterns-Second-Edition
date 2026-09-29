"""Chapter 16 capstone verifier tests."""

from __future__ import annotations

from pathlib import Path

from policyops.capstone import (
    CapstoneDecision,
    CapstoneRuntime,
    CapstoneVerifier,
    GameDayRunner,
    GameDayStatus,
    TicketExecuteRequest,
    TicketPreviewRequest,
    TraceabilityValidator,
    run_capstone_faults,
    run_capstone_verification,
)
from policyops.extensions import TicketInput
from policyops.extensions.service import fixture_context
from policyops.governance import Decision as GovernanceDecision
from policyops.governance import GovernanceVerification


def test_traceability_closes_all_chapter_handoffs() -> None:
    closure = TraceabilityValidator().validate()
    assert closure.closed is True
    assert closure.chapters_found == 15
    assert closure.missing_chapters == []
    assert closure.rollback_paths_present is True
    assert closure.decisions_go is True


def test_game_day_runs_sixteen_ordered_mandatory_steps() -> None:
    steps = GameDayRunner().run()
    assert len(steps) == 16
    assert [step.step for step in steps] == list(range(1, 17))
    assert all(step.status == GameDayStatus.PASSED for step in steps)
    assert all(step.operator_id == "operator-release" for step in steps)
    assert all(step.mandatory_gate_decision == "pass" for step in steps)
    assert all(step.cleanup_status == "complete" for step in steps)


def test_seeded_mandatory_failure_returns_no_go() -> None:
    verifier = CapstoneVerifier()
    closure = verifier.traceability.validate()
    steps = verifier.game_day.run(seeded_failure_step=4)
    governance = GovernanceVerification().final_decision()
    rights_receipts = list(GovernanceVerification().rights_receipts())
    decision = verifier.decide(
        closure,
        steps,
        verifier.bundle(closure, steps, [], governance, rights_receipts),
        governance,
        seeded_failure_proven=True,
    )
    assert decision.decision == CapstoneDecision.NO_GO
    assert "GAME_DAY_STEP_4_FAILED" in decision.reasons
    assert steps[3].mandatory_gate_decision == "fail"


def test_missing_seeded_failure_proof_forces_no_go() -> None:
    verifier = CapstoneVerifier()
    closure = verifier.traceability.validate()
    steps = verifier.game_day.run()
    governance = GovernanceVerification().final_decision()
    rights_receipts = list(GovernanceVerification().rights_receipts())
    decision = verifier.decide(
        closure,
        steps,
        verifier.bundle(closure, steps, [], governance, rights_receipts),
        governance,
        seeded_failure_proven=False,
    )
    assert decision.decision == CapstoneDecision.NO_GO
    assert "SEEDED_FAILURE_PROOF_MISSING" in decision.reasons


def test_governance_no_go_forces_capstone_no_go() -> None:
    verifier = CapstoneVerifier()
    closure = verifier.traceability.validate()
    steps = verifier.game_day.run()
    governance = GovernanceVerification().final_decision().model_copy(update={"decision": GovernanceDecision.NO_GO})
    rights_receipts = list(GovernanceVerification().rights_receipts())
    decision = verifier.decide(
        closure,
        steps,
        verifier.bundle(closure, steps, [], governance, rights_receipts),
        governance,
        seeded_failure_proven=True,
    )
    assert decision.decision == CapstoneDecision.NO_GO
    assert "GOVERNANCE_NO_GO" in decision.reasons


def test_clean_capstone_release_returns_go_with_signed_bundle() -> None:
    scorecard, evidence = CapstoneVerifier().verify()
    assert scorecard.gates_passed is True
    assert scorecard.release_go is True
    assert scorecard.game_day_steps_passed == 16
    assert scorecard.seeded_failure_returns_no_go is True
    assert scorecard.rights_receipt_complete is True
    assert evidence["bundle"]["signature"].startswith("sha256:")
    assert evidence["governance_decision"]["decision"] == "GO"
    assert evidence["release_decision"]["decision"] == "GO"
    assert evidence["game_day_measurements"][3]["payload"]["ticket_id"] is not None
    assert evidence["game_day_measurements"][4]["payload"]["duplicate_tickets"] == 0
    assert evidence["game_day_measurements"][10]["payload"]["decision"] == "revert"
    assert evidence["game_day_measurements"][11]["payload"]["behavior_canary"]["decision"] == "rollback"
    assert evidence["game_day_measurements"][12]["payload"]["corrupt_rejected"] is True


def test_capstone_verifier_writes_required_evidence(tmp_path) -> None:
    payload = run_capstone_verification(tmp_path)
    assert payload["gates_passed"] is True
    required = [
        "traceability_closure.json",
        "game_day_results.json",
        "game_day_measurements.json",
        "seeded_failure_game_day.json",
        "seeded_failure_measurements.json",
        "governance_decision.json",
        "rights_receipts.json",
        "release_bundle.json",
        "release_decision.json",
        "seeded_failure_decision.json",
        "capstone_scorecard.json",
    ]
    for name in required:
        assert (tmp_path / name).exists(), name


def test_capstone_fault_drills_cover_required_scenarios(tmp_path) -> None:
    payload = run_capstone_faults(tmp_path, "all")
    assert payload["passed"] is True
    assert payload["results"] == {
        "bundle": True,
        "game_day": True,
        "seeded_failure": True,
        "traceability": True,
    }


def test_game_day_measurements_prove_integrated_chapter_behaviors() -> None:
    _steps, measurements = GameDayRunner().run_with_measurements()
    by_step = {item["step"]: item for item in measurements}
    assert by_step[2]["payload"]["multi_route"] == "multi_hop_graph"
    assert by_step[2]["payload"]["scanned_citation"]["page"] == 3
    assert by_step[5]["payload"]["duplicate_tickets"] == 0
    assert by_step[7]["payload"]["deleted_absent"] is True
    assert by_step[10]["payload"]["p95_latency_ms"] <= by_step[10]["payload"]["p95_threshold_ms"]
    assert by_step[12]["payload"]["image_canary"]["decision"] == "rollback"
    assert by_step[16]["payload"]["prior_steps_passed"] is True


def test_preview_remains_side_effect_free_and_execute_replays_idempotently(tmp_path: Path) -> None:
    runtime = CapstoneRuntime(tmp_path / "runtime")
    context = fixture_context()
    ticket = TicketInput(
        tenant_id="tenant_alpha",
        title="Remote-work exception support",
        description="Create a policy support ticket for a manager-approved remote-work exception.",
        severity="medium",
        source_refs=["policy_remote:v2:span_remote_approval"],
    )

    preview = runtime.preview_ticket(TicketPreviewRequest(ticket=ticket), context=context)
    assert preview.result.status.value == "preview"
    assert preview.result.ticket_id is None

    executed = runtime.execute_ticket(
        TicketExecuteRequest(ticket=ticket, preview=preview.preview, idempotency_key="capstone-test-1"),
        context=context,
    )
    assert executed.result.ticket_id is not None
    assert executed.run.status.value == "executed"

    replayed = CapstoneRuntime(tmp_path / "runtime").execute_ticket(
        TicketExecuteRequest(ticket=ticket, preview=preview.preview, idempotency_key="capstone-test-1"),
        context=context,
    )
    assert replayed.run.run_id == executed.run.run_id
    assert replayed.result.ticket_id == executed.result.ticket_id
