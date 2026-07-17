"""Chapter 16 capstone verifier tests."""

from __future__ import annotations

from policyops.capstone import (
    CapstoneDecision,
    CapstoneVerifier,
    GameDayRunner,
    GameDayStatus,
    TraceabilityValidator,
    run_capstone_faults,
    run_capstone_verification,
)


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
    assert all(step.cleanup_status == "complete" for step in steps)


def test_seeded_mandatory_failure_returns_no_go() -> None:
    verifier = CapstoneVerifier()
    closure = verifier.traceability.validate()
    steps = verifier.game_day.run(seeded_failure_step=4)
    decision = verifier.decide(closure, steps, verifier.bundle(closure, steps), seeded_failure_proven=True)
    assert decision.decision == CapstoneDecision.NO_GO
    assert "GAME_DAY_STEP_4_FAILED" in decision.reasons


def test_clean_capstone_release_returns_go_with_signed_bundle() -> None:
    scorecard, evidence = CapstoneVerifier().verify()
    assert scorecard.gates_passed is True
    assert scorecard.release_go is True
    assert scorecard.game_day_steps_passed == 16
    assert scorecard.seeded_failure_returns_no_go is True
    assert evidence["bundle"]["signature"].startswith("sha256:")
    assert evidence["release_decision"]["decision"] == "GO"


def test_capstone_verifier_writes_required_evidence(tmp_path) -> None:
    payload = run_capstone_verification(tmp_path)
    assert payload["gates_passed"] is True
    required = [
        "traceability_closure.json",
        "game_day_results.json",
        "seeded_failure_game_day.json",
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
