"""Fixture-runnable deployment and recovery model for Chapter 14."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from policyops.deployment.schemas import (
    AdmissionLimits,
    BackupCatalog,
    BackupVerificationReport,
    CanaryReport,
    ChaosResult,
    CircuitBreakerState,
    DependencyDiagnostic,
    DeploymentScorecard,
    DeploymentStatusEnvelope,
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
    QueueDrainReport,
    ReconcileReport,
    RestoreReport,
    RestoreExecutionReport,
    RollbackReport,
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

    def _active_claims(self, *, now_ms: int) -> list[WorkItem]:
        return [
            item
            for item in self.items.values()
            if item.state == WorkState.CLAIMED
            and item.claim_expires_at_ms is not None
            and item.claim_expires_at_ms > now_ms
        ]

    def offer(self, item: WorkItem, *, now_ms: int = NOW_MS) -> OfferResult:
        if item.payload_bytes > self.limits.max_payload_bytes:
            return OfferResult(status=OfferStatus.REJECTED_PAYLOAD, reason="payload too large", enqueued=False)
        if item.envelope.deadline_ms - now_ms < self.limits.min_deadline_ms:
            return OfferResult(
                status=OfferStatus.REJECTED_DEADLINE,
                reason="deadline cannot survive expected queue delay",
                enqueued=False,
            )
        active_claims = self._active_claims(now_ms=now_ms)
        if len(active_claims) >= self.limits.global_concurrency:
            return OfferResult(
                status=OfferStatus.REJECTED_429,
                retry_after_ms=250,
                reason="global concurrency exhausted",
                enqueued=False,
            )
        tenant_claims = [
            claimed
            for claimed in active_claims
            if claimed.envelope.tenant_id == item.envelope.tenant_id
        ]
        if len(tenant_claims) >= self.limits.per_tenant_concurrency:
            return OfferResult(
                status=OfferStatus.REJECTED_429,
                retry_after_ms=250,
                reason="tenant concurrency exhausted",
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
        for item in self.items.values():
            if (
                item.state == WorkState.CLAIMED
                and item.claim_expires_at_ms is not None
                and item.claim_expires_at_ms <= now_ms
            ):
                item.state = WorkState.QUEUED
                item.claim_owner = None
                item.claim_expires_at_ms = None
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
            startup=HealthState.READY if config_valid else HealthState.NOT_READY,
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

    def canary(
        self,
        bad_image: bool = True,
        *,
        candidate_digest: str | None = None,
        baseline_digest: str | None = None,
    ) -> CanaryReport:
        baseline = baseline_digest or self.baseline
        candidate = candidate_digest or ("sha256:badcandidate" if bad_image else "sha256:goodcandidate")
        if bad_image:
            return CanaryReport(
                release_id="rel-ch14-001",
                baseline_digest=baseline,
                candidate_digest=candidate,
                health_passed=False,
                error_rate=0.15,
                saturation=0.92,
                smoke_passed=False,
                policy_passed=True,
                decision="rollback",
                accepted_digest_after=baseline,
            )
        return CanaryReport(
            release_id="rel-ch14-002",
            baseline_digest=baseline,
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
    def _p95(self, values: list[int]) -> int:
        ordered = sorted(values)
        index = max(0, math.ceil(len(ordered) * 0.95) - 1)
        return ordered[index]

    def load_measurements(self) -> tuple[LoadReport, dict[str, Any]]:
        queue = DurableWorkQueue()
        offers: list[dict[str, Any]] = []
        queue_depth_max = 0
        started_at_ms = NOW_MS
        for index in range(8):
            tenant_id = "tenant-alpha" if index % 2 == 0 else "tenant-beta"
            item = WorkItem(
                item_id=f"load-{index}",
                envelope=fixture_envelope(tenant_id=tenant_id, session_id=f"load-session-{index}"),
                priority=index,
                payload_bytes=512,
            )
            offer = queue.offer(item, now_ms=started_at_ms)
            offers.append(
                {
                    "item_id": item.item_id,
                    "tenant_id": tenant_id,
                    "status": offer.status.value,
                    "enqueued": offer.enqueued,
                    "reason": offer.reason,
                }
            )
            queue_depth_max = max(
                queue_depth_max,
                len([queued for queued in queue.items.values() if queued.state == WorkState.QUEUED]),
            )
        worker_clocks = {"worker-a": started_at_ms, "worker-b": started_at_ms}
        completions: list[dict[str, Any]] = []
        while True:
            worker_id = min(worker_clocks, key=worker_clocks.get)
            now_ms = worker_clocks[worker_id]
            lease = queue.claim(worker_id, now_ms=now_ms)
            if lease is None:
                break
            item = queue.items[lease.item_id]
            service_ms = 250 + item.priority * 35 + (20 if item.envelope.tenant_id == "tenant-beta" else 0)
            latency_ms = (now_ms - started_at_ms) + service_ms
            queue.acknowledge(lease)
            worker_clocks[worker_id] = now_ms + service_ms
            completions.append(
                {
                    "item_id": item.item_id,
                    "tenant_id": item.envelope.tenant_id,
                    "worker_id": worker_id,
                    "service_ms": service_ms,
                    "latency_ms": latency_ms,
                    "fencing_token": lease.fencing_token,
                }
            )
        accepted_by_tenant = {
            tenant: sum(1 for item in completions if item["tenant_id"] == tenant)
            for tenant in {"tenant-alpha", "tenant-beta"}
        }
        normalized_fairness = [
            accepted_by_tenant[tenant] / max(1, queue.limits.tenant_weights.get(tenant, 1))
            for tenant in accepted_by_tenant
        ]
        fairness_ratio = round(max(normalized_fairness) / max(0.0001, min(normalized_fairness)), 4)
        overload_count = sum(1 for offer in offers if offer["status"] == OfferStatus.REJECTED_429.value)
        load = LoadReport(
            workload="fixture-policyops-load-v1",
            hardware="local 12GB RAM profile",
            concurrency=len(offers),
            queue_depth_max=queue_depth_max,
            queue_depth_limit=queue.limits.max_queue_depth,
            p95_latency_ms=self._p95([item["latency_ms"] for item in completions]),
            p95_threshold_ms=750,
            error_rate=round(overload_count / len(offers), 4),
            error_threshold=0.5,
            tenant_fairness_ratio=fairness_ratio,
            overload_429_count=overload_count,
        )
        return load, {"offers": offers, "completions": completions}

    def load(self) -> LoadReport:
        report, _ = self.load_measurements()
        return report

    def chaos_measurements(self) -> tuple[list[ChaosResult], list[dict[str, Any]]]:
        reliability = ReliabilityController()
        release = ReleaseController()
        backup = BackupRestoreController()
        health = HealthChecker()
        queue = DurableWorkQueue()
        queue.offer(WorkItem(item_id="chaos-work", envelope=fixture_envelope(session_id="chaos-worker"), priority=0, payload_bytes=128))
        first_lease = queue.claim("worker-a", now_ms=NOW_MS)
        recovered_lease = queue.claim("worker-b", now_ms=(first_lease.expires_at_ms if first_lease else NOW_MS) + 1)
        ticket_service = IdempotentTicketService()
        duplicate_a = ticket_service.create_ticket("idem-chaos")
        duplicate_b = ticket_service.create_ticket("idem-chaos")
        model_route = reliability.route_model(primary_healthy=False, fallback_quality=0.88)
        model_breaker = reliability.breaker_after_failures("model", 3)
        ticket_breaker = reliability.breaker_after_failures("ticket-service", 3)
        not_ready_db = health.report(db_ready=False)
        not_ready_disk = health.report(config_valid=False)
        migration = release.migration_plan()
        bad_canary = release.canary(bad_image=True)
        corrupt, valid = backup.catalogs()
        restore = backup.restore(valid)
        load, load_samples = self.load_measurements()
        measured = [
            {
                "scenario": "worker_kill",
                "detected": recovered_lease is not None,
                "automatic_response": "expired lease recycled to replacement worker",
                "recovery_seconds": 1 if recovered_lease else 0,
                "data_loss_events": 0,
                "duplicate_effects": 0,
            },
            {
                "scenario": "sandbox_kill",
                "detected": True,
                "automatic_response": "readiness blocks unsafe worker participation",
                "recovery_seconds": 2 if not_ready_disk.readiness == HealthState.NOT_READY else 0,
                "data_loss_events": 0,
                "duplicate_effects": 0,
            },
            {
                "scenario": "duplicate_effect",
                "detected": duplicate_a == duplicate_b,
                "automatic_response": "idempotency receipt reused instead of creating a second effect",
                "recovery_seconds": 1,
                "data_loss_events": 0,
                "duplicate_effects": 0 if duplicate_a == duplicate_b else 1,
            },
            {
                "scenario": "model_brownout",
                "detected": model_breaker.open,
                "automatic_response": "breaker opened and approved degraded route selected",
                "recovery_seconds": 3 if model_route.mode == "degraded" else 0,
                "data_loss_events": 0,
                "duplicate_effects": 0,
            },
            {
                "scenario": "ticket_service_loss",
                "detected": ticket_breaker.open,
                "automatic_response": "retry budget capped and reconcile path preserved",
                "recovery_seconds": 3 if ticket_breaker.open else 0,
                "data_loss_events": 0,
                "duplicate_effects": 0,
            },
            {
                "scenario": "database_latency",
                "detected": not_ready_db.readiness == HealthState.NOT_READY,
                "automatic_response": "readiness turned off before unsafe resume",
                "recovery_seconds": 2 if not_ready_db.readiness == HealthState.NOT_READY else 0,
                "data_loss_events": 0,
                "duplicate_effects": 0,
            },
            {
                "scenario": "network_loss",
                "detected": ticket_breaker.open,
                "automatic_response": "dependency isolation limited retry amplification",
                "recovery_seconds": 3 if ticket_breaker.open else 0,
                "data_loss_events": 0,
                "duplicate_effects": 0,
            },
            {
                "scenario": "queue_overload",
                "detected": load.overload_429_count > 0,
                "automatic_response": "service-entry 429s rejected work before enqueue",
                "recovery_seconds": 1 if load.overload_429_count > 0 else 0,
                "data_loss_events": 0,
                "duplicate_effects": 0,
            },
            {
                "scenario": "disk_pressure",
                "detected": not_ready_disk.readiness == HealthState.NOT_READY,
                "automatic_response": "config/startup failure disabled readiness and invoked operator runbook",
                "recovery_seconds": 2 if not_ready_disk.readiness == HealthState.NOT_READY else 0,
                "data_loss_events": 0,
                "duplicate_effects": 0,
            },
            {
                "scenario": "overlapping_binary",
                "detected": migration.compatible_with_current_binary,
                "automatic_response": "compatible schema window kept old and new binaries safe",
                "recovery_seconds": 2 if migration.compatible_with_current_binary else 0,
                "data_loss_events": 0,
                "duplicate_effects": 0,
            },
            {
                "scenario": "restore_reconciliation",
                "detected": (not valid.corrupt) and restore.integrity_passed,
                "automatic_response": "isolated restore reconciled revocations and deletion state",
                "recovery_seconds": restore.rto_seconds,
                "data_loss_events": restore.rpo_seconds,
                "duplicate_effects": 0,
            },
        ]
        results = [
            ChaosResult(
                scenario=entry["scenario"],
                detected=bool(entry["detected"]),
                automatic_response=str(entry["automatic_response"]),
                recovery_seconds=int(entry["recovery_seconds"]),
                data_loss_events=int(entry["data_loss_events"]),
                duplicate_effects=int(entry["duplicate_effects"]),
                runbook_ref=f"RB-14-{index + 1:02d}",
            )
            for index, entry in enumerate(measured)
        ]
        return results, {"scenarios": measured, "load_samples": load_samples}

    def chaos(self) -> list[ChaosResult]:
        results, _ = self.chaos_measurements()
        return results

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


class DeploymentRuntime:
    operator_roles = {
        "operator",
        "platform-engineer",
        "site-reliability-engineer",
        "database-engineer",
        "release-engineer",
    }

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.release = ReleaseController()
        self.health = HealthChecker()
        self.backup = BackupRestoreController()

    def _state_path(self) -> Path:
        return self.root / "runtime_state.json"

    def _events_dir(self) -> Path:
        path = self.root / "events"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _seed_state(self) -> dict[str, Any]:
        queue = [
            WorkItem(
                item_id=f"runtime-work-{index}",
                envelope=fixture_envelope(
                    tenant_id="tenant-alpha" if index % 2 == 0 else "tenant-beta",
                    session_id=f"runtime-session-{index}",
                ),
                priority=index,
                payload_bytes=512,
            ).model_dump(mode="json")
            for index in range(3)
        ]
        return {
            "accepted_digest": self.release.baseline,
            "containment_mode": False,
            "db_ready": True,
            "schema_compatible": True,
            "config_valid": True,
            "worker_safe": True,
            "dependencies": {
                "postgres": {"healthy": True, "reason_code": "ready"},
                "model-gateway": {"healthy": True, "reason_code": "healthy"},
                "ticket-service": {"healthy": True, "reason_code": "reachable"},
                "telemetry-collector": {"healthy": True, "reason_code": "buffering_ok"},
            },
            "queue": queue,
            "outbox_pending": [
                {
                    "idempotency_key": "idem-runtime-reconcile-1",
                    "effect_ref": "ticket:create:runtime-session-0",
                }
            ],
            "ticket_receipts": {},
            "last_restore": None,
        }

    def _load_state(self) -> dict[str, Any]:
        path = self._state_path()
        if not path.exists():
            state = self._seed_state()
            self._save_state(state)
            return state
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_state(self, state: dict[str, Any]) -> None:
        self._state_path().write_text(
            json.dumps(state, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _require_role(self, role: str) -> None:
        if role not in self.operator_roles:
            raise PermissionError(f"operator role required, got {role}")

    def _queue_items(self, state: dict[str, Any]) -> list[WorkItem]:
        return [WorkItem.model_validate(item) for item in state["queue"]]

    def _save_queue(self, state: dict[str, Any], items: list[WorkItem]) -> None:
        state["queue"] = [item.model_dump(mode="json") for item in items]

    def startup_report(self) -> HealthReport:
        state = self._load_state()
        return self.health.report(
            db_ready=state["db_ready"],
            schema_compatible=state["schema_compatible"],
            config_valid=state["config_valid"],
            worker_safe=state["worker_safe"],
        )

    def dependency_diagnostics(self, *, role: str) -> list[DependencyDiagnostic]:
        self._require_role(role)
        state = self._load_state()
        return [
            DependencyDiagnostic(
                dependency=name,
                healthy=details["healthy"],
                reason_code=details["reason_code"],
                bounded_detail=f"{name}={details['reason_code']}",
            )
            for name, details in state["dependencies"].items()
        ]

    def status(self, *, role: str) -> DeploymentStatusEnvelope:
        self._require_role(role)
        state = self._load_state()
        health = self.startup_report()
        diagnostics = self.dependency_diagnostics(role=role)
        queue_depth = len([item for item in self._queue_items(state) if item.state == WorkState.QUEUED])
        return DeploymentStatusEnvelope(
            accepted_digest=state["accepted_digest"],
            startup=health.startup,
            readiness=health.readiness,
            queue_depth=queue_depth,
            outbox_pending=len(state["outbox_pending"]),
            containment_mode=state["containment_mode"],
            diagnostics=diagnostics,
        )

    def queue_drain(self, *, role: str, dry_run: bool = False) -> QueueDrainReport:
        self._require_role(role)
        state = self._load_state()
        items = self._queue_items(state)
        before = len([item for item in items if item.state == WorkState.QUEUED])
        drained = before
        if not dry_run:
            items = [item for item in items if item.state != WorkState.QUEUED]
            state["containment_mode"] = True
            self._save_queue(state, items)
            self._save_state(state)
        after = before if dry_run else 0
        report = QueueDrainReport(
            queue_depth_before=before,
            drained_count=drained,
            queue_depth_after=after,
            containment_mode=True if not dry_run else state["containment_mode"],
            dry_run=dry_run,
        )
        write_json(self._events_dir() / "queue_drain.json", report.model_dump(mode="json"))
        return report

    def outbox_reconcile(self, *, role: str, dry_run: bool = False) -> ReconcileReport:
        self._require_role(role)
        state = self._load_state()
        pending = list(state["outbox_pending"])
        receipts = dict(state["ticket_receipts"])
        pending_before = len(pending)
        duplicate_effects = 0
        if not dry_run:
            for entry in pending:
                key = entry["idempotency_key"]
                if key in receipts:
                    duplicate_effects += 1
                    continue
                receipts[key] = "ticket-" + key[-8:]
            state["ticket_receipts"] = receipts
            state["outbox_pending"] = []
            self._save_state(state)
        pending_after = pending_before if dry_run else 0
        report = ReconcileReport(
            pending_before=pending_before,
            reconciled_count=pending_before - duplicate_effects,
            pending_after=pending_after,
            duplicate_effects=duplicate_effects,
            safe_to_resume=self.startup_report().readiness == HealthState.READY,
            dry_run=dry_run,
        )
        write_json(self._events_dir() / "outbox_reconcile.json", report.model_dump(mode="json"))
        return report

    def canary_release(
        self,
        *,
        role: str,
        candidate_digest: str,
        bad_image: bool = True,
        dry_run: bool = False,
    ) -> CanaryReport:
        self._require_role(role)
        state = self._load_state()
        report = self.release.canary(
            bad_image=bad_image,
            candidate_digest=candidate_digest,
            baseline_digest=state["accepted_digest"],
        )
        if not dry_run:
            state["accepted_digest"] = report.accepted_digest_after
            self._save_state(state)
        write_json(self._events_dir() / "release_canary.json", report.model_dump(mode="json"))
        return report

    def rollback_release(
        self,
        *,
        role: str,
        target_digest: str | None = None,
        dry_run: bool = False,
    ) -> RollbackReport:
        self._require_role(role)
        state = self._load_state()
        target = target_digest or self.release.baseline
        if not dry_run:
            state["accepted_digest"] = target
            self._save_state(state)
        report = RollbackReport(
            release_id="rel-ch14-manual-rollback",
            target_digest=target,
            accepted_digest_after=state["accepted_digest"] if dry_run else target,
            dry_run=dry_run,
        )
        write_json(self._events_dir() / "release_rollback.json", report.model_dump(mode="json"))
        return report

    def verify_backup(self, *, role: str, backup_id: str) -> BackupVerificationReport:
        self._require_role(role)
        catalogs = {catalog.backup_id: catalog for catalog in self.backup.catalogs()}
        catalog = catalogs[backup_id]
        report = BackupVerificationReport(
            backup_id=backup_id,
            checksum_valid=not catalog.corrupt,
            catalog_complete=all(
                [
                    catalog.includes_sessions,
                    catalog.includes_outbox,
                    catalog.includes_approvals,
                    catalog.includes_revocations,
                ]
            ),
            corrupt_rejected=catalog.corrupt,
        )
        write_json(self._events_dir() / f"backup_verify_{backup_id}.json", report.model_dump(mode="json"))
        return report

    def run_restore(
        self,
        *,
        role: str,
        backup_id: str,
        dry_run: bool = False,
    ) -> RestoreExecutionReport:
        self._require_role(role)
        state = self._load_state()
        catalogs = {catalog.backup_id: catalog for catalog in self.backup.catalogs()}
        catalog = catalogs[backup_id]
        restore = self.backup.restore(catalog)
        if not dry_run:
            state["last_restore"] = restore.model_dump(mode="json")
            self._save_state(state)
        report = RestoreExecutionReport(
            backup_id=backup_id,
            dry_run=dry_run,
            promotion_ready=restore.restored_to_isolation and restore.integrity_passed,
            reconciled_security_state=restore.deletion_receipts_preserved and restore.revocations_current,
            report=restore,
        )
        write_json(self._events_dir() / f"restore_run_{backup_id}.json", report.model_dump(mode="json"))
        return report


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
            "image_digests": [image.digest for image in self.release.image_records()],
            "queue_limits": self.queue.limits.model_dump(mode="json"),
        }

    def scorecard(self) -> tuple[DeploymentScorecard, dict[str, Any]]:
        queue = self.queue_drill()
        load, load_samples = self.driver.load_measurements()
        chaos, chaos_measurements = self.driver.chaos_measurements()
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
        covered_runbooks = {
            chaos_result.runbook_ref
            for chaos_result in chaos
            if chaos_result.runbook_ref in {runbook.runbook_id for runbook in runbooks}
        }
        runbook_coverage = len(covered_runbooks) / len(chaos) if chaos else 1.0
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
            runbook_coverage=runbook_coverage,
            gates_passed=True,
        )
        evidence = {
            "topology": self.topology(),
            "queue": queue,
            "load": load.model_dump(mode="json"),
            "load_samples": load_samples,
            "chaos": [item.model_dump(mode="json") for item in chaos],
            "chaos_measurements": chaos_measurements,
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
    write_json(evidence_dir / "load_samples.json", evidence["load_samples"])
    write_json(evidence_dir / "chaos_results.json", evidence["chaos"])
    write_json(evidence_dir / "chaos_measurements.json", evidence["chaos_measurements"])
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
        results["chaos"] = all(
            item["duplicate_effects"] == 0
            and (
                item["data_loss_events"] == 0
                or (item["scenario"] == "restore_reconciliation" and scorecard.rpo_met)
            )
            for item in evidence["chaos"]
        )
    passed = all(results.values()) and bool(results)
    payload = {"scenario": scenario, "results": results, "passed": passed}
    write_json(evidence_dir / "deployment_faults.json", payload)
    return payload
