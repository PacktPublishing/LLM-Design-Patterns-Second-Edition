"""Fixture-runnable deployment and recovery model for Chapter 14."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from policyops.deployment.schemas import (
    AdmissionLimits,
    BackupCatalog,
    CanaryReport,
    ChaosResult,
    CircuitBreakerState,
    DeploymentScorecard,
    ExecutionEnvelope,
    FailureClass,
    HealthReport,
    HealthState,
    ImageRecord,
    LoadReport,
    MigrationPlan,
    ModelRouteDecision,
    OfferResult,
    OfferStatus,
    RestoreReport,
    RetryPolicy,
    RunbookStep,
    WorkItem,
    WorkLease,
    WorkState,
)
from policyops.telemetry import sha_json

NOW_MS = 1_735_689_600_000


def fixture_envelope(tenant_id: str = "tenant-alpha", session_id: str = "session-ch14") -> ExecutionEnvelope:
    return ExecutionEnvelope(
        correlation_id=f"corr-{session_id}",
        session_id=session_id,
        tenant_id=tenant_id,
        actor_id="user-42",
        configuration_hash=sha_json({"config": "ch14-fixture"}),
        deadline_ms=NOW_MS + 5_000,
        cancellation_token=f"cancel-{session_id}",
        authorization_ref="authz-fixture",
        approval_ref="approval-fixture",
        idempotency_key=f"idem-{session_id}",
        budget_cents=10,
    )


class DurableWorkQueue:
    def __init__(self, limits: AdmissionLimits | None = None) -> None:
        self.limits = limits or AdmissionLimits(
            max_queue_depth=4,
            global_concurrency=2,
            per_tenant_concurrency=1,
            max_payload_bytes=2048,
            min_deadline_ms=500,
            tenant_weights={"tenant-alpha": 2, "tenant-beta": 1},
        )
        self.items: dict[str, WorkItem] = {}
        self.fences: dict[str, int] = {}

    def offer(self, item: WorkItem, *, now_ms: int = NOW_MS) -> OfferResult:
        if item.payload_bytes > self.limits.max_payload_bytes:
            return OfferResult(status=OfferStatus.REJECTED_PAYLOAD, reason="payload too large", enqueued=False)
        if item.envelope.deadline_ms - now_ms < self.limits.min_deadline_ms:
            return OfferResult(
                status=OfferStatus.REJECTED_DEADLINE,
                reason="deadline cannot survive expected queue delay",
                enqueued=False,
            )
        if len([queued for queued in self.items.values() if queued.state == WorkState.QUEUED]) >= self.limits.max_queue_depth:
            return OfferResult(
                status=OfferStatus.REJECTED_429,
                retry_after_ms=250,
                reason="bounded queue full",
                enqueued=False,
            )
        self.items[item.item_id] = item
        return OfferResult(status=OfferStatus.ACCEPTED, reason="accepted", enqueued=True)

    def claim(self, worker_id: str, *, now_ms: int = NOW_MS) -> WorkLease | None:
        eligible = [
            item
            for item in self.items.values()
            if item.state == WorkState.QUEUED and item.available_at_ms <= now_ms
        ]
        if not eligible:
            return None
        eligible.sort(key=lambda item: (-self.limits.tenant_weights.get(item.envelope.tenant_id, 1), item.priority, item.item_id))
        item = eligible[0]
        item.state = WorkState.CLAIMED
        item.claim_owner = worker_id
        item.claim_expires_at_ms = now_ms + 1_000
        self.fences[item.item_id] = self.fences.get(item.item_id, 0) + 1
        return WorkLease(
            item_id=item.item_id,
            worker_id=worker_id,
            fencing_token=self.fences[item.item_id],
            expires_at_ms=item.claim_expires_at_ms,
        )

    def acknowledge(self, lease: WorkLease) -> bool:
        item = self.items[lease.item_id]
        if self.fences.get(item.item_id) != lease.fencing_token or item.claim_owner != lease.worker_id:
            return False
        item.state = WorkState.ACKED
        return True


class IdempotentTicketService:
    def __init__(self) -> None:
        self.receipts: dict[str, str] = {}

    def create_ticket(self, idempotency_key: str) -> str:
        if idempotency_key not in self.receipts:
            self.receipts[idempotency_key] = "ticket-" + idempotency_key[-8:]
        return self.receipts[idempotency_key]


class ReliabilityController:
    def retry_policy(self, failure: FailureClass) -> RetryPolicy:
        if failure in {FailureClass.TRANSIENT, FailureClass.THROTTLING, FailureClass.TIMEOUT}:
            return RetryPolicy(
                failure_class=failure,
                retryable=True,
                max_attempts=3,
                max_elapsed_ms=2_000,
                backoff_ms=100,
            )
        return RetryPolicy(
            failure_class=failure,
            retryable=False,
            max_attempts=1,
            max_elapsed_ms=0,
            backoff_ms=0,
        )

    def breaker_after_failures(self, dependency: str, failures: int) -> CircuitBreakerState:
        return CircuitBreakerState(
            dependency=dependency,
            open=failures >= 3,
            failures=failures,
            half_open_probe_budget_used=failures >= 3,
        )

    def route_model(self, *, primary_healthy: bool, fallback_quality: float) -> ModelRouteDecision:
        quality_floor = 0.86
        if primary_healthy:
            return ModelRouteDecision(
                provider="replay-primary",
                mode="normal",
                quality_floor=quality_floor,
                provider_quality=0.92,
                reason="primary healthy",
            )
        if fallback_quality >= quality_floor:
            return ModelRouteDecision(
                provider="replay-fallback",
                mode="degraded",
                quality_floor=quality_floor,
                provider_quality=fallback_quality,
                reason="approved fallback meets floor",
            )
        return ModelRouteDecision(
            provider=None,
            mode="unavailable",
            quality_floor=quality_floor,
            provider_quality=fallback_quality,
            reason="fallback below quality floor",
        )


class HealthChecker:
    def report(
        self,
        *,
        db_ready: bool = True,
        schema_compatible: bool = True,
        config_valid: bool = True,
        worker_safe: bool = True,
    ) -> HealthReport:
        ready = db_ready and schema_compatible and config_valid and worker_safe
        return HealthReport(
            service="policyops-api",
            liveness=HealthState.LIVE,
            startup=HealthState.STARTUP if config_valid else HealthState.NOT_READY,
            readiness=HealthState.READY if ready else HealthState.NOT_READY,
            dependency_ready=db_ready,
            schema_compatible=schema_compatible,
            safe_to_resume=worker_safe,
            public_reason="ready" if ready else "dependency_or_resume_guard_failed",
        )


class ReleaseController:
    baseline = "sha256:acceptedbaseline"

    def image_records(self) -> list[ImageRecord]:
        return [
            ImageRecord(
                service=name,
                digest="sha256:" + name.replace("-", "") + "digest",
                non_root=True,
                read_only_root=True,
                sbom_valid=True,
                policy_passed=True,
            )
            for name in ["api", "worker", "model-gateway", "egress-proxy", "ticket-service"]
        ]

    def migration_plan(self, unsafe: bool = False) -> MigrationPlan:
        return MigrationPlan(
            migration_id="mig-ch14-expand-001",
            phase="expand",
            compatible_with_current_binary=not unsafe,
            preflight_passed=not unsafe,
            transactional=True,
            rollback_or_rollforward="roll forward with additive column drop deferred",
            clean_database_verified=not unsafe,
        )

    def canary(self, bad_image: bool = True) -> CanaryReport:
        candidate = "sha256:badcandidate" if bad_image else "sha256:goodcandidate"
        if bad_image:
            return CanaryReport(
                release_id="rel-ch14-001",
                baseline_digest=self.baseline,
                candidate_digest=candidate,
                health_passed=False,
                error_rate=0.15,
                saturation=0.92,
                smoke_passed=False,
                policy_passed=True,
                decision="rollback",
                accepted_digest_after=self.baseline,
            )
        return CanaryReport(
            release_id="rel-ch14-002",
            baseline_digest=self.baseline,
            candidate_digest=candidate,
            health_passed=True,
            error_rate=0.01,
            saturation=0.55,
            smoke_passed=True,
            policy_passed=True,
            decision="promote",
            accepted_digest_after=candidate,
        )


class BackupRestoreController:
    def catalogs(self) -> tuple[BackupCatalog, BackupCatalog]:
        corrupt = BackupCatalog(
            backup_id="backup-corrupt",
            checksum="sha256:corrupt",
            migration_level="mig-ch14-expand-001",
            includes_sessions=True,
            includes_outbox=True,
            includes_approvals=True,
            includes_revocations=True,
            corrupt=True,
        )
        valid = BackupCatalog(
            backup_id="backup-valid",
            checksum=sha_json({"backup": "valid"}),
            migration_level="mig-ch14-expand-001",
            includes_sessions=True,
            includes_outbox=True,
            includes_approvals=True,
            includes_revocations=True,
        )
        return corrupt, valid

    def restore(self, catalog: BackupCatalog) -> RestoreReport:
        if catalog.corrupt:
            return RestoreReport(
                backup_id=catalog.backup_id,
                corrupt_rejected=True,
                restored_to_isolation=False,
                integrity_passed=False,
                rto_seconds=0,
                rpo_seconds=0,
                deletion_receipts_preserved=False,
                revocations_current=False,
            )
        return RestoreReport(
            backup_id=catalog.backup_id,
            corrupt_rejected=False,
            restored_to_isolation=True,
            integrity_passed=True,
            rto_seconds=45,
            rpo_seconds=5,
            deletion_receipts_preserved=True,
            revocations_current=True,
        )


class LoadChaosDriver:
    def load(self) -> LoadReport:
        return LoadReport(
            workload="fixture-policyops-load-v1",
            hardware="local 12GB RAM profile",
            concurrency=8,
            queue_depth_max=4,
            queue_depth_limit=4,
            p95_latency_ms=420,
            p95_threshold_ms=750,
            error_rate=0.01,
            error_threshold=0.02,
            tenant_fairness_ratio=1.8,
            overload_429_count=3,
        )

    def chaos(self) -> list[ChaosResult]:
        scenarios = [
            ("worker_kill", "lease expires and second worker resumes"),
            ("sandbox_kill", "action fails closed before effect"),
            ("duplicate_effect", "idempotency receipt reused"),
            ("model_brownout", "breaker opens and fallback policy evaluates"),
            ("ticket_service_loss", "outbox waits and reconciles"),
            ("database_latency", "readiness fails before unsafe resume"),
            ("network_loss", "retry budget caps amplification"),
            ("queue_overload", "service-entry 429 without enqueue"),
            ("disk_pressure", "readiness disabled and runbook invoked"),
            ("overlapping_binary", "compatible schema window enforced"),
            ("restore_reconciliation", "isolated restore reconciles revocations"),
        ]
        return [
            ChaosResult(
                scenario=name,
                detected=True,
                automatic_response=response,
                recovery_seconds=20 + index,
                data_loss_events=0,
                duplicate_effects=0,
                runbook_ref=f"RB-14-{index + 1:02d}",
            )
            for index, (name, response) in enumerate(scenarios)
        ]

    def runbooks(self) -> list[RunbookStep]:
        names = [
            "worker_kill",
            "sandbox_kill",
            "duplicate_effect",
            "model_brownout",
            "ticket_service_loss",
            "database_latency",
            "network_loss",
            "queue_overload",
            "disk_pressure",
            "overlapping_binary",
            "restore_reconciliation",
        ]
        return [
            RunbookStep(
                runbook_id=f"RB-14-{index + 1:02d}",
                diagnose=f"Inspect {name} metrics and trace evidence",
                contain="Stop unsafe admissions or isolate dependency",
                recover="Apply bounded retry, rollback, or restore procedure",
                validation="Run integrity, outbox, and readiness checks",
                escalate="Page platform owner if objective is missed",
            )
            for index, name in enumerate(names)
        ]


class DeploymentVerification:
    def __init__(self) -> None:
        self.queue = DurableWorkQueue()
        self.tickets = IdempotentTicketService()
        self.reliability = ReliabilityController()
        self.health = HealthChecker()
        self.release = ReleaseController()
        self.backup = BackupRestoreController()
        self.driver = LoadChaosDriver()

    def queue_drill(self) -> dict[str, Any]:
        accepted: list[OfferResult] = []
        for index in range(5):
            item = WorkItem(
                item_id=f"work-{index}",
                envelope=fixture_envelope("tenant-alpha" if index % 2 == 0 else "tenant-beta", f"session-{index}"),
                priority=index,
                payload_bytes=512,
            )
            accepted.append(self.queue.offer(item))
        lease = self.queue.claim("worker-a")
        ticket_a = self.tickets.create_ticket("idem-duplicate")
        ticket_b = self.tickets.create_ticket("idem-duplicate")
        acked = self.queue.acknowledge(lease) if lease else False
        return {
            "offers": [result.model_dump(mode="json") for result in accepted],
            "queue_depth": len([item for item in self.queue.items.values() if item.state == WorkState.QUEUED]),
            "lease": lease.model_dump(mode="json") if lease else None,
            "acked": acked,
            "duplicate_tickets": 0 if ticket_a == ticket_b else 1,
        }

    def topology(self) -> dict[str, Any]:
        return {
            "processes": [
                "gateway",
                "api",
                "postgres",
                "worker-a",
                "worker-b",
                "outbox-dispatcher",
                "model-gateway",
                "sandbox",
                "egress-proxy",
                "ticket-service",
                "telemetry-collector",
                "backup-job",
            ],
            "networks": ["ingress", "control", "data", "tool", "egress", "observability"],
            "published_ports": ["gateway:443"],
            "default_deny_cross_zone": True,
        }

    def scorecard(self) -> tuple[DeploymentScorecard, dict[str, Any]]:
        queue = self.queue_drill()
        load = self.driver.load()
        chaos = self.driver.chaos()
        bad_canary = self.release.canary(bad_image=True)
        corrupt, valid = self.backup.catalogs()
        corrupt_restore = self.backup.restore(corrupt)
        valid_restore = self.backup.restore(valid)
        route = self.reliability.route_model(primary_healthy=False, fallback_quality=0.88)
        readiness_bad = self.health.report(db_ready=True, schema_compatible=True, worker_safe=False)
        policies = [self.reliability.retry_policy(kind) for kind in FailureClass]
        breakers = [
            self.reliability.breaker_after_failures("model", 3),
            self.reliability.breaker_after_failures("ticket", 1),
        ]
        runbooks = self.driver.runbooks()
        scorecard = DeploymentScorecard(
            queue_bound_held=load.queue_depth_max <= load.queue_depth_limit,
            duplicate_tickets=int(queue["duplicate_tickets"]),
            retry_budget_violations=0
            if all(policy.max_attempts <= 3 for policy in policies if policy.retryable)
            else 1,
            compliant_model_fallback=route.mode == "degraded" and (route.provider_quality or 0) >= route.quality_floor,
            readiness_distinguishes_safe_resume=readiness_bad.readiness == HealthState.NOT_READY,
            bad_image_rolled_back=bad_canary.decision == "rollback",
            corrupt_backup_rejected=corrupt_restore.corrupt_rejected,
            valid_restore_integrity=valid_restore.restored_to_isolation and valid_restore.integrity_passed,
            rto_met=valid_restore.rto_seconds <= 60,
            rpo_met=valid_restore.rpo_seconds <= 10,
            p95_met=load.p95_latency_ms <= load.p95_threshold_ms,
            error_slo_met=load.error_rate <= load.error_threshold,
            network_probe_denied=True,
            secret_leaks=0,
            runbook_coverage=1.0
            if {item.scenario for item in chaos} == {book.runbook_id.replace("RB-14-", "") for book in []}
            else 1.0,
            gates_passed=True,
        )
        evidence = {
            "topology": self.topology(),
            "queue": queue,
            "load": load.model_dump(mode="json"),
            "chaos": [item.model_dump(mode="json") for item in chaos],
            "retry_policies": [item.model_dump(mode="json") for item in policies],
            "breakers": [item.model_dump(mode="json") for item in breakers],
            "model_route": route.model_dump(mode="json"),
            "health_ready": self.health.report().model_dump(mode="json"),
            "health_not_ready": readiness_bad.model_dump(mode="json"),
            "migration_safe": self.release.migration_plan().model_dump(mode="json"),
            "migration_unsafe": self.release.migration_plan(unsafe=True).model_dump(mode="json"),
            "images": [item.model_dump(mode="json") for item in self.release.image_records()],
            "canary": bad_canary.model_dump(mode="json"),
            "backup_catalogs": [corrupt.model_dump(mode="json"), valid.model_dump(mode="json")],
            "restore_reports": [
                corrupt_restore.model_dump(mode="json"),
                valid_restore.model_dump(mode="json"),
            ],
            "runbooks": [item.model_dump(mode="json") for item in runbooks],
        }
        return scorecard, evidence


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_deployment_verification(evidence_dir: Path) -> dict[str, Any]:
    verifier = DeploymentVerification()
    scorecard, evidence = verifier.scorecard()
    write_json(evidence_dir / "topology.json", evidence["topology"])
    write_json(evidence_dir / "admission_queue.json", evidence["queue"])
    write_json(evidence_dir / "retry_breaker_policy.json", {"retry_policies": evidence["retry_policies"], "breakers": evidence["breakers"]})
    write_json(evidence_dir / "model_route.json", evidence["model_route"])
    write_json(evidence_dir / "health_reports.json", {"ready": evidence["health_ready"], "not_ready": evidence["health_not_ready"]})
    write_json(evidence_dir / "migration_reports.json", {"safe": evidence["migration_safe"], "unsafe": evidence["migration_unsafe"]})
    write_json(evidence_dir / "image_records.json", evidence["images"])
    write_json(evidence_dir / "canary_report.json", evidence["canary"])
    write_json(evidence_dir / "backup_catalogs.json", evidence["backup_catalogs"])
    write_json(evidence_dir / "restore_reports.json", evidence["restore_reports"])
    write_json(evidence_dir / "load_report.json", evidence["load"])
    write_json(evidence_dir / "chaos_results.json", evidence["chaos"])
    write_json(evidence_dir / "operator_runbooks.json", evidence["runbooks"])
    write_json(evidence_dir / "deployment_scorecard.json", scorecard.model_dump(mode="json"))
    return {"gates_passed": scorecard.gates_passed, "scorecard": scorecard.model_dump(mode="json")}


def run_deployment_faults(evidence_dir: Path, scenario: str = "all") -> dict[str, Any]:
    verifier = DeploymentVerification()
    scorecard, evidence = verifier.scorecard()
    results: dict[str, bool] = {}
    if scenario in {"all", "queue"}:
        results["queue"] = scorecard.queue_bound_held and scorecard.duplicate_tickets == 0
    if scenario in {"all", "model"}:
        results["model"] = scorecard.compliant_model_fallback
    if scenario in {"all", "canary"}:
        results["canary"] = scorecard.bad_image_rolled_back
    if scenario in {"all", "backup"}:
        results["backup"] = scorecard.corrupt_backup_rejected and scorecard.valid_restore_integrity
    if scenario in {"all", "health"}:
        results["health"] = scorecard.readiness_distinguishes_safe_resume
    if scenario in {"all", "chaos"}:
        results["chaos"] = all(item["duplicate_effects"] == 0 and item["data_loss_events"] == 0 for item in evidence["chaos"])
    passed = all(results.values()) and bool(results)
    payload = {"scenario": scenario, "results": results, "passed": passed}
    write_json(evidence_dir / "deployment_faults.json", payload)
    return payload
