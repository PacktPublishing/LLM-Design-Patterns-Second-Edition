"""Chapter 12 telemetry, experiment, and behavior-canary schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SpanKind(str, Enum):
    REQUEST = "request"
    MODEL = "model"
    RETRIEVAL = "retrieval"
    RERANK = "rerank"
    MEMORY = "memory"
    AGENT = "agent"
    HANDOFF = "handoff"
    BROWSER_OBSERVATION = "browser_observation"
    BROWSER_ACTION = "browser_action"
    APPROVAL = "approval"
    TOOL = "tool"
    SANDBOX = "sandbox"
    EXTERNAL_EFFECT = "external_effect"
    OUTCOME = "outcome"


class SamplingDecision(str, Enum):
    HEAD = "head"
    TAIL = "tail"
    REQUIRED = "required"
    DROPPED = "dropped"


class FailureClass(str, Enum):
    PRODUCT_FAILURE = "product_failure"
    PREFERENCE = "preference"
    UNSUPPORTED_REQUEST = "unsupported_request"
    INFRASTRUCTURE_NOISE = "infrastructure_noise"
    SECURITY_EVENT = "security_event"


class ExperimentDecision(str, Enum):
    KEEP = "keep"
    REVERT = "revert"


class CanaryDecision(str, Enum):
    PROMOTE = "promote"
    ROLLBACK = "rollback"
    HOLD = "hold"


class ArtifactRecord(StrictModel):
    artifact_type: str
    name: str
    version: str
    digest: str

    @model_validator(mode="after")
    def _digest_is_sha(self) -> ArtifactRecord:
        if not self.digest.startswith("sha256:"):
            raise ValueError("artifact digest must use sha256")
        return self


class ArtifactSet(StrictModel):
    artifact_set_id: str
    artifacts: list[ArtifactRecord]

    def by_type(self) -> dict[str, ArtifactRecord]:
        return {artifact.artifact_type: artifact for artifact in self.artifacts}


class TraceContext(StrictModel):
    correlation_id: str
    request_id: str
    tenant_hash: str
    actor_class: Literal["reader", "operator", "domain_expert", "engineer"]
    session_id: str
    artifact_set_id: str
    risk_tier: Literal["low", "medium", "high"]
    sampling_decision: SamplingDecision = SamplingDecision.HEAD


class RawEvent(StrictModel):
    provider: str
    event_name: str
    span_kind: SpanKind
    correlation_id: str
    request_id: str
    tenant_id: str
    actor_id: str
    session_id: str
    artifact_set_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    started_at_ms: int
    ended_at_ms: int


class RedactedSpan(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    name: str
    span_kind: SpanKind
    context: TraceContext
    attributes: dict[str, str | int | float | bool]
    duration_ms: int
    redacted_fields: list[str] = Field(default_factory=list)
    dropped_fields: list[str] = Field(default_factory=list)


class SloRecord(StrictModel):
    name: str
    owner: str
    window: str
    objective: str
    measurement_query: str
    budget: str


class TraceAdjudication(StrictModel):
    adjudication_id: str
    correlation_id: str
    expert_role: str
    failure_class: FailureClass
    evidence_refs: list[str]
    expected_behavior: str | None = None
    may_graduate: bool

    @model_validator(mode="after")
    def _graduation_requires_product_failure(self) -> TraceAdjudication:
        if self.may_graduate and self.failure_class != FailureClass.PRODUCT_FAILURE:
            raise ValueError("only expert-adjudicated product failures may graduate")
        if self.may_graduate and not self.expected_behavior:
            raise ValueError("graduated failures require expected behavior")
        return self


class EvaluationCase(StrictModel):
    case_id: str
    source_correlation_id: str
    adjudication_id: str
    expected_behavior: str
    redacted_trace_hash: str
    protected_split: Literal["target", "regression", "safety", "holdout"]
    source_refs: list[str]


class ExperimentManifest(StrictModel):
    experiment_id: str
    baseline_hash: str
    candidate_hash: str
    writable_surface: str
    trial_budget: int
    suites: list[Literal["target", "regression", "safety", "holdout"]]
    protected_hashes: dict[str, str]
    decision_rule: Literal["all_mandatory_gates_and_target_gain"]

    @model_validator(mode="after")
    def _one_surface_and_all_suites(self) -> ExperimentManifest:
        if self.trial_budget <= 0:
            raise ValueError("trial budget must be positive")
        required = {"target", "regression", "safety", "holdout"}
        if set(self.suites) != required:
            raise ValueError("experiments must run target, regression, safety, and holdout")
        return self


class SuiteResult(StrictModel):
    suite: Literal["target", "regression", "safety", "holdout"]
    baseline_score: float
    candidate_score: float
    baseline_cost_cents: float
    candidate_cost_cents: float
    successful_outcomes: int

    @property
    def candidate_cost_per_success(self) -> float:
        if self.successful_outcomes <= 0:
            return float("inf")
        return round(self.candidate_cost_cents / self.successful_outcomes, 4)


class ExperimentLedger(StrictModel):
    manifest: ExperimentManifest
    results: list[SuiteResult]
    protected_hashes_before: dict[str, str]
    protected_hashes_after: dict[str, str]
    decision: ExperimentDecision
    reason: str

    @model_validator(mode="after")
    def _hashes_match_for_keep(self) -> ExperimentLedger:
        if self.protected_hashes_before != self.protected_hashes_after:
            if self.decision == ExperimentDecision.KEEP:
                raise ValueError("cannot keep candidate after protected hash drift")
        return self


class CanaryMetric(StrictModel):
    window: str
    baseline_success_rate: float
    candidate_success_rate: float
    baseline_cost_per_success: float
    candidate_cost_per_success: float
    p95_latency_ms: int
    safety_incidents: int


class CanaryReport(StrictModel):
    canary_id: str
    baseline_alias_before: str
    candidate_hash: str
    stop_conditions: list[str]
    metrics: CanaryMetric
    decision: CanaryDecision
    accepted_alias_after: str
    rollback_reason: str | None = None

    @model_validator(mode="after")
    def _rollback_restores_baseline(self) -> CanaryReport:
        if self.decision == CanaryDecision.ROLLBACK:
            if self.accepted_alias_after != self.baseline_alias_before:
                raise ValueError("rollback must restore the baseline alias")
            if not self.rollback_reason:
                raise ValueError("rollback requires a reason")
        return self


class ReconstructionReport(StrictModel):
    correlation_id: str
    reconstructed_span_count: int
    external_calls_attempted: int
    model_calls_attempted: int
    tool_calls_attempted: int
    safe: bool


class HarnessRetirementAdr(StrictModel):
    adr_id: str
    scaffold: str
    measured_benefit: str
    decision: Literal["keep", "retire"]
    rollback_path: str


class ObservabilityScorecard(StrictModel):
    schema_version: Literal["1"] = "1"
    correlation_coverage: float
    pii_leaks: int
    secret_leaks: int
    cardinality_violations: int
    graduated_cases_with_provenance: int
    overfit_rejected: bool
    bad_canary_rolled_back: bool
    telemetry_outage_request_failures: int
    reconstruction_external_calls: int
    cost_per_success_reported: bool
    slo_owner_coverage: float
    gates_passed: bool

    @model_validator(mode="after")
    def _hard_gates(self) -> ObservabilityScorecard:
        if self.gates_passed and (
            self.correlation_coverage < 1.0
            or self.pii_leaks
            or self.secret_leaks
            or self.cardinality_violations
            or self.graduated_cases_with_provenance < 1
            or not self.overfit_rejected
            or not self.bad_canary_rolled_back
            or self.telemetry_outage_request_failures
            or self.reconstruction_external_calls
            or not self.cost_per_success_reported
            or self.slo_owner_coverage < 1.0
        ):
            raise ValueError("observability scorecard cannot pass with unsafe evidence")
        return self


class OperationEnvelope(StrictModel):
    correlation_id: str
    artifacts: ArtifactSet
    spans: list[RedactedSpan]
    slos: list[SloRecord]


class AdjudicationRequest(StrictModel):
    correlation_id: str
    failure_class: FailureClass
    expert_role: str
    expected_behavior: str | None = None


class AdjudicationEnvelope(StrictModel):
    adjudication: TraceAdjudication
    evaluation_case: EvaluationCase | None = None


class ExperimentRunRequest(StrictModel):
    candidate_profile: Literal["overfit", "accepted"] = "overfit"


class ExperimentEnvelope(StrictModel):
    ledger: ExperimentLedger
    active_canary_id: str | None = None


class CanaryStopRequest(StrictModel):
    reason: str = "operator stopped canary"
