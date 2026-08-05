"""Bounded orchestration schemas — Chapter 10."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TopologyVariant(str, Enum):
    WORKFLOW = "workflow"
    SINGLE_AGENT = "single_agent"
    BROWSER = "browser_computer_use"
    ORCHESTRATOR_WORKER = "orchestrator_worker"


class RunStatus(str, Enum):
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TerminalReason(str, Enum):
    COMPLETED = "completed"
    CAPACITY_UNAVAILABLE = "capacity_unavailable"
    CONFLICTING_RESULTS = "conflicting_results"
    MERGE_COLLISION = "merge_collision"
    INVALID_DELEGATION = "invalid_delegation"
    BROWSER_PROFILE_MISMATCH = "browser_profile_mismatch"
    APPROVAL_DENIED = "approval_denied"
    CANCELLED_BY_OPERATOR = "cancelled_by_operator"


class FindingKind(str, Enum):
    EVIDENCE = "evidence"
    RISK = "risk"
    TICKET_READY = "ticket_ready"


class PrincipalRef(StrictModel):
    run_context_hash: str
    request_id: str
    trace_id: str
    actor_id: str
    tenant_id: str
    roles: list[str]
    scopes: list[str]
    data_classification: str
    configuration_id: str


class Finding(StrictModel):
    finding_id: str
    kind: FindingKind
    text: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class BudgetLedger(StrictModel):
    worker_limit: int = 2
    model_call_limit: int = 1
    tool_call_limit: int = 3
    token_limit: int = 1600
    spend_limit_cents: int = 10
    reserved_workers: int = 0
    consumed_workers: int = 0
    consumed_model_calls: int = 0
    consumed_tool_calls: int = 0
    consumed_tokens: int = 0
    consumed_spend_cents: int = 0

    def can_reserve(self, workers: int, model_calls: int = 0, tool_calls: int = 0) -> bool:
        return (
            self.reserved_workers + workers <= self.worker_limit
            and self.consumed_model_calls + model_calls <= self.model_call_limit
            and self.consumed_tool_calls + tool_calls <= self.tool_call_limit
        )


class TaskState(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    version: int = 1
    variant: TopologyVariant
    status: RunStatus
    principal: PrincipalRef
    evidence_refs: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    proposed_effect_hash: str | None = None
    ticket_id: str | None = None
    terminal_reason: TerminalReason | None = None
    budget: BudgetLedger = Field(default_factory=BudgetLedger)
    delegated_task_ids: list[str] = Field(default_factory=list)
    browser_actions: list[str] = Field(default_factory=list)
    model_calls: int = 0
    trace: list[str] = Field(default_factory=list)


class TransitionEvent(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    sequence: int
    event_type: str
    status: RunStatus
    terminal_reason: TerminalReason | None = None
    trace_code: str
    occurred_at: int


class BudgetEntry(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    sequence: int
    action: Literal["reserve", "consume", "release", "cancel_release"]
    reserved_workers: int
    consumed_workers: int
    consumed_model_calls: int
    consumed_tool_calls: int
    budget_snapshot: BudgetLedger
    occurred_at: int


class DelegatedTask(StrictModel):
    task_id: str
    run_id: str
    parent_delegation_id: str | None = None
    principal: PrincipalRef
    worker_id: str
    objective: str
    evidence_allowlist: list[str]
    tool_allowlist: list[str]
    budget_tokens: int
    output_schema: str
    success_criteria: list[str]
    expires_at: int
    nonce: str
    signature: str


class WorkerResult(StrictModel):
    result_id: str
    task_id: str
    run_id: str
    worker_id: str
    findings: list[Finding]
    evidence_refs: list[str]
    usage_tokens: int
    completed_at: int
    signature: str


class BrowserObservation(StrictModel):
    fixture_id: str
    profile_id: str
    dom_hash: str
    screen_hash: str
    fields: dict[str, str]


class BrowserActionTrace(StrictModel):
    action_id: str
    fixture_id: str
    profile_id: str
    action: str
    selector: str
    value_hash: str
    trusted: Literal[False] = False


class TopologyMetrics(StrictModel):
    variant: TopologyVariant
    task_success: bool
    latency_ms: int
    model_calls: int
    tool_calls: int
    worker_calls: int
    browser_actions: int
    estimated_cost_cents: int
    cost_per_successful_outcome_cents: int | None = None
    trace_steps: int = 0
    risk_events: int


class TopologyComparison(StrictModel):
    schema_version: Literal["1"] = "1"
    metrics: list[TopologyMetrics]
    selected_variant: TopologyVariant
    adr_decision: str
    a2a_decision: str

    @model_validator(mode="after")
    def _selected_present(self) -> TopologyComparison:
        if self.selected_variant not in {metric.variant for metric in self.metrics}:
            raise ValueError("selected variant must be in metrics")
        return self


class OrchestrationScorecard(StrictModel):
    schema_version: Literal["1"] = "1"
    deterministic_agreement: bool
    approval_bypasses: int
    authority_widening: int
    invalid_delegations_rejected: int
    browser_bypass_attempts: int
    capacity_partial_spawns: int
    finite_termination: bool
    gates_passed: bool

    @model_validator(mode="after")
    def _hard_gates(self) -> OrchestrationScorecard:
        if self.gates_passed and (
            not self.deterministic_agreement
            or self.approval_bypasses
            or self.authority_widening
            or self.capacity_partial_spawns
            or not self.finite_termination
        ):
            raise ValueError("orchestration hard gates cannot pass with boundary failures")
        return self


class TriageRunRequest(StrictModel):
    scenario_id: str = "policy-triage-default"
    variant: TopologyVariant
    budget: BudgetLedger | None = None
    browser_profile: str | None = None
    idempotency_key: str | None = None


class TriageControlRequest(StrictModel):
    expected_version: int = Field(ge=1)


class TriageRunEnvelope(StrictModel):
    run: TaskState
    delegated_tasks: list[DelegatedTask] = Field(default_factory=list)
    worker_results: list[WorkerResult] = Field(default_factory=list)
    available_controls: list[str] = Field(default_factory=list)
    scenario_id: str = "policy-triage-default"
    idempotency_key: str | None = None
