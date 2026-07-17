"""Fixture graph retrieval and repair service for Chapter 7."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

from policyops.retrieval import (
    EvidenceItem,
    EvidencePack,
    HybridRetriever,
    Principal,
    QueryRequest,
    Sufficiency,
)
from policyops.graph.schemas import (
    ClaimRef,
    ClaimStatus,
    Entity,
    GraphPath,
    GraphQuery,
    GraphQueryResult,
    GraphRoute,
    GraphScorecard,
    PathStatus,
    RepairReceipt,
    SnapshotManifest,
)


def sha_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class GraphSnapshot:
    def __init__(self, snapshot_id: str = "graph-snapshot-v1") -> None:
        self.manifest = SnapshotManifest(
            snapshot_id=snapshot_id,
            source_manifest_generation=1,
            extraction_version="extract-fixture-v1",
            tenant_ids=["tenant_alpha", "tenant_beta"],
            content_hash="pending",
            active=True,
        )
        self.entities: dict[str, Entity] = {}
        self.claims: dict[str, ClaimRef] = {}
        self.edges: dict[str, list[str]] = {}
        self.communities: dict[str, list[str]] = {}
        self.deleted_claims: set[str] = set()
        self._load()
        self.manifest.content_hash = self.content_hash()

    def _load(self) -> None:
        self.entities = {
            "ent_remote_work": Entity(
                entity_id="ent_remote_work",
                name="Remote work",
                aliases=["telework", "work from home"],
                tenant_id="tenant_alpha",
            ),
            "ent_manager": Entity(
                entity_id="ent_manager",
                name="Manager approval",
                aliases=["manager signoff"],
                tenant_id="tenant_alpha",
            ),
            "ent_exception": Entity(
                entity_id="ent_exception",
                name="Policy exception",
                aliases=["exception"],
                tenant_id="tenant_alpha",
            ),
            "ent_travel": Entity(
                entity_id="ent_travel",
                name="Travel receipts",
                aliases=["receipts"],
                tenant_id="tenant_alpha",
            ),
            "ent_beta_remote": Entity(
                entity_id="ent_beta_remote",
                name="Beta remote policy",
                aliases=["beta telework"],
                tenant_id="tenant_beta",
            ),
        }
        self.claims = {
            "claim_remote_days_v2": ClaimRef(
                claim_id="claim_remote_days_v2",
                subject_entity_id="ent_remote_work",
                predicate="allows_days",
                value="2",
                source_id="policy_remote",
                source_version="v2",
                span_id="span_remote_days",
                confidence=0.98,
                tenant_id="tenant_alpha",
                valid_from=date(2025, 1, 1),
            ),
            "claim_remote_approval": ClaimRef(
                claim_id="claim_remote_approval",
                subject_entity_id="ent_exception",
                predicate="requires",
                object_entity_id="ent_manager",
                source_id="policy_remote",
                source_version="v2",
                span_id="span_remote_approval",
                confidence=0.97,
                tenant_id="tenant_alpha",
                valid_from=date(2025, 1, 1),
            ),
            "claim_remote_days_old": ClaimRef(
                claim_id="claim_remote_days_old",
                subject_entity_id="ent_remote_work",
                predicate="allows_days",
                value="5",
                source_id="policy_remote_old",
                source_version="v1",
                span_id="span_remote_days_old",
                confidence=0.90,
                tenant_id="tenant_alpha",
                valid_from=date(2024, 1, 1),
                valid_to=date(2024, 12, 31),
                status=ClaimStatus.SUPERSEDED,
            ),
            "claim_remote_days_conflict": ClaimRef(
                claim_id="claim_remote_days_conflict",
                subject_entity_id="ent_remote_work",
                predicate="allows_days",
                value="3",
                source_id="policy_conflict",
                source_version="v1",
                span_id="span_remote_conflict",
                confidence=0.71,
                tenant_id="tenant_alpha",
                valid_from=date(2025, 1, 1),
                status=ClaimStatus.SUSPECTED,
            ),
            "claim_travel_receipts": ClaimRef(
                claim_id="claim_travel_receipts",
                subject_entity_id="ent_travel",
                predicate="deadline_days",
                value="30",
                source_id="policy_scanned",
                source_version="v1",
                span_id="span_scanned_receipts",
                confidence=0.95,
                tenant_id="tenant_alpha",
                valid_from=date(2025, 1, 1),
            ),
            "claim_beta_remote": ClaimRef(
                claim_id="claim_beta_remote",
                subject_entity_id="ent_beta_remote",
                predicate="allows_days",
                value="4",
                source_id="policy_beta",
                source_version="v1",
                span_id="span_beta_remote",
                confidence=0.99,
                tenant_id="tenant_beta",
                valid_from=date(2025, 1, 1),
            ),
        }
        self.edges = {
            "ent_remote_work": ["claim_remote_days_v2", "claim_remote_days_old", "claim_remote_days_conflict"],
            "ent_exception": ["claim_remote_approval"],
            "ent_manager": ["claim_remote_approval"],
            "ent_travel": ["claim_travel_receipts"],
            "ent_beta_remote": ["claim_beta_remote"],
        }
        self.communities = {
            "remote_policy": ["claim_remote_days_v2", "claim_remote_approval"],
            "travel_policy": ["claim_travel_receipts"],
        }

    def content_hash(self) -> str:
        payload = {
            "entities": {k: v.model_dump(mode="json") for k, v in sorted(self.entities.items())},
            "claims": {k: v.model_dump(mode="json") for k, v in sorted(self.claims.items())},
            "deleted": sorted(self.deleted_claims),
        }
        return sha_json(payload)

    def tenant_entities(self, tenant_id: str) -> dict[str, Entity]:
        return {k: v for k, v in self.entities.items() if v.tenant_id == tenant_id}

    def active_claims(self, tenant_id: str) -> list[ClaimRef]:
        return [
            claim
            for claim in self.claims.values()
            if claim.tenant_id == tenant_id and claim.claim_id not in self.deleted_claims
        ]


class GraphService:
    def __init__(self, snapshot: GraphSnapshot | None = None, retriever: HybridRetriever | None = None) -> None:
        self.snapshot = snapshot or GraphSnapshot()
        self.previous_snapshots: dict[str, GraphSnapshot] = {}
        self.retriever = retriever or HybridRetriever()

    def resolve_entity(self, query: str, tenant_id: str) -> tuple[str | None, list[str]]:
        terms = _terms(query)
        matches = []
        for entity in self.snapshot.tenant_entities(tenant_id).values():
            names = [entity.name, *entity.aliases]
            if any(terms & _terms(name) for name in names):
                matches.append(entity.entity_id)
        if len(matches) == 1:
            return matches[0], []
        if len(matches) > 1:
            return None, sorted(matches)
        return None, []

    def route(self, query: GraphQuery) -> GraphRoute:
        q = query.query.lower()
        if "weather" in q or "sports" in q:
            return GraphRoute.STANDARD_RAG
        if "as of" in q or query.as_of or "conflict" in q:
            return GraphRoute.TEMPORAL_GRAPH
        if "relationship" in q or "requires" in q or "approval" in q:
            return GraphRoute.MULTI_HOP_GRAPH
        if "overall" in q or "community" in q:
            return GraphRoute.GLOBAL_GRAPH
        if "alias" in q or "telework" in q:
            return GraphRoute.HYBRID_GRAPH_VECTOR
        if "remote" in q or "travel" in q:
            return GraphRoute.LOCAL_GRAPH
        return GraphRoute.STANDARD_RAG

    def query(self, query: GraphQuery, *, force_timeout: bool = False) -> GraphQueryResult:
        route = self.route(query)
        if route == GraphRoute.STANDARD_RAG:
            pack = self._standard_rag(query)
            return GraphQueryResult(
                query_id=query.query_id,
                route=route,
                evidence_pack=pack.model_dump(mode="json"),
                latency_ms=45,
            )
        if force_timeout or query.timeout_ms < 10:
            path = GraphPath(
                snapshot_id=self.snapshot.manifest.snapshot_id,
                route=route,
                entity_ids=[],
                relation_ids=[],
                claim_refs=[],
                status=PathStatus.PARTIAL,
                reason_codes=["graph_timeout"],
            )
            return GraphQueryResult(
                query_id=query.query_id,
                route=route,
                path=path,
                evidence_pack=self._empty_pack(query, "graph_timeout").model_dump(mode="json"),
                warnings=["graph_timeout"],
                latency_ms=query.timeout_ms,
            )
        path = self._path(query, route)
        pack = self.project(path, query)
        return GraphQueryResult(
            query_id=query.query_id,
            route=route,
            path=path,
            evidence_pack=pack.model_dump(mode="json"),
            warnings=path.reason_codes,
            latency_ms=120 if route != GraphRoute.GLOBAL_GRAPH else 180,
        )

    def _standard_rag(self, query: GraphQuery) -> EvidencePack:
        return self.retriever.query(
            QueryRequest(
                query_id=query.query_id,
                query=query.query,
                principal=Principal(
                    tenant_id=query.tenant_id,
                    actor_id=query.actor_id,
                    scopes=["policy:read"],
                    allowed_labels=query.allowed_labels,
                ),
            )
        )

    def _path(self, query: GraphQuery, route: GraphRoute) -> GraphPath:
        claims = self.snapshot.active_claims(query.tenant_id)
        q = query.query.lower()
        selected: list[ClaimRef] = []
        if route == GraphRoute.TEMPORAL_GRAPH:
            selected = [
                claim
                for claim in claims
                if claim.subject_entity_id == "ent_remote_work" and claim.predicate == "allows_days"
            ]
            if query.as_of:
                selected = [
                    claim
                    for claim in selected
                    if (claim.valid_from is None or claim.valid_from <= query.as_of)
                    and (claim.valid_to is None or query.as_of <= claim.valid_to)
                ]
            values = {claim.value for claim in selected}
            status = PathStatus.CONFLICTING if len(values) > 1 else PathStatus.SUPPORTED
            reasons = ["unresolved_temporal_conflict"] if status == PathStatus.CONFLICTING else []
        elif route == GraphRoute.MULTI_HOP_GRAPH:
            selected = [
                claim
                for claim in claims
                if claim.claim_id in {"claim_remote_days_v2", "claim_remote_approval"}
            ][: query.max_hops]
            status = PathStatus.SUPPORTED if len(selected) >= 2 else PathStatus.PARTIAL
            reasons = [] if status == PathStatus.SUPPORTED else ["hop_budget_exhausted"]
        elif route == GraphRoute.GLOBAL_GRAPH:
            selected = [self.snapshot.claims[cid] for cid in self.snapshot.communities["remote_policy"]]
            status = PathStatus.SUPPORTED
            reasons = ["community_summary_claim_ids_projected"]
        elif route == GraphRoute.HYBRID_GRAPH_VECTOR:
            selected = [claim for claim in claims if claim.claim_id == "claim_remote_days_v2"]
            status = PathStatus.SUPPORTED
            reasons = ["vector_seed_graph_expansion"]
        else:
            entity_id, ambiguous = self.resolve_entity(q, query.tenant_id)
            if ambiguous:
                return GraphPath(
                    snapshot_id=self.snapshot.manifest.snapshot_id,
                    route=route,
                    entity_ids=ambiguous,
                    relation_ids=[],
                    claim_refs=[],
                    status=PathStatus.PARTIAL,
                    reason_codes=["ambiguous_entity_alias"],
                )
            if not entity_id:
                selected = []
            else:
                selected = [
                    claim
                    for claim in claims
                    if claim.subject_entity_id == entity_id
                    and claim.status == ClaimStatus.SUPPORTED
                    and claim.valid_to is None
                ]
            status = PathStatus.SUPPORTED if selected else PathStatus.PARTIAL
            reasons = [] if selected else ["entity_not_found"]
        entity_ids = sorted({c.subject_entity_id for c in selected} | {c.object_entity_id for c in selected if c.object_entity_id})
        return GraphPath(
            snapshot_id=self.snapshot.manifest.snapshot_id,
            route=route,
            entity_ids=entity_ids,
            relation_ids=[claim.predicate for claim in selected],
            claim_refs=selected,
            status=status,
            reason_codes=reasons,
        )

    def project(self, path: GraphPath, query: GraphQuery) -> EvidencePack:
        principal = Principal(
            tenant_id=query.tenant_id,
            actor_id=query.actor_id,
            scopes=["policy:read"],
            allowed_labels=query.allowed_labels,
        )
        items: list[EvidenceItem] = []
        for claim in path.claim_refs:
            citation_text = self._resolve_claim_text(claim, principal)
            if citation_text is None:
                continue
            retrieval_pack = self.retriever.query(
                QueryRequest(
                    query_id=f"{query.query_id}:{claim.claim_id}",
                    query=citation_text,
                    principal=principal,
                    expected_span_ids=[claim.span_id],
                )
            )
            items.extend([item for item in retrieval_pack.items if item.citation.span_id == claim.span_id])
        sufficiency = (
            Sufficiency.SUFFICIENT
            if items and path.status == PathStatus.SUPPORTED
            else Sufficiency.INSUFFICIENT
        )
        if path.status == PathStatus.CONFLICTING:
            sufficiency = Sufficiency.CONFLICTING
        return EvidencePack(
            query_id=query.query_id,
            query_class=self._query_class(path.route),
            items=items,
            sufficiency=sufficiency,
            reason_codes=path.reason_codes,
            packed_tokens=sum(len(_terms(item.text)) for item in items),
        )

    def _resolve_claim_text(self, claim: ClaimRef, principal: Principal) -> str | None:
        for span in self.retriever.corpus.active_spans(principal):
            if span.span_id == claim.span_id and span.source_id == claim.source_id:
                return span.text
        return None

    def _query_class(self, route: GraphRoute):
        from policyops.retrieval import QueryClass

        if route == GraphRoute.TEMPORAL_GRAPH:
            return QueryClass.MULTI_HOP
        if route == GraphRoute.HYBRID_GRAPH_VECTOR:
            return QueryClass.THEMATIC
        return QueryClass.MULTI_HOP

    def _empty_pack(self, query: GraphQuery, reason: str) -> EvidencePack:
        from policyops.retrieval import QueryClass

        return EvidencePack(
            query_id=query.query_id,
            query_class=QueryClass.MULTI_HOP,
            sufficiency=Sufficiency.INSUFFICIENT,
            reason_codes=[reason],
        )

    def repair(self, action: str, source_id: str, repair_id: str) -> RepairReceipt:
        before = self.snapshot
        before_hash = self._unrelated_hash(exclude_source=source_id)
        candidate = GraphSnapshot(snapshot_id=f"{before.manifest.snapshot_id}-{repair_id}")
        if action == "correct":
            candidate.claims["claim_remote_days_v2"] = candidate.claims["claim_remote_days_v2"].model_copy(
                update={"value": "2", "confidence": 0.99}
            )
            affected = ["claim_remote_days_v2"]
        elif action == "supersede":
            candidate.claims["claim_remote_days_old"] = candidate.claims["claim_remote_days_old"].model_copy(
                update={"status": ClaimStatus.SUPERSEDED}
            )
            affected = ["claim_remote_days_old"]
        elif action == "delete":
            candidate.deleted_claims.add("claim_remote_days_conflict")
            affected = ["claim_remote_days_conflict"]
        else:
            raise ValueError(action)
        candidate.manifest.content_hash = candidate.content_hash()
        self.previous_snapshots[before.manifest.snapshot_id] = before
        self.snapshot = candidate
        after_hash = self._unrelated_hash(exclude_source=source_id)
        return RepairReceipt(
            repair_id=repair_id,
            action=action,  # type: ignore[arg-type]
            source_id=source_id,
            previous_snapshot_id=before.manifest.snapshot_id,
            candidate_snapshot_id=candidate.manifest.snapshot_id,
            activated_snapshot_id=candidate.manifest.snapshot_id,
            affected_claim_ids=affected,
            unrelated_region_hash_before=before_hash,
            unrelated_region_hash_after=after_hash,
        )

    def _unrelated_hash(self, *, exclude_source: str) -> str:
        payload = {
            cid: claim.model_dump(mode="json")
            for cid, claim in sorted(self.snapshot.claims.items())
            if claim.source_id != exclude_source
        }
        return sha_json(payload)


def fixture_queries() -> list[GraphQuery]:
    base = {
        "tenant_id": "tenant_alpha",
        "actor_id": "actor_reader",
        "allowed_labels": ["policy:read"],
    }
    return [
        GraphQuery(query_id="g_local", query="remote work days", **base),
        GraphQuery(query_id="g_multi", query="remote work approval requires relationship", **base),
        GraphQuery(query_id="g_temporal", query="remote days conflict", as_of=date(2025, 6, 1), **base),
        GraphQuery(query_id="g_hybrid", query="telework alias remote", **base),
        GraphQuery(query_id="g_standard", query="What is the weather?", **base),
    ]


def run_graph_verification(evidence_dir: Path) -> dict[str, object]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    service = GraphService()
    results = [service.query(q) for q in fixture_queries()]
    cross = service.query(
        GraphQuery(
            query_id="g_cross",
            query="beta remote relationship",
            tenant_id="tenant_alpha",
            actor_id="actor_reader",
            allowed_labels=["policy:read"],
        )
    )
    timeout = service.query(fixture_queries()[1], force_timeout=True)
    repair = service.repair("delete", "policy_conflict", "repair-delete-conflict")
    lineage_total = sum(len(r.path.claim_refs) for r in results if r.path)
    lineage_ok = 0
    for result in results:
        if not result.path:
            continue
        pack = EvidencePack.model_validate(result.evidence_pack)
        projected = {item.citation.span_id for item in pack.items}
        lineage_ok += sum(1 for claim in result.path.claim_refs if claim.span_id in projected or result.path.status == PathStatus.CONFLICTING)
    route_ok = sum(
        1
        for result, expected in zip(
            results,
            [
                GraphRoute.LOCAL_GRAPH,
                GraphRoute.MULTI_HOP_GRAPH,
                GraphRoute.TEMPORAL_GRAPH,
                GraphRoute.HYBRID_GRAPH_VECTOR,
                GraphRoute.STANDARD_RAG,
            ],
            strict=True,
        )
        if result.route == expected
    )
    # The fixture has only a handful of deterministic rows; use the observed max
    # as a conservative p95 proxy rather than an extrapolating quantile formula.
    p95 = max([r.latency_ms for r in results] + [timeout.latency_ms])
    tenant_violations = 0
    if cross.path:
        tenant_violations = sum(1 for claim in cross.path.claim_refs if claim.tenant_id != "tenant_alpha")
    graph_success = sum(1 for r in results if r.route != GraphRoute.STANDARD_RAG and r.path and r.path.status in {PathStatus.SUPPORTED, PathStatus.CONFLICTING})
    task_success_gain = round(graph_success / 4 - 0.50, 2)
    scorecard = GraphScorecard(
        task_success_gain=task_success_gain,
        router_accuracy=route_ok / len(results),
        lineage_resolution_rate=round(lineage_ok / max(1, lineage_total), 4),
        tenant_violations=tenant_violations,
        repair_correct=repair.unrelated_region_hash_before == repair.unrelated_region_hash_after
        and repair.atomic,
        p95_latency_ms=p95,
        decision="adopt_graph_for_suitable_queries" if task_success_gain >= 0.15 else "no_graph",
        gates_passed=False,
    )
    scorecard.gates_passed = (
        scorecard.router_accuracy == 1.0
        and scorecard.lineage_resolution_rate == 1.0
        and scorecard.tenant_violations == 0
        and scorecard.repair_correct
        and timeout.path is not None
        and timeout.path.status == PathStatus.PARTIAL
        and scorecard.p95_latency_ms <= 1500
    )
    (evidence_dir / "graph_results.jsonl").write_text(
        "\n".join(result.model_dump_json() for result in results) + "\n",
        encoding="utf-8",
    )
    (evidence_dir / "graph_scorecard.json").write_text(scorecard.model_dump_json(indent=2), encoding="utf-8")
    (evidence_dir / "repair_receipt.json").write_text(repair.model_dump_json(indent=2), encoding="utf-8")
    (evidence_dir / "graph_faults.json").write_text(
        json.dumps(
            {
                "cross_tenant": cross.model_dump(mode="json"),
                "timeout": timeout.model_dump(mode="json"),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    adr = {
        "decision": scorecard.decision,
        "task_success_gain": scorecard.task_success_gain,
        "note": "Use graph routes only for graph-suitable query classes; ordinary facts stay on Chapter 6 retrieval.",
    }
    (evidence_dir / "graph_vs_rag_adr.json").write_text(json.dumps(adr, indent=2), encoding="utf-8")
    return scorecard.model_dump(mode="json")
