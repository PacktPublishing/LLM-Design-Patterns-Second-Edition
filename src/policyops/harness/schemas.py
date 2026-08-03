"""Resumable agent-loop schemas — Chapter 11."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SessionPhase(str, Enum):
    TRIGGERED = "triggered"
    PLANNED = "planned"
    ACTION_READY = "action_ready"
    EFFECT_DELIVERED = "effect_delivered"
    VERIFIED = "verified"
    STOPPED = "stopped"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    SESSION_CREATED = "session_created"
    PLAN_RECORDED = "plan_recorded"
    ACTION_READY = "action_ready"
    OUTBOX_CREATED = "outbox_created"
    EFFECT_RECEIPT = "effect_receipt"
    CHECKPOINT_WRITTEN = "checkpoint_written"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


class FailureClass(str, Enum):
    TRANSIENT = "transient_dependency"
    SEMANTIC = "semantic_model_output"
    POLICY = "policy"
    AUTHORIZATION = "authorization"
    VERIFICATION = "verification_mismatch"
    PERMANENT = "permanent_input"
    BUDGET = "budget_exhaustion"


class ReviewStage(str, Enum):
    INSPECT = "inspect"
    PLAN = "plan"
    CHANGE = "change"
    AUTOMATED_VERIFY = "automated_verify"
    DIRECT_QA = "direct_qa"
    FRESH_REVIEW = "fresh_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SessionEvent(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: str
    sequence: int
    event_type: EventType
    request_id: str
    trace_id: str
    tenant_id: str
    actor_id: str
    configuration_id: str
    prior_state: SessionPhase | None
    new_state: SessionPhase
    fencing_token: int
    payload_hash: str | None = None
    occurred_at: int


class BudgetSnapshot(StrictModel):
    iteration_limit: int = 4
    tool_call_limit: int = 4
    effect_limit: int = 1
    spend_limit_cents: int = 10
    iterations: int = 0
    tool_calls: int = 0
    effects: int = 0
    spend_cents: int = 0

    def exhausted(self) -> bool:
        return (
            self.iterations >= self.iteration_limit
            or self.tool_calls >= self.tool_call_limit
            or self.effects >= self.effect_limit
            or self.spend_cents >= self.spend_limit_cents
        )


class SessionState(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: str
    version: int
    state: SessionPhase
    tenant_id: str
    actor_id: str
    request_id: str
    trace_id: str
    configuration_id: str
    budget: BudgetSnapshot = Field(default_factory=BudgetSnapshot)
    pending_action_id: str | None = None
    approval_reference: str | None = None
    ticket_id: str | None = None
    terminal_reason: FailureClass | None = None


class SessionCheckpoint(StrictModel):
    session_id: str
    event_sequence: int
    state_hash: str
    state: SessionState
    created_at: int


class Lease(StrictModel):
    session_id: str
    owner_id: str
    fencing_token: int
    expires_at: int
    renewed_at: int


class ActionIntent(StrictModel):
    intent_id: str
    session_id: str
    tenant_id: str
    actor_id: str
    capability: Literal["ticket.create"] = "ticket.create"
    effect_hash: str
    idempotency_key: str
    approval_reference: str
    approval_expires_at: int
    configuration_id: str
    expected_postcondition: dict[str, int]


class OutboxMessage(StrictModel):
    message_id: str
    intent_id: str
    session_id: str
    tenant_id: str
    idempotency_key: str
    delivered: bool = False
    attempts: int = 0


class EffectReceipt(StrictModel):
    tenant_id: str
    capability: str
    idempotency_key: str
    effect_hash: str
    external_reference: str
    status: Literal["confirmed", "reconciled", "failed"]
    observed_postcondition: dict[str, int]
    recorded_at: int


class ScopedPlan(StrictModel):
    plan_id: str
    allowed_paths: list[str]
    explicit_exclusions: list[str]
    acceptance_checks: list[str]


class ReviewBundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: str
    stage: ReviewStage
    plan_hash: str
    changed_paths: list[str]
    diff_hash: str
    checks: dict[str, bool]
    direct_qa_hash: str
    findings: list[str] = Field(default_factory=list)
    accepted: bool

    @model_validator(mode="after")
    def _accepted_has_no_findings(self) -> ReviewBundle:
        if self.accepted and self.findings:
            raise ValueError("accepted review bundle cannot contain blocking findings")
        return self


class FaultScenario(str, Enum):
    BEFORE_EFFECT = "before_effect"
    AFTER_EFFECT_BEFORE_ACK = "after_effect_before_ack"
    AFTER_CHECKPOINT = "after_checkpoint"
    LEASE_CONTENTION = "lease_contention"


class HarnessScorecard(StrictModel):
    schema_version: Literal["1"] = "1"
    crash_cases_recovered: int
    duplicate_tickets: int
    out_of_scope_changes: int
    stale_fence_writes_rejected: int
    replay_external_calls: int
    approval_mismatch_denials: int
    budget_stops: int
    gates_passed: bool

    @model_validator(mode="after")
    def _hard_gates(self) -> HarnessScorecard:
        if self.gates_passed and (
            self.duplicate_tickets
            or self.out_of_scope_changes
            or self.replay_external_calls
            or not self.stale_fence_writes_rejected
        ):
            raise ValueError("harness gates cannot pass with duplicate effects or unsafe replay")
        return self


class SessionRunRequest(StrictModel):
    expected_version: int | None = Field(default=None, ge=0)
    owner_id: str = "worker-a"
    budget: BudgetSnapshot | None = None
    fault: FaultScenario | None = None


class SessionResumeRequest(StrictModel):
    expected_version: int | None = Field(default=None, ge=0)
    owner_id: str = "worker-b"


class SessionCancelRequest(StrictModel):
    expected_version: int | None = Field(default=None, ge=0)
    owner_id: str = "operator-a"


class SessionEnvelope(StrictModel):
    session: SessionState
    lease: Lease | None = None
    checkpoint: SessionCheckpoint | None = None
    events: list[SessionEvent] = Field(default_factory=list)
    pending_outbox: list[OutboxMessage] = Field(default_factory=list)
    receipts: list[EffectReceipt] = Field(default_factory=list)
