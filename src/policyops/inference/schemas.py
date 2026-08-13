"""Adaptive inference gateway schemas — Chapter 4."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TaskClass(str, Enum):
    POLICY_QA = "policy_qa"
    CLASSIFICATION = "classification"
    CONTROLLED_ACTION = "controlled_action"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasoningEffort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FailureReason(str, Enum):
    NONE = "none"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_VERIFIED_CANDIDATE = "no_verified_candidate"
    INVALID_CACHE_ENTRY = "invalid_cache_entry"
    AUTHORIZATION_DENIED = "authorization_denied"
    HARD_GATE_FAILED = "hard_gate_failed"


class InferenceBudget(StrictModel):
    max_input_tokens: int = Field(default=2048, ge=1)
    max_output_tokens: int = Field(default=512, ge=1)
    max_duration_ms: int = Field(default=5000, ge=1)
    max_spend_units: float = Field(default=25.0, ge=0)
    max_candidates: int = Field(default=3, ge=1, le=8)
    min_quality: float = Field(default=0.80, ge=0.0, le=1.0)


class InferenceRequest(StrictModel):
    schema_version: Literal["1"] = "1"
    request_id: str
    tenant_id: str
    actor_id: str
    authorization_fingerprint: str
    configuration_hash: str
    policy_version: str
    question: str = Field(min_length=1)
    task_class: TaskClass = TaskClass.POLICY_QA
    risk_tier: RiskTier = RiskTier.MEDIUM
    data_classification: Literal["public", "internal", "confidential"] = "internal"
    require_citations: bool = True
    authorized: bool = True
    cacheable: bool = True
    source_freshness: str = "fixture-v1"
    budget: InferenceBudget = Field(default_factory=InferenceBudget)


class ModelProfile(StrictModel):
    profile_id: str
    quality: float = Field(ge=0.0, le=1.0)
    latency_ms: int = Field(ge=1)
    cost_per_1k_tokens: float = Field(ge=0.0)
    supports_structured_output: bool = True
    max_output_tokens: int = Field(default=512, ge=1)
    quantized: bool = False
    draft_profile_id: str | None = None


class CacheKey(StrictModel):
    tenant_hash: str
    authorization_hash: str
    semantic_request_hash: str
    model_profile: str
    configuration_hash: str
    policy_hash: str
    source_freshness: str
    answer_schema: Literal["1"] = "1"


class VerificationResult(StrictModel):
    passed: bool
    quality_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    # Which gate produced this result. Hard-gate failures are never recoverable: they stop
    # the request outright. Quality-gate failures may be recoverable: they escalate to the
    # next model in the route sequence if budget remains.
    gate: Literal["hard", "quality"] = "quality"
    recoverable: bool = True


class CandidateResult(StrictModel):
    candidate_id: str
    profile_id: str
    text: str
    citations: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0)
    latency_ms: int = Field(ge=0)
    cost_units: float = Field(ge=0.0)
    valid: bool
    verifier_reasons: list[str] = Field(default_factory=list)
    cache_hit: bool = False
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM


class GatewayResult(StrictModel):
    schema_version: Literal["1"] = "1"
    request_id: str
    selected: CandidateResult | None = None
    candidates: list[CandidateResult] = Field(default_factory=list)
    route: list[str] = Field(default_factory=list)
    cache_status: Literal["hit", "miss", "bypass", "rejected"] = "miss"
    early_exit: bool = False
    budget_exhausted: bool = False
    duration_ms: int = Field(ge=0)
    spend_units: float = Field(ge=0.0)
    failure_reason: FailureReason = FailureReason.NONE

    @model_validator(mode="after")
    def _success_or_failure_is_explicit(self) -> GatewayResult:
        if self.selected is None and self.failure_reason == FailureReason.NONE:
            raise ValueError("unsuccessful gateway results require a failure_reason")
        return self


class CacheEntry(StrictModel):
    key: CacheKey
    candidate: CandidateResult
    created_ms: int = Field(ge=0)
    expires_ms: int = Field(ge=0)
    validator_version: Literal["verifier-v1"] = "verifier-v1"


class BenchmarkRow(StrictModel):
    """One (request, route profile, cache state) measurement. Raw rows are never compared
    for dominance across different `request_id`s — see `ProfileAggregate` and
    `gateway._dominance`, which operate only on per-profile aggregates."""

    request_id: str
    profile: str
    cache_state: Literal["cold", "warm"]
    success: bool
    quality: float
    latency_ms: int
    spend_units: float
    cost_per_successful_outcome: float | None
    selected_profile: str | None
    failure_reason: FailureReason = FailureReason.NONE


class ProfileAggregate(StrictModel):
    """Per-route-profile aggregate over ALL of that profile's rows (both cache states).
    This is the only level at which dominance / Pareto-frontier membership is computed —
    never on individual per-request rows (see `gateway._dominance`)."""

    profile: str
    row_count: int = Field(ge=1)
    success_count: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0)
    avg_quality: float = Field(ge=0.0, le=1.0)
    avg_latency_ms: float = Field(ge=0.0)
    p50_latency_ms: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)
    p99_latency_ms: float = Field(ge=0.0)
    total_spend_units: float = Field(ge=0.0)
    cost_per_successful_outcome: float | None
    clears_quality_floor: bool
    dominated: bool = False


class BenchmarkReport(StrictModel):
    schema_version: Literal["1"] = "1"
    workload_id: str
    quality_floor: float
    rows: list[BenchmarkRow]
    aggregates: list[ProfileAggregate]
    selected_profile: str
    pareto_profiles: list[str]


class MatchedPairOutcome(StrictModel):
    """One (request, unordered pair of route profiles) comparison. See `gateway._verdict`
    for the precise definition of "verdict" and `gateway._classify_pair` for the
    agreement/disagreement/reversal taxonomy."""

    request_id: str
    profile_a: str
    profile_b: str
    verdict_a: str
    verdict_b: str
    classification: Literal["agreement", "disagreement", "reversal"]


class MatchedPairComparison(StrictModel):
    schema_version: Literal["1"] = "1"
    workload_id: str
    outcomes: list[MatchedPairOutcome]
    agreement_count: int = Field(ge=0)
    disagreement_count: int = Field(ge=0)
    reversal_count: int = Field(ge=0)
    reversals: list[MatchedPairOutcome]
