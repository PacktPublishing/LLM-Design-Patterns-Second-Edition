"""Citation-first hybrid RAG schemas — Chapter 6."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class QueryClass(str, Enum):
    DIRECT = "direct"
    THEMATIC = "thematic"
    MULTI_HOP = "multi_hop"
    VISUAL = "visual"
    OUT_OF_SCOPE = "out_of_scope"


class Sufficiency(str, Enum):
    SUFFICIENT = "sufficient"
    CONFLICTING = "conflicting"
    INSUFFICIENT = "insufficient"


class RetrievalError(str, Enum):
    AUTH_SCOPE_REQUIRED = "AUTH_SCOPE_REQUIRED"
    SOURCE_VERSION_CONFLICT = "SOURCE_VERSION_CONFLICT"
    RETRIEVAL_TIMEOUT = "RETRIEVAL_TIMEOUT"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"


class Principal(StrictModel):
    tenant_id: str
    actor_id: str
    scopes: list[str]
    allowed_labels: list[str] = Field(default_factory=list)


class EvidenceBudget(StrictModel):
    max_candidates: int = Field(default=10, ge=1)
    max_passages: int = Field(default=4, ge=1)
    max_tokens: int = Field(default=500, ge=32)
    timeout_ms: int = Field(default=1200, ge=1)


class QueryRequest(StrictModel):
    schema_version: Literal["1"] = "1"
    query_id: str
    query: str
    principal: Principal
    budget: EvidenceBudget = Field(default_factory=EvidenceBudget)
    expected_span_ids: list[str] = Field(default_factory=list)


class SourceVersion(StrictModel):
    source_id: str
    version_id: str
    tenant_id: str
    acl_labels: list[str]
    title: str
    active: bool = True
    deleted: bool = False
    content_hash: str


class Span(StrictModel):
    span_id: str
    source_id: str
    version_id: str
    section_path: list[str]
    text: str
    token_count: int = Field(ge=1)
    tags: list[str] = Field(default_factory=list)
    page: int | None = None
    region: tuple[float, float, float, float] | None = None
    table_cell: str | None = None
    poisoned: bool = False


class CitationRef(StrictModel):
    source_id: str
    version_id: str
    span_id: str
    content_hash: str
    section_path: list[str]
    page: int | None = None
    region: tuple[float, float, float, float] | None = None
    table_cell: str | None = None


class Candidate(StrictModel):
    span: Span
    lexical_score: float = 0.0
    vector_score: float = 0.0
    fusion_score: float = 0.0
    rerank_score: float = 0.0
    excluded_reason: str | None = None


class EvidenceItem(StrictModel):
    citation: CitationRef
    text: str
    lexical_score: float | None = None
    vector_score: float | None = None
    rerank_score: float | None = None


class EvidencePack(StrictModel):
    schema_version: Literal["1"] = "1"
    query_id: str
    query_class: QueryClass
    items: list[EvidenceItem] = Field(default_factory=list)
    sufficiency: Sufficiency
    reason_codes: list[str] = Field(default_factory=list)
    packed_tokens: int = 0
    transformed_query: str | None = None

    @model_validator(mode="after")
    def _sufficient_requires_items(self) -> EvidencePack:
        if self.sufficiency == Sufficiency.SUFFICIENT and not self.items:
            raise ValueError("sufficient evidence packs require items")
        return self


class LifecycleReceipt(StrictModel):
    source_id: str
    previous_version_id: str | None = None
    active_version_id: str | None = None
    action: Literal["ingest", "replace", "delete"]
    idempotency_key: str
    manifest_generation: int
    freshness_lag_ms: int


class IngestionJob(StrictModel):
    job_id: str
    source_id: str
    action: Literal["replace", "delete"]
    idempotency_key: str
    state: Literal["active"] = "active"
    receipt: LifecycleReceipt


class IndexManifest(StrictModel):
    schema_version: Literal["1"] = "1"
    manifest_generation: int
    active_versions: dict[str, str | None]
    deleted_sources: list[str] = Field(default_factory=list)
    content_hash: str


class RetrievalScorecard(StrictModel):
    recall_at_10: float
    ndcg_at_10: float
    citation_resolution_rate: float
    abstention_accuracy: float
    authorization_violations: int
    p95_latency_ms: int
    gates_passed: bool
