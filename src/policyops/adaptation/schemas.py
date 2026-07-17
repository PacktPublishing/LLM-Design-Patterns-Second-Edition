"""Adaptation decision schemas — Chapter 3."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    derived_from: list[str] = Field(default_factory=list)
    deletion_scope: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    synthetic: bool = False
    generator_config: dict[str, Any] | None = None
    review_status: str = "accepted"


class DatasetManifest(StrictModel):
    schema_version: Literal["1"] = "1"
    dataset_id: str
    record_ids: list[str]
    content_hash: str | None = None


class SplitManifest(StrictModel):
    schema_version: Literal["1"] = "1"
    split_id: str
    train: list[str]
    validation: list[str]
    protected_test: list[str]
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
    metrics: dict[str, float] = Field(default_factory=dict)


class ModelArtifact(StrictModel):
    schema_version: Literal["1"] = "1"
    artifact_id: str
    path: str
    content_hash: str
    license: str
    base_model: str
    format: str = "fixture-adapter"


class ExperimentRun(StrictModel):
    schema_version: Literal["1"] = "1"
    experiment_id: str
    dataset_hash: str
    split_hash: str
    baseline_suite_hash: str
    candidate_ids: list[str]
    contamination_clean: bool
    gates: dict[str, bool] = Field(default_factory=dict)


class ReleaseDecision(StrictModel):
    schema_version: Literal["1"] = "1"
    decision: Literal["ship", "no_ship"]
    selected_candidate_id: str
    approver_role: str
    rollback_target: str
    gate_evidence: dict[str, Any]
    residual_risks: list[str] = Field(default_factory=list)
    review_by: str | None = None
