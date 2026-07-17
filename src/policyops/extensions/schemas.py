"""Secure extension-pack schemas — Chapter 9."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ImpactClass(str, Enum):
    READ = "read"
    WRITE = "write"


class DomainErrorCode(str, Enum):
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_STALE = "APPROVAL_STALE"
    EFFECT_MISMATCH = "EFFECT_MISMATCH"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    EXTENSION_DISABLED = "EXTENSION_DISABLED"
    EXTENSION_REVOKED = "EXTENSION_REVOKED"
    HOOK_TIMEOUT = "HOOK_TIMEOUT"
    PACKAGE_TAMPERED = "PACKAGE_TAMPERED"
    PACKAGE_INCOMPATIBLE = "PACKAGE_INCOMPATIBLE"
    UNAUTHORIZED = "UNAUTHORIZED"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class TicketStatus(str, Enum):
    CREATED = "created"
    PREVIEW = "preview"
    DENIED = "denied"


class ExtensionStatus(str, Enum):
    STAGED = "staged"
    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"


class McpProfile(str, Enum):
    STABLE_2025_11_25 = "2025-11-25"
    RC_2026_07_28 = "2026-07-28-rc"


class TicketInput(StrictModel):
    tenant_id: str
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=4000)
    severity: Literal["low", "medium", "high"]
    source_refs: list[str] = Field(min_length=1, max_length=8)


class TicketEffect(TicketInput):
    operation: Literal["create_policy_ticket"] = "create_policy_ticket"


class EffectPreview(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    canonical_effect: TicketEffect
    effect_hash: str
    impact: ImpactClass = ImpactClass.WRITE


class ApprovalClaims(StrictModel):
    actor_id: str
    tenant_id: str
    audience: Literal["policyops-ticket"] = "policyops-ticket"
    operation: Literal["create_policy_ticket"] = "create_policy_ticket"
    effect_hash: str
    scopes: list[str]
    expires_at: int
    nonce: str
    issuer: str = "dev-issuer"
    signature: str


class HookDecision(StrictModel):
    allow: bool
    reason_code: str
    duration_ms: int


class TicketResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    status: TicketStatus
    ticket_id: str | None = None
    effect_hash: str
    reason_code: DomainErrorCode | None = None
    evidence_status: Literal["recorded", "degraded", "not_applicable"] = "not_applicable"
    idempotency_key: str | None = None


class AuditEvent(StrictModel):
    event_id: str
    tenant_id: str
    actor_id: str
    extension_id: str
    operation: str
    effect_hash: str
    result_hash: str
    decision: str
    reason_code: str | None = None
    redacted: Literal[True] = True


class PackageFile(StrictModel):
    path: str
    sha256: str


class PluginManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    extension_id: str
    version: str
    host_contract: str
    mcp_profile: McpProfile = McpProfile.STABLE_2025_11_25
    entry_points: dict[str, str]
    permissions: list[str]
    files: list[PackageFile]
    predecessor: str | None = None
    signing_key_id: str = "fixture-key"
    signature: str


class PackageVerification(StrictModel):
    extension_id: str
    version: str
    accepted: bool
    reason_codes: list[str] = Field(default_factory=list)
    manifest_hash: str


class ExtensionVersion(StrictModel):
    extension_id: str
    version: str
    status: ExtensionStatus
    manifest_hash: str
    permissions: list[str]
    predecessor: str | None = None


class SkillActivationResult(StrictModel):
    task_id: str
    activated: bool
    sensitive_mutation_path: bool = False
    reason_code: str


class ActivationScorecard(StrictModel):
    corpus_hash: str
    precision: float
    recall: float
    false_sensitive_auto_activations: int
    gates_passed: bool


class CompatibilityReport(StrictModel):
    stable_profile: McpProfile
    rc_profile: McpProfile
    rc_opt_in: bool
    unsupported_features_fail_closed: bool
    explicit_state_stores: list[str]
    second_host_gaps: list[str]


class ExtensionScorecard(StrictModel):
    schema_version: Literal["1"] = "1"
    direct_contract_pass_rate: float
    mcp_contract_pass_rate: float
    activation_precision: float
    activation_recall: float
    unauthorized_tickets: int
    idempotency_violations: int
    secret_exposure: int
    tampered_or_revoked_loads: int
    hook_timeout_denials: int
    rollback_success: bool
    gates_passed: bool

    @model_validator(mode="after")
    def _hard_gates(self) -> ExtensionScorecard:
        if self.gates_passed and (
            self.activation_precision < 0.95
            or self.activation_recall < 0.90
            or self.unauthorized_tickets
            or self.idempotency_violations
            or self.secret_exposure
            or self.tampered_or_revoked_loads
        ):
            raise ValueError("extension hard gates cannot pass with security or quality gaps")
        return self


class CapabilityResource(StrictModel):
    resource_id: str
    name: str
    impact: ImpactClass
    input_schema: dict[str, Any]
    extension_id: str
    version: str
    available: bool
