"""Governed long-term memory schemas — Chapter 8."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MemoryKind(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryScope(str, Enum):
    PERSONAL = "personal"
    TEAM = "team"
    TENANT = "tenant"
    GLOBAL = "global"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    QUARANTINED = "quarantined"
    DELETED = "deleted"
    EXPIRED = "expired"


class MutationAction(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NOOP = "NOOP"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"


SENSITIVITY_RANK = {
    Sensitivity.PUBLIC: 0,
    Sensitivity.INTERNAL: 1,
    Sensitivity.CONFIDENTIAL: 2,
}


class Principal(StrictModel):
    tenant_id: str
    subject_id: str
    actor_id: str
    capabilities: list[str] = Field(default_factory=list)


class ConsentReceipt(StrictModel):
    consent_id: str
    tenant_id: str
    subject_id: str
    purpose: str
    sensitivity: Sensitivity
    valid_until: int | None = None

    def active_for(self, *, now: int, purpose: str, sensitivity: Sensitivity) -> bool:
        if self.purpose != purpose:
            return False
        if self.valid_until is not None and self.valid_until <= now:
            return False
        return SENSITIVITY_RANK[self.sensitivity] >= SENSITIVITY_RANK[sensitivity]


class MemoryPolicy(StrictModel):
    policy_id: str = "memory-policy-v1"
    allowed_scopes: list[MemoryScope] = Field(
        default_factory=lambda: [
            MemoryScope.PERSONAL,
            MemoryScope.TEAM,
            MemoryScope.TENANT,
        ]
    )
    allowed_purposes: list[str] = Field(default_factory=lambda: ["policy_support", "evaluation"])
    max_sensitivity_without_consent: Sensitivity = Sensitivity.INTERNAL
    ttl_seconds: int = 31_536_000
    min_consolidation_members: int = 2


class MemoryProposal(StrictModel):
    proposal_id: str
    tenant_id: str
    subject_id: str
    actor_id: str
    kind: MemoryKind
    scope: MemoryScope
    text: str = Field(min_length=1)
    purpose: str
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_ref: str
    consent_id: str | None = None
    valid_from: int
    expires_at: int | None = None
    expected_version: int | None = None
    target_record_id: str | None = None
    approval_ref: str | None = None


class MutationDecision(StrictModel):
    proposal_id: str
    action: MutationAction
    reason_codes: list[str]
    target_record_id: str | None = None
    status: MemoryStatus | None = None
    expected_version: int | None = None

    @property
    def write_allowed(self) -> bool:
        return self.action in {MutationAction.ADD, MutationAction.UPDATE, MutationAction.DELETE}


class MemoryRecord(StrictModel):
    schema_version: Literal["1"] = "1"
    record_id: str
    tenant_id: str
    subject_id: str
    actor_id: str
    kind: MemoryKind
    scope: MemoryScope
    text: str
    normalized_text: str
    purpose: str
    sensitivity: Sensitivity
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: str
    source_hash: str
    consent_id: str | None = None
    valid_from: int
    expires_at: int | None = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    version: int = Field(default=1, ge=1)
    created_at: int
    updated_at: int
    supersedes: str | None = None
    parent_record_ids: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)

    def is_effective(self, as_of: int) -> bool:
        if self.status != MemoryStatus.ACTIVE:
            return False
        if self.valid_from > as_of:
            return False
        return self.expires_at is None or self.expires_at > as_of


class MemoryEvent(StrictModel):
    event_id: str
    proposal_id: str
    action: MutationAction
    record_id: str | None
    tenant_id: str
    subject_id: str
    reason_codes: list[str]
    created_at: int
    version: int
    content_hash: str | None = None


class RecallRequest(StrictModel):
    request_id: str
    tenant_id: str
    subject_id: str
    actor_id: str
    purpose: str
    query: str
    allowed_scopes: list[MemoryScope]
    allowed_sensitivity: Sensitivity = Sensitivity.INTERNAL
    as_of: int
    max_items: int = Field(default=5, ge=1)


class RecallItem(StrictModel):
    record_id: str
    kind: MemoryKind
    scope: MemoryScope
    text: str
    source_ref: str
    source_hash: str
    sensitivity: Sensitivity
    version: int
    reason_codes: list[str]
    trust_label: Literal["untrusted_memory"] = "untrusted_memory"
    can_grant_authority: Literal[False] = False


class RecallExclusion(StrictModel):
    record_id: str
    reason_code: str


class RecallResult(StrictModel):
    request_id: str
    items: list[RecallItem]
    exclusions: list[RecallExclusion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=lambda: ["memory_is_untrusted_not_authority"])


class DeletionReceipt(StrictModel):
    receipt_id: str
    tenant_id: str
    subject_id: str
    record_ids: list[str]
    redacted_hashes: list[str]
    deleted_at: int
    content_removed: Literal[True] = True
    contains_deleted_text: Literal[False] = False


class ExportRecord(StrictModel):
    record_id: str
    kind: MemoryKind
    scope: MemoryScope
    purpose: str
    sensitivity: Sensitivity
    source_ref: str
    source_hash: str
    status: MemoryStatus
    version: int


class ExportJob(StrictModel):
    export_id: str
    tenant_id: str
    subject_id: str
    record_count: int
    created_at: int
    expires_at: int


class MemoryScorecard(StrictModel):
    schema_version: Literal["1"] = "1"
    mutation_decision_accuracy: float
    recall_precision: float
    correction_success: float
    deletion_coverage: float
    quarantine_precision: float
    tenant_violations: int
    authority_changes_from_memory: int
    no_memory_success_rate: float
    governed_memory_success_rate: float
    gates_passed: bool

    @model_validator(mode="after")
    def _hard_gates(self) -> MemoryScorecard:
        if self.gates_passed and (
            self.tenant_violations != 0
            or self.authority_changes_from_memory != 0
            or self.deletion_coverage < 1.0
        ):
            raise ValueError("memory hard gates cannot pass with isolation, authority, or deletion gaps")
        return self
