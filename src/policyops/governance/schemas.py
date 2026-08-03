"""Chapter 15 governance, rights, and release-decision schemas."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Decision(str, Enum):
    GO = "GO"
    NO_GO = "NO-GO"


class ReasonCode(str, Enum):
    OWNER_MISSING = "OWNER_MISSING"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    EVIDENCE_TAMPERED = "EVIDENCE_TAMPERED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    WRONG_CONFIGURATION = "WRONG_CONFIGURATION"
    TEST_FAILED = "TEST_FAILED"
    APPROVER_NOT_INDEPENDENT = "APPROVER_NOT_INDEPENDENT"
    RIGHTS_INCOMPLETE = "RIGHTS_INCOMPLETE"
    APPROVAL_MISSING = "APPROVAL_MISSING"
    OK = "OK"


class OwnerRecord(StrictModel):
    owner_id: str
    name: str
    role: str
    current: bool = True
    backup_owner_id: str | None = None


class SystemInventory(StrictModel):
    inventory_id: str
    purpose: str
    users: list[str]
    affected_parties: list[str]
    components: list[str]
    stores: list[str]
    ai_components: list[str]
    tools: list[str]
    owners: list[str]
    non_goals: list[str]


class RiskRecord(StrictModel):
    risk_id: str
    use_case: str
    impact: Literal["low", "medium", "high"]
    autonomy_tier: Literal["assistive", "agentic_with_approval", "autonomous"]
    data_sensitivity: Literal["public", "internal", "private"]
    communication_reach: Literal["none", "internal", "external"]
    side_effects: bool
    oversight_mode: str
    prohibited_use: str
    residual_risk: str
    owner_id: str


class ApprovalPolicy(StrictModel):
    policy_id: str
    change_class: str
    required_role: str
    separation_of_duties: bool
    evidence_expiry_seconds: int
    escalation_path: str
    required_evidence_ids: list[str] = Field(default_factory=list)
    high_impact_required: bool = False


class SignatureEnvelope(StrictModel):
    artifact_hash: str
    schema_version: str
    configuration_scope: str
    issuer: str
    issuer_role: str
    issued_at: int
    expires_at: int
    purpose: str
    signature: str


class EvidenceRef(StrictModel):
    evidence_id: str
    control_id: str
    artifact_uri: str
    artifact_hash: str
    schema_version: str
    configuration_scope: str
    result: Literal["pass", "fail"]
    signature: SignatureEnvelope
    reviewed_by: str


class ControlRecord(StrictModel):
    control_id: str
    risk_id: str
    implementation: str
    test_id: str
    evidence_id: str
    owner_id: str
    mandatory: bool = True


class ChangeSet(StrictModel):
    change_set_id: str
    model_changed: bool = False
    data_changed: bool = False
    tool_changed: bool = False
    policy_changed: bool = False
    autonomy_changed: bool = False
    deployment_changed: bool = False
    owner_changed: bool = False
    retention_changed: bool = False

    def classes(self) -> list[str]:
        mapping = {
            "model": self.model_changed,
            "data": self.data_changed,
            "tool": self.tool_changed,
            "policy": self.policy_changed,
            "autonomy": self.autonomy_changed,
            "deployment": self.deployment_changed,
            "owner": self.owner_changed,
            "retention": self.retention_changed,
        }
        return [name for name, changed in mapping.items() if changed]


class RightsRequest(StrictModel):
    request_id: str
    tenant_id: str
    subject_id: str
    request_type: Literal["correction", "export", "deletion"]
    authenticated: bool
    scope: str


class RightsTaskRecord(StrictModel):
    task_id: str
    store: str
    request_type: Literal["correction", "export", "deletion"]
    status: Literal["pending", "completed", "failed"]
    completed_at: int | None = None
    verifier_passed: bool = False
    exception: str | None = None
    retention_basis: str | None = None
    follow_up_at: int | None = None


class StoreReceipt(StrictModel):
    store: str
    action: str
    completed_at: int
    verifier_passed: bool
    exception: str | None = None
    retention_basis: str | None = None
    follow_up_at: int | None = None


class RightsReceipt(StrictModel):
    receipt_id: str
    request_id: str
    tenant_id: str
    store_inventory_version: str
    workflow_id: str | None = None
    request_digest: str | None = None
    stores: list[StoreReceipt]
    complete: bool
    signed_hash: str

    @model_validator(mode="after")
    def _complete_requires_all_verifiers(self) -> RightsReceipt:
        if self.complete and not all(store.verifier_passed for store in self.stores):
            raise ValueError("complete rights receipt requires every store verifier")
        return self


class TransparencyNotice(StrictModel):
    notice_id: str
    ai_involvement: str
    sources: list[str]
    memory_use: str
    tools_and_actions: list[str]
    limits: list[str]
    human_oversight: str
    rights_channels: list[str]


class DecisionReason(StrictModel):
    priority: int
    record_id: str
    reason_code: ReasonCode
    remediation: str


class ReleaseDecision(StrictModel):
    decision_id: str
    decision: Decision
    policy_hash: str
    manifest_hash: str
    change_set_hash: str
    evidence_graph_hash: str
    approver_id: str | None
    reasons: list[DecisionReason] = Field(default_factory=list)
    decided_at: int
    decision_digest: str


class GovernanceScorecard(StrictModel):
    schema_version: Literal["1"] = "1"
    high_risk_paths_resolved: bool
    invalid_evidence_cases_blocked: int
    independent_approver_valid: bool
    rights_receipt_complete: bool
    transparency_notice_consistent: bool
    deterministic_digest: bool
    agent_self_approval_denied: bool
    secret_leaks: int
    gates_passed: bool

    @model_validator(mode="after")
    def _hard_gates(self) -> GovernanceScorecard:
        if self.gates_passed and (
            not self.high_risk_paths_resolved
            or self.invalid_evidence_cases_blocked < 5
            or not self.independent_approver_valid
            or not self.rights_receipt_complete
            or not self.transparency_notice_consistent
            or not self.deterministic_digest
            or not self.agent_self_approval_denied
            or self.secret_leaks
        ):
            raise ValueError("governance scorecard cannot pass with release-gate gaps")
        return self
