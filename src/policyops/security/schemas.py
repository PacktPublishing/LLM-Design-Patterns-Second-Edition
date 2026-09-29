"""Chapter 13 security and guardrail schemas."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TrustClass(str, Enum):
    TRUSTED_CONTROL = "trusted_control"
    UNTRUSTED_RETRIEVED = "untrusted_retrieved"
    UNTRUSTED_WEB = "untrusted_web"
    UNTRUSTED_TOOL = "untrusted_tool"
    UNTRUSTED_MEMORY = "untrusted_memory"


class DataClass(str, Enum):
    PUBLIC = "public"
    CASE_SUMMARY = "case_summary"
    PRIVATE = "private"
    SECRET = "secret"


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class ReasonCode(str, Enum):
    ALLOWED = "ALLOWED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    UNTRUSTED_AUTHORITY = "UNTRUSTED_AUTHORITY"
    CAPABILITY_SCOPE_DENIED = "CAPABILITY_SCOPE_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_EXACT_PREVIEW_MISMATCH = "APPROVAL_EXACT_PREVIEW_MISMATCH"
    APPROVAL_STALE_OR_REPLAYED = "APPROVAL_STALE_OR_REPLAYED"
    EGRESS_DENIED = "EGRESS_DENIED"
    SANDBOX_DENIED = "SANDBOX_DENIED"
    SECRET_DENIED = "SECRET_DENIED"
    INTEGRITY_DENIED = "INTEGRITY_DENIED"
    REVOKED = "REVOKED"
    MCP_AUTH_DENIED = "MCP_AUTH_DENIED"
    PROHIBITED_CONTENT = "PROHIBITED_CONTENT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class ThreatModelEntry(StrictModel):
    threat_id: str
    asset: str
    actor: str
    entry_point: str
    trust_boundary: str
    autonomy_tier: str
    abuse_case: str
    control_ids: list[str]
    test_ids: list[str]
    residual_risk_owner: str


class ContentEnvelope(StrictModel):
    content_id: str
    text: str
    provenance: str
    trust_class: TrustClass
    tenant_id: str
    authority_level: Literal["none", "evidence", "instruction"] = "evidence"
    data_class: DataClass
    integrity_hash: str

    @model_validator(mode="after")
    def _untrusted_content_has_no_instruction_authority(self) -> ContentEnvelope:
        if self.trust_class != TrustClass.TRUSTED_CONTROL and self.authority_level == "instruction":
            raise ValueError("untrusted content cannot carry instruction authority")
        return self


class Principal(StrictModel):
    actor_id: str
    tenant_id: str
    roles: list[str]
    scopes: list[str]
    authenticated: bool = True


class AuthorizationQuery(StrictModel):
    principal: Principal
    action: str
    resource: str
    destination: str | None
    data_classes: list[DataClass]
    content_trust: list[TrustClass]
    content_tenant_ids: list[str] = Field(default_factory=list)
    risk_tier: Literal["low", "medium", "high"]
    approval_effect_hash: str | None = None
    extension_id: str
    extension_digest: str
    extension_allowlisted: bool = True
    budget_effects_remaining: int = 1


class AuthorizationDecision(StrictModel):
    decision: Decision
    reason_code: ReasonCode
    obligations: dict[str, str | int | bool] = Field(default_factory=dict)


class CanonicalPreview(StrictModel):
    action: str
    tenant_id: str
    resource: str
    destination: str
    data_classes: list[DataClass]
    effect_hash: str


class ApprovalRecord(StrictModel):
    approval_id: str
    actor_id: str
    tenant_id: str
    effect_hash: str
    destination: str
    expires_at: int
    nonce: str
    signature: str


class CapabilityGrant(StrictModel):
    grant_id: str
    actor_id: str
    tenant_id: str
    action: str
    destination: str
    data_classes: list[DataClass]
    expires_at: int
    byte_budget: int
    revoked: bool = False


class SandboxProfile(StrictModel):
    profile_id: str
    non_root: bool
    read_only_root: bool
    writable_paths: list[str]
    process_limit: int
    memory_mb: int
    network_default_deny: bool
    host_credentials_inherited: bool = False
    tested_syscall_profile: bool


class OutboundRequest(StrictModel):
    scheme: str
    host: str
    port: int
    method: str
    data_class: DataClass
    resolved_address: str
    bytes_out: int
    follows_redirect: bool = False


class EgressDecision(StrictModel):
    allow: bool
    reason_code: ReasonCode
    normalized_destination: str


class SecretLease(StrictModel):
    lease_id: str
    fingerprint: str
    actor_id: str
    tenant_id: str
    capability: str
    expires_at: int
    model_visible: Literal[False] = False


class IntegrityRecord(StrictModel):
    artifact_id: str
    version: str
    digest: str
    allowlisted: bool
    revoked: bool = False
    signature_valid: bool = True


class McpAuthResult(StrictModel):
    profile: Literal["2025-11-25", "2026-07-28-rc"]
    protected_resource_discovery: bool
    pkce_used: bool
    resource_audience_valid: bool
    token_passthrough_rejected: bool
    issuer_validated: bool | None = None
    issuer_bound_client_credentials: bool | None = None
    accepted: bool
    reason_code: ReasonCode


class AttackCase(StrictModel):
    attack_id: str
    description: str
    content: ContentEnvelope | None = None
    expected_reason: ReasonCode
    high_impact: bool = True
    benign: bool = False


class AttackResult(StrictModel):
    attack_id: str
    decision: Decision
    reason_code: ReasonCode
    unauthorized_effects: int = 0
    secret_leaks: int = 0
    evidence_ref: str


class IncidentRecord(StrictModel):
    incident_id: str
    attack_id: str
    session_quarantined: bool
    capabilities_revoked: list[str]
    evidence_preserved: bool
    regression_case_id: str
    secret_values_redacted: bool


class SecurityReport(StrictModel):
    schema_version: Literal["1"] = "1"
    attack_results: list[AttackResult]
    unauthorized_high_impact_effects: int
    secret_leaks: int
    denied_filesystem_probes: int
    denied_network_probes: int
    revoked_invocations_allowed: int
    prohibited_cases_failed_safely: int
    benign_false_positive_rate: float
    threat_mapping_complete: bool
    stable_mcp_auth_passed: bool
    rc_mcp_auth_passed: bool
    gates_passed: bool

    @model_validator(mode="after")
    def _hard_gates(self) -> SecurityReport:
        if self.gates_passed and (
            self.unauthorized_high_impact_effects
            or self.secret_leaks
            or self.revoked_invocations_allowed
            or self.benign_false_positive_rate > 0.10
            or not self.threat_mapping_complete
            or not self.stable_mcp_auth_passed
            or not self.rc_mcp_auth_passed
        ):
            raise ValueError("security report cannot pass with hard-gate failures")
        return self
