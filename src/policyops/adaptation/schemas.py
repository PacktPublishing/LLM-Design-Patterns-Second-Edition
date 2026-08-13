"""Adaptation decision schemas — Chapter 3."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"


class DataRecord(StrictModel):
    schema_version: Literal["1"] = "1"
    record_id: str
    text: str
    label: str
    content_hash: str
    source_ref: str
    rights_basis: str
    consent_ref: str | None = None
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    owner: str
    entity_key: str
    subgroup_key: str = "general"
    provenance_chain: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    deletion_scope: list[str] = Field(default_factory=list)
    retention_days: int | None = Field(default=None, ge=1)
    deletion_ticket: str | None = None
    created_at: datetime | None = None
    synthetic: bool = False
    generator_config: dict[str, Any] | None = None
    generator_filters: list[str] = Field(default_factory=list)
    review_status: str = "accepted"
    reviewer: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_lineage(self) -> "DataRecord":
        if not self.provenance_chain:
            object.__setattr__(self, "provenance_chain", [self.source_ref])
        if self.synthetic and (not self.generator_config or not self.derived_from):
            raise ValueError("synthetic records require generator_config and derived_from lineage")
        if self.synthetic and self.review_status != "accepted":
            raise ValueError("synthetic records must be human-reviewed before acceptance")
        return self


class DatasetManifest(StrictModel):
    schema_version: Literal["1"] = "1"
    dataset_id: str
    record_ids: list[str]
    record_count: int = 0
    source_breakdown: dict[str, int] = Field(default_factory=dict)
    rights_bases: list[str] = Field(default_factory=list)
    synthetic_record_ids: list[str] = Field(default_factory=list)
    lineage_hash: str | None = None
    code_revision: str = "fixture-repo"
    lockfile_hash: str = "sha256:fixture-lock"
    content_hash: str | None = None


class SplitManifest(StrictModel):
    schema_version: Literal["1"] = "1"
    split_id: str
    strategy: str = "entity-group-hash-v1"
    seed: int = 0
    train: list[str]
    validation: list[str]
    protected_test: list[str]
    protected_entity_keys: list[str] = Field(default_factory=list)
    subgroup_membership: dict[str, list[str]] = Field(default_factory=dict)
    content_hash: str | None = None


class CandidateKind(str, Enum):
    BASELINE = "baseline"
    PROMPT = "prompt"
    RETRIEVAL_REPLAY = "retrieval_replay"
    ADAPTER = "adapter"


class AdaptationCandidate(StrictModel):
    schema_version: Literal["1"] = "1"
    candidate_id: str
    kind: CandidateKind
    model_ref: str
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    configuration_hash: str
    rollback_target: str
    suite_hash: str
    grader_hash: str = "sha256:grader-fixture"
    environment_hash: str = "sha256:fixture-env"
    base_candidate_id: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


class ModelArtifact(StrictModel):
    schema_version: Literal["1"] = "1"
    artifact_id: str
    path: str
    content_hash: str
    license: str
    base_model: str
    format: str = "fixture-adapter"
    size_bytes: int = Field(default=0, ge=0)
    approved_source: str = "fixture"
    declared_architecture: str = "adapter"
    load_policy: str = "json-safe-load"


class ExperimentRun(StrictModel):
    schema_version: Literal["1"] = "1"
    experiment_id: str
    dataset_hash: str
    split_hash: str
    baseline_suite_hash: str
    candidate_ids: list[str]
    contamination_clean: bool
    suite_hash: str
    grader_hash: str = "sha256:grader-fixture"
    environment_hash: str = "sha256:fixture-env"
    policy_hash: str = "sha256:adaptation-policy-v1"
    results: dict[str, Any] = Field(default_factory=dict)
    gates: dict[str, bool] = Field(default_factory=dict)


class ReleaseDecision(StrictModel):
    schema_version: Literal["1"] = "1"
    decision: Literal["ship", "no_ship"]
    selected_candidate_id: str
    selected_candidate_kind: str = "baseline"
    approver_role: str
    rollback_target: str
    gate_evidence: dict[str, Any]
    decision_reason: str = "candidate_selection_complete"
    residual_risks: list[str] = Field(default_factory=list)
    review_by: str | None = None
    expires_at: datetime | None = None
