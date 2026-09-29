"""Chapter 14 deployment and recovery tests."""

from __future__ import annotations

from policyops.deployment import (
    DeploymentVerification,
    DeploymentRuntime,
    DurableWorkQueue,
    FailureClass,
    HealthChecker,
    HealthState,
    IdempotentTicketService,
    ReleaseController,
    ReliabilityController,
    WorkItem,
    fixture_envelope,
    run_deployment_faults,
    run_deployment_verification,
)


def test_admission_rejects_overload_without_enqueueing() -> None:
    queue = DurableWorkQueue()
    results = []
    for index in range(5):
        results.append(
            queue.offer(
                WorkItem(
                    item_id=f"work-{index}",
                    envelope=fixture_envelope(session_id=f"session-{index}"),
                    priority=index,
                    payload_bytes=512,
                )
            )
        )
    assert sum(result.enqueued for result in results) == 4
    assert results[-1].status.value == "rejected_429"
    assert len(queue.items) == 4


def test_worker_claim_and_ack_use_fencing() -> None:
    queue = DurableWorkQueue()
    queue.offer(WorkItem(item_id="work-a", envelope=fixture_envelope(), priority=0, payload_bytes=128))
    lease = queue.claim("worker-a")
    assert lease is not None
    assert queue.acknowledge(lease) is True
    stale = lease.model_copy(update={"fencing_token": lease.fencing_token - 1})
    assert queue.acknowledge(stale) is False


def test_admission_rejects_when_global_or_tenant_concurrency_is_exhausted() -> None:
    queue = DurableWorkQueue()
    queue.offer(WorkItem(item_id="alpha-a", envelope=fixture_envelope(session_id="alpha-a"), priority=0, payload_bytes=128))
    queue.offer(WorkItem(item_id="beta-a", envelope=fixture_envelope(tenant_id="tenant-beta", session_id="beta-a"), priority=1, payload_bytes=128))
    lease_a = queue.claim("worker-a")
    lease_b = queue.claim("worker-b")
    assert lease_a is not None
    assert lease_b is not None

    global_reject = queue.offer(
        WorkItem(item_id="alpha-b", envelope=fixture_envelope(session_id="alpha-b"), priority=2, payload_bytes=128)
    )
    assert global_reject.status.value == "rejected_429"
    assert global_reject.reason == "global concurrency exhausted"
    assert global_reject.enqueued is False

    queue = DurableWorkQueue()
    queue.offer(WorkItem(item_id="alpha-c", envelope=fixture_envelope(session_id="alpha-c"), priority=0, payload_bytes=128))
    lease_c = queue.claim("worker-a")
    assert lease_c is not None
    tenant_reject = queue.offer(
        WorkItem(item_id="alpha-d", envelope=fixture_envelope(session_id="alpha-d"), priority=1, payload_bytes=128)
    )
    assert tenant_reject.status.value == "rejected_429"
    assert tenant_reject.reason == "tenant concurrency exhausted"
    assert tenant_reject.enqueued is False


def test_idempotency_preserves_one_business_effect() -> None:
    service = IdempotentTicketService()
    assert service.create_ticket("idem-1") == service.create_ticket("idem-1")
    assert len(service.receipts) == 1


def test_retry_breaker_and_model_route_do_not_silently_lower_quality() -> None:
    reliability = ReliabilityController()
    assert reliability.retry_policy(FailureClass.TRANSIENT).retryable is True
    assert reliability.retry_policy(FailureClass.AUTHORIZATION).retryable is False
    assert reliability.breaker_after_failures("model", 3).open is True
    compliant = reliability.route_model(primary_healthy=False, fallback_quality=0.88)
    inadequate = reliability.route_model(primary_healthy=False, fallback_quality=0.70)
    assert compliant.mode == "degraded"
    assert inadequate.mode == "unavailable"


def test_health_distinguishes_liveness_startup_readiness_and_safe_resume() -> None:
    checker = HealthChecker()
    ready = checker.report()
    unsafe = checker.report(worker_safe=False)
    schema_bad = checker.report(schema_compatible=False)
    assert ready.liveness == HealthState.LIVE
    assert ready.readiness == HealthState.READY
    assert unsafe.readiness == HealthState.NOT_READY
    assert schema_bad.schema_compatible is False


def test_migration_canary_and_image_evidence_are_gateable() -> None:
    release = ReleaseController()
    assert release.migration_plan().preflight_passed is True
    assert release.migration_plan(unsafe=True).preflight_passed is False
    assert release.canary(bad_image=True).decision == "rollback"
    assert release.canary(bad_image=True).accepted_digest_after == release.baseline
    assert all(image.non_root and image.sbom_valid and image.digest.startswith("sha256:") for image in release.image_records())


def test_backup_restore_rejects_corrupt_and_validates_isolated_restore() -> None:
    controller = __import__("policyops.deployment", fromlist=["BackupRestoreController"]).BackupRestoreController()
    corrupt, valid = controller.catalogs()
    corrupt_report = controller.restore(corrupt)
    valid_report = controller.restore(valid)
    assert corrupt_report.corrupt_rejected is True
    assert valid_report.restored_to_isolation is True
    assert valid_report.integrity_passed is True
    assert valid_report.rto_seconds <= 60
    assert valid_report.rpo_seconds <= 10


def test_load_and_chaos_scorecard_passes_hard_gates() -> None:
    scorecard, evidence = DeploymentVerification().scorecard()
    assert scorecard.gates_passed is True
    assert scorecard.queue_bound_held is True
    assert scorecard.duplicate_tickets == 0
    assert scorecard.bad_image_rolled_back is True
    assert scorecard.runbook_coverage == 1.0
    assert evidence["load_samples"]["offers"]
    assert evidence["chaos_measurements"]["scenarios"]
    assert all(item["duplicate_effects"] == 0 for item in evidence["chaos"])


def test_runtime_status_drain_reconcile_and_restore_surfaces_are_operational(tmp_path) -> None:
    runtime = DeploymentRuntime(tmp_path / "runtime")
    status = runtime.status(role="operator")
    assert status.queue_depth == 3
    assert status.outbox_pending == 1

    dry_run = runtime.queue_drain(role="operator", dry_run=True)
    assert dry_run.queue_depth_after == 3

    applied = runtime.queue_drain(role="operator", dry_run=False)
    assert applied.queue_depth_after == 0
    assert applied.containment_mode is True

    reconcile = runtime.outbox_reconcile(role="operator", dry_run=False)
    assert reconcile.pending_before == 1
    assert reconcile.pending_after == 0
    assert reconcile.duplicate_effects == 0

    canary = runtime.canary_release(
        role="release-engineer",
        candidate_digest="sha256:goodcandidate",
        bad_image=False,
        dry_run=False,
    )
    assert canary.decision == "promote"

    rollback = runtime.rollback_release(role="release-engineer", dry_run=False)
    assert rollback.accepted_digest_after == "sha256:acceptedbaseline"

    backup = runtime.verify_backup(role="database-engineer", backup_id="backup-corrupt")
    assert backup.corrupt_rejected is True

    restore = runtime.run_restore(role="database-engineer", backup_id="backup-valid", dry_run=False)
    assert restore.promotion_ready is True
    assert restore.reconciled_security_state is True


def test_deployment_verifier_writes_required_evidence(tmp_path) -> None:
    payload = run_deployment_verification(tmp_path)
    assert payload["gates_passed"] is True
    required = [
        "topology.json",
        "admission_queue.json",
        "retry_breaker_policy.json",
        "model_route.json",
        "health_reports.json",
        "migration_reports.json",
        "image_records.json",
        "canary_report.json",
        "backup_catalogs.json",
        "restore_reports.json",
        "load_report.json",
        "load_samples.json",
        "chaos_results.json",
        "chaos_measurements.json",
        "operator_runbooks.json",
        "deployment_scorecard.json",
    ]
    for name in required:
        assert (tmp_path / name).exists(), name


def test_deployment_fault_drills_cover_required_scenarios(tmp_path) -> None:
    payload = run_deployment_faults(tmp_path, "all")
    assert payload["passed"] is True
    assert payload["results"] == {
        "backup": True,
        "canary": True,
        "chaos": True,
        "health": True,
        "model": True,
        "queue": True,
    }
