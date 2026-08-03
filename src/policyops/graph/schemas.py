"""Graph RAG schemas — Chapter 7."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GraphRoute(str, Enum):
    STANDARD_RAG = "standard_rag"
    LOCAL_GRAPH = "local_graph"
    MULTI_HOP_GRAPH = "multi_hop_graph"
    TEMPORAL_GRAPH = "temporal_graph"
    GLOBAL_GRAPH = "global_graph"
    HYBRID_GRAPH_VECTOR = "hybrid_graph_vector"


class PathStatus(str, Enum):
    SUPPORTED = "supported"
    CONFLICTING = "conflicting"
    PARTIAL = "partial"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    SUSPECTED = "suspected"
    REFUTED = "refuted"
    SUPERSEDED = "superseded"


class Entity(StrictModel):
    entity_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    tenant_id: str


class ClaimRef(StrictModel):
    claim_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str | None = None
    value: str | None = None
    source_id: str
    source_version: str
    span_id: str
    extraction_version: str = "extract-fixture-v1"
    confidence: float = Field(ge=0.0, le=1.0)
    tenant_id: str
    valid_from: date | None = None
    valid_to: date | None = None
    status: ClaimStatus = ClaimStatus.SUPPORTED


class GraphPath(StrictModel):
    schema_version: Literal["1"] = "1"
    snapshot_id: str
    route: GraphRoute
    entity_ids: list[str]
    relation_ids: list[str]
    claim_refs: list[ClaimRef]
    status: PathStatus
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _claim_paths_are_explained(self) -> GraphPath:
        if self.status == PathStatus.SUPPORTED and not self.claim_refs:
            raise ValueError("supported graph paths require source-linked claims")
        return self


class GraphQuery(StrictModel):
    schema_version: Literal["1"] = "1"
    query_id: str
    query: str
    tenant_id: str
    actor_id: str
    allowed_labels: list[str]
    as_of: date | None = None
    max_hops: int = Field(default=3, ge=1, le=4)
    max_fanout: int = Field(default=25, ge=1, le=100)
    timeout_ms: int = Field(default=1000, ge=1)


class SnapshotManifest(StrictModel):
    schema_version: Literal["1"] = "1"
    snapshot_id: str
    source_manifest_generation: int
    extraction_version: str
    tenant_ids: list[str]
    content_hash: str
    active: bool = False


class SnapshotActivation(StrictModel):
    activation_id: str
    previous_snapshot_id: str | None = None
    activated_snapshot_id: str
    reason: str
    rollback_of: str | None = None


class RepairReceipt(StrictModel):
    repair_id: str
    action: Literal["correct", "supersede", "delete"]
    source_id: str
    activation_id: str
    previous_snapshot_id: str
    candidate_snapshot_id: str
    activated_snapshot_id: str
    affected_claim_ids: list[str]
    unrelated_region_hash_before: str
    unrelated_region_hash_after: str
    atomic: bool = True


class GraphQueryResult(StrictModel):
    query_id: str
    route: GraphRoute
    path: GraphPath | None = None
    evidence_pack: dict
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)


class GraphScorecard(StrictModel):
    task_success_gain: float
    router_accuracy: float
    lineage_resolution_rate: float
    tenant_violations: int
    repair_correct: bool
    p95_latency_ms: int
    decision: Literal["adopt_graph_for_suitable_queries", "no_graph"]
    gates_passed: bool
