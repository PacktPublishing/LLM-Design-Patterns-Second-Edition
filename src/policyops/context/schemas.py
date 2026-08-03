"""Context planner schemas — Chapter 5."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceKind(str, Enum):
    POLICY = "policy"
    PROJECT = "project"
    TASK = "task"
    EVIDENCE = "evidence"
    MEMORY = "memory"
    CAPABILITY = "capability"
    OBSERVATION = "observation"
    USER = "user"


class AuthorityLevel(str, Enum):
    SYSTEM_POLICY = "system_policy"
    PROJECT_INSTRUCTION = "project_instruction"
    TASK_INSTRUCTION = "task_instruction"
    VERIFIED_EVIDENCE = "verified_evidence"
    STATE = "state"
    USER_INPUT = "user_input"
    UNTRUSTED_CONTENT = "untrusted_content"


AUTHORITY_RANK: dict[AuthorityLevel, int] = {
    AuthorityLevel.SYSTEM_POLICY: 0,
    AuthorityLevel.PROJECT_INSTRUCTION: 1,
    AuthorityLevel.TASK_INSTRUCTION: 2,
    AuthorityLevel.VERIFIED_EVIDENCE: 3,
    AuthorityLevel.STATE: 4,
    AuthorityLevel.USER_INPUT: 5,
    AuthorityLevel.UNTRUSTED_CONTENT: 6,
}


class TrustLabel(str, Enum):
    TRUSTED_INSTRUCTION = "trusted_instruction"
    VERIFIED_DATA = "verified_data"
    OBSERVED_DATA = "observed_data"
    UNTRUSTED_CONTENT = "untrusted_content"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"


SENSITIVITY_RANK = {
    Sensitivity.PUBLIC: 0,
    Sensitivity.INTERNAL: 1,
    Sensitivity.CONFIDENTIAL: 2,
}


class Placement(str, Enum):
    STABLE_PREFIX = "stable_prefix"
    VARIABLE_CONTEXT = "variable_context"
    USER_SUFFIX = "user_suffix"


class DecisionReason(str, Enum):
    INCLUDED_REQUIRED = "included_required"
    INCLUDED_RELEVANT = "included_relevant"
    EXCLUDED_IRRELEVANT = "excluded_irrelevant"
    EXCLUDED_BUDGET = "excluded_budget"
    REJECTED_SECRET = "rejected_secret"
    REJECTED_CONFLICT = "rejected_conflict"
    REJECTED_AUTHORITY_ELEVATION = "rejected_authority_elevation"
    REJECTED_STALE = "rejected_stale"
    REJECTED_SENSITIVITY = "rejected_sensitivity"
    COMPACTED = "compacted"
    MISSING_REQUIRED = "missing_required"
    BUDGET_IMPOSSIBLE = "budget_impossible"


class TerminalReason(str, Enum):
    READY = "ready"
    REQUIRED_FACT_MISSING = "required_fact_missing"
    CONTEXT_BUDGET_IMPOSSIBLE = "context_budget_impossible"
    AUTHORITY_CONFLICT = "authority_conflict"
    SENSITIVITY_VIOLATION = "sensitivity_violation"
    SOURCE_INVALID = "source_invalid"


class Provenance(StrictModel):
    source_id: str
    content_hash: str
    version: str = "fixture-v1"


class SourceSummary(StrictModel):
    schema_version: Literal["1"] = "1"
    item_id: str
    source_kind: SourceKind
    authority: AuthorityLevel
    trust: TrustLabel
    provenance: Provenance
    tenant_id: str
    sensitivity: Sensitivity
    required: bool = False
    stable: bool = False
    estimated_tokens: int = Field(ge=1)
    relevance_tags: list[str] = Field(default_factory=list)
    fresh: bool = True


class ContextItem(SourceSummary):
    text: str = Field(min_length=1)
    coordinates: dict[str, int] | None = None


class ContextRequest(StrictModel):
    schema_version: Literal["1"] = "1"
    request_id: str
    tenant_id: str
    actor_id: str
    task: str
    question: str
    required_fact_ids: list[str] = Field(default_factory=list)
    max_input_tokens: int = Field(default=1200, ge=128)
    output_reserve_tokens: int = Field(default=256, ge=1)
    allowed_sensitivity: Sensitivity = Sensitivity.INTERNAL
    policy_version: str = "context-policy-v1"


class ContextPolicy(StrictModel):
    schema_version: Literal["1"] = "1"
    authority_order: list[AuthorityLevel]
    stable_prefix_authorities: list[AuthorityLevel]
    max_summary_calls: int = Field(default=16, ge=1)
    max_materializations: int = Field(default=16, ge=1)
    render_overhead_tokens: int = Field(default=96, ge=0)
    optional_source_token_budgets: dict[SourceKind, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_authority_order(self) -> "ContextPolicy":
        expected = sorted(AUTHORITY_RANK, key=AUTHORITY_RANK.get)
        if self.authority_order != expected:
            raise ValueError("authority_order must match the supported authority ranking")
        invalid = [level for level in self.stable_prefix_authorities if level not in self.authority_order]
        if invalid:
            raise ValueError("stable_prefix_authorities must be drawn from authority_order")
        return self


class ManifestDecision(StrictModel):
    item_id: str
    source_id: str
    source_kind: SourceKind
    authority: AuthorityLevel
    trust: TrustLabel
    sensitivity: Sensitivity
    decision: DecisionReason
    content_hash: str
    estimated_tokens: int
    actual_tokens: int | None = None


class ContextPlan(StrictModel):
    schema_version: Literal["1"] = "1"
    request_id: str
    selected_ids: list[str]
    rejected: list[ManifestDecision] = Field(default_factory=list)
    terminal_reason: TerminalReason = TerminalReason.READY


class CompactionResult(StrictModel):
    schema_version: Literal["1"] = "1"
    item_id: str
    retained_decisions: list[str]
    retained_artifacts: list[str]
    original_tokens: int
    compacted_tokens: int
    content_hash: str


class RenderedContext(StrictModel):
    schema_version: Literal["1"] = "1"
    request_id: str
    model_request_text: str
    stable_prefix: str
    variable_context: str
    answer_schema: dict[str, Any]
    stable_prefix_hash: str
    full_context_hash: str
    input_tokens: int


class ContextManifest(StrictModel):
    schema_version: Literal["1"] = "1"
    request_id: str
    terminal_reason: TerminalReason
    policy_hash: str
    tokenizer_hash: str
    included: list[ManifestDecision] = Field(default_factory=list)
    excluded: list[ManifestDecision] = Field(default_factory=list)
    rejected: list[ManifestDecision] = Field(default_factory=list)
    compacted: list[CompactionResult] = Field(default_factory=list)
    stable_prefix_hash: str | None = None
    full_context_hash: str | None = None
    input_tokens: int = 0
    monolith_tokens: int = 0
    planned_token_reduction: int = 0
    summary_calls: int = 0
    materializations: int = 0

    @model_validator(mode="after")
    def _required_fields_for_ready(self) -> ContextManifest:
        if self.terminal_reason == TerminalReason.READY and not self.full_context_hash:
            raise ValueError("ready manifests require rendered context fingerprints")
        return self
