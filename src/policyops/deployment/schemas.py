"""Chapter 14 deployment and recovery schemas."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    THROTTLING = "throttling"
    TIMEOUT = "timeout"
    SEMANTIC = "semantic"
    POLICY = "policy"
    AUTHORIZATION = "authorization"
    PERMANENT = "permanent"


class HealthState(str, Enum):
    LIVE = "live"
    STARTUP = "startup"
    READY = "ready"
    NOT_READY = "not_ready"


class OfferStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED_429 = "rejected_429"
    REJECTED_DEADLINE = "rejected_deadline"
    REJECTED_PAYLOAD = "rejected_payload"


class WorkState(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    ACKED = "acked"
    TERMINAL = "terminal"


class ExecutionEnvelope(StrictModel):
    correlation_id: str
    session_id: str
    tenant_id: str
    actor_id: str
    configuration_hash: str
    deadline_ms: int
    cancellation_token: str
    authorization_ref: str
    approval_ref: str | None
    idempotency_key: str | None
    budget_cents: int


class AdmissionLimits(StrictModel):
    max_queue_depth: int
    global_concurrency: int
    per_tenant_concurrency: int
    max_payload_bytes: int
    min_deadline_ms: int
    tenant_weights: dict[str, int]


class WorkItem(StrictModel):
    item_id: str
    envelope: ExecutionEnvelope
    priority: int
    payload_bytes: int
    available_at_ms: int = 0
    attempts: int = 0
    state: WorkState = WorkState.QUEUED
    claim_owner: str | None = None
    claim_expires_at_ms: int | None = None


class OfferResult(StrictModel):
    status: OfferStatus
    retry_after_ms: int | None = None
    reason: str
    enqueued: bool


class WorkLease(StrictModel):
    item_id: str
    worker_id: str
    fencing_token: int
    expires_at_ms: int


class RetryPolicy(StrictModel):
    failure_class: FailureClass
    retryable: bool
    max_attempts: int
    max_elapsed_ms: int
    backoff_ms: int


class CircuitBreakerState(StrictModel):
    dependency: str
    open: bool
    failures: int
    half_open_probe_budget_used: bool = False


class ModelRouteDecision(StrictModel):
    provider: str | None
    mode: Literal["normal", "degraded", "unavailable"]
    quality_floor: float
    provider_quality: float | None
    reason: str


class HealthReport(StrictModel):
    service: str
    liveness: HealthState
    startup: HealthState
    readiness: HealthState
    dependency_ready: bool
    schema_compatible: bool
    safe_to_resume: bool
    public_reason: str


class MigrationPlan(StrictModel):
    migration_id: str
    phase: Literal["expand", "migrate", "contract"]
    compatible_with_current_binary: bool
    preflight_passed: bool
    transactional: bool
    rollback_or_rollforward: str
    clean_database_verified: bool


class ImageRecord(StrictModel):
    service: str
    digest: str
    non_root: bool
    read_only_root: bool
    sbom_valid: bool
    policy_passed: bool

    @model_validator(mode="after")
    def _digest_pinned(self) -> ImageRecord:
        if not self.digest.startswith("sha256:"):
            raise ValueError("image must be digest pinned")
        return self


class CanaryReport(StrictModel):
    release_id: str
    baseline_digest: str
    candidate_digest: str
    health_passed: bool
    error_rate: float
    saturation: float
    smoke_passed: bool
    policy_passed: bool
    decision: Literal["promote", "rollback"]
    accepted_digest_after: str

    @model_validator(mode="after")
    def _rollback_restores_baseline(self) -> CanaryReport:
        if self.decision == "rollback" and self.accepted_digest_after != self.baseline_digest:
            raise ValueError("container rollback must restore accepted baseline digest")
        return self


class BackupCatalog(StrictModel):
    backup_id: str
    checksum: str
    migration_level: str
    includes_sessions: bool
    includes_outbox: bool
    includes_approvals: bool
    includes_revocations: bool
    corrupt: bool = False


class RestoreReport(StrictModel):
    backup_id: str
    corrupt_rejected: bool
    restored_to_isolation: bool
    integrity_passed: bool
    rto_seconds: int
    rpo_seconds: int
    deletion_receipts_preserved: bool
    revocations_current: bool


class LoadReport(StrictModel):
    workload: str
    hardware: str
    concurrency: int
    queue_depth_max: int
    queue_depth_limit: int
    p95_latency_ms: int
    p95_threshold_ms: int
    error_rate: float
    error_threshold: float
    tenant_fairness_ratio: float
    overload_429_count: int


class ChaosResult(StrictModel):
    scenario: str
    detected: bool
    automatic_response: str
    recovery_seconds: int
    data_loss_events: int
    duplicate_effects: int
    runbook_ref: str


class RunbookStep(StrictModel):
    runbook_id: str
    diagnose: str
    contain: str
    recover: str
    validation: str
    escalate: str


class DependencyDiagnostic(StrictModel):
    dependency: str
    healthy: bool
    reason_code: str
    bounded_detail: str


class DeploymentStatusEnvelope(StrictModel):
    accepted_digest: str
    startup: HealthState
    readiness: HealthState
    queue_depth: int
    outbox_pending: int
    containment_mode: bool
    diagnostics: list[DependencyDiagnostic]


class QueueDrainReport(StrictModel):
    queue_depth_before: int
    drained_count: int
    queue_depth_after: int
    containment_mode: bool
    dry_run: bool


class ReconcileReport(StrictModel):
    pending_before: int
    reconciled_count: int
    pending_after: int
    duplicate_effects: int
    safe_to_resume: bool
    dry_run: bool


class RollbackReport(StrictModel):
    release_id: str
    target_digest: str
    accepted_digest_after: str
    dry_run: bool


class BackupVerificationReport(StrictModel):
    backup_id: str
    checksum_valid: bool
    catalog_complete: bool
    corrupt_rejected: bool


class RestoreExecutionReport(StrictModel):
    backup_id: str
    dry_run: bool
    promotion_ready: bool
    reconciled_security_state: bool
    report: RestoreReport


class DeploymentScorecard(StrictModel):
    schema_version: Literal["1"] = "1"
    queue_bound_held: bool
    duplicate_tickets: int
    retry_budget_violations: int
    compliant_model_fallback: bool
    readiness_distinguishes_safe_resume: bool
    bad_image_rolled_back: bool
    corrupt_backup_rejected: bool
    valid_restore_integrity: bool
    rto_met: bool
    rpo_met: bool
    p95_met: bool
    error_slo_met: bool
    network_probe_denied: bool
    secret_leaks: int
    runbook_coverage: float
    gates_passed: bool

    @model_validator(mode="after")
    def _hard_gates(self) -> DeploymentScorecard:
        if self.gates_passed and (
            not self.queue_bound_held
            or self.duplicate_tickets
            or self.retry_budget_violations
            or not self.compliant_model_fallback
            or not self.readiness_distinguishes_safe_resume
            or not self.bad_image_rolled_back
            or not self.corrupt_backup_rejected
            or not self.valid_restore_integrity
            or not self.rto_met
            or not self.rpo_met
            or not self.p95_met
            or not self.error_slo_met
            or not self.network_probe_denied
            or self.secret_leaks
            or self.runbook_coverage < 1.0
        ):
            raise ValueError("deployment scorecard cannot pass with reliability gaps")
        return self
