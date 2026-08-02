"""Worker facade tests for the Chapter 11 session runtime."""

from __future__ import annotations

from policyops.harness import FaultScenario
from policyops.worker import SessionWorker


def _worker(root, owner_id: str = "worker-a") -> SessionWorker:
    return SessionWorker(
        root,
        tenant_id="tenant_alpha",
        actor_id="actor_reader",
        configuration_id="test-config",
        owner_id=owner_id,
    )


def test_worker_run_resume_and_reconcile_share_the_same_runtime(tmp_path) -> None:
    runtime_root = tmp_path / "runtime"
    worker = _worker(runtime_root)
    started = worker.run("worker-session-1", fault=FaultScenario.BEFORE_EFFECT)
    assert started.session.state.value == "action_ready"

    resumed = _worker(runtime_root, owner_id="worker-b").resume(
        "worker-session-1", expected_version=started.session.version
    )
    assert resumed.session.state.value == "verified"

    reconciled = worker.reconcile("worker-session-1")
    assert reconciled.session.state.value == "verified"


def test_worker_cancel_preserves_session_history(tmp_path) -> None:
    runtime_root = tmp_path / "runtime"
    worker = _worker(runtime_root)
    started = worker.run("worker-session-2", fault=FaultScenario.BEFORE_EFFECT)
    cancelled = worker.cancel("worker-session-2", expected_version=started.session.version)
    assert cancelled.session.state.value == "cancelled"
    inspected = worker.inspect("worker-session-2")
    assert inspected.events[-1].new_state.value == "cancelled"
