"""Fixture graph retrieval and repair service for Chapter 7."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
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
    SnapshotActivation,
    SnapshotManifest,
)


def sha_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class GraphSnapshot:
    def __init__(self, snapshot_id: str = "graph-snapshot-v1", db_path: str | Path | None = None) -> None:
        self.db_path = ":memory:" if db_path is None else str(Path(db_path))
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        if self._is_empty():
            self._load_defaults(snapshot_id=snapshot_id)
            self._persist_version(self._state_payload())
            self._record_activation(
                SnapshotActivation(
                    activation_id=f"activate-{snapshot_id}",
                    previous_snapshot_id=None,
                    activated_snapshot_id=snapshot_id,
                    reason="initial_load",
                )
            )
        else:
            self.manifest = self.manifest.model_copy(update={"content_hash": self.content_hash(), "active": True})

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS snapshot_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    entity_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    claim_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS edges (
                    entity_id TEXT PRIMARY KEY,
                    edge_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS communities (
                    community_id TEXT PRIMARY KEY,
                    community_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS deleted_claims (
                    claim_id TEXT PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS snapshot_versions (
                    snapshot_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshot_activations (
                    activation_id TEXT PRIMARY KEY,
                    activation_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS repair_receipts (
                    repair_id TEXT PRIMARY KEY,
                    receipt_json TEXT NOT NULL
                );
                """
            )

    def _is_empty(self) -> bool:
        row = self._conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()
        return int(row["count"]) == 0

    def _dump(self, payload: object) -> str:
        return json.dumps(payload, sort_keys=True, default=str)

    def _load_json(self, payload: str) -> object:
        return json.loads(payload)

    @property
    def manifest(self) -> SnapshotManifest:
        row = self._conn.execute(
            "SELECT value FROM snapshot_meta WHERE key = 'manifest'"
        ).fetchone()
        if row is None:
            raise RuntimeError("graph snapshot manifest not initialized")
        return SnapshotManifest.model_validate(self._load_json(row["value"]))

    @manifest.setter
    def manifest(self, value: SnapshotManifest) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO snapshot_meta(key, value) VALUES ('manifest', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (self._dump(value.model_dump(mode="json")),),
            )

    @property
    def entities(self) -> dict[str, Entity]:
        rows = self._conn.execute("SELECT entity_id, entity_json FROM entities ORDER BY entity_id").fetchall()
        return {
            row["entity_id"]: Entity.model_validate(self._load_json(row["entity_json"]))
            for row in rows
        }

    @entities.setter
    def entities(self, payload: dict[str, Entity]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM entities")
            self._conn.executemany(
                "INSERT INTO entities(entity_id, tenant_id, entity_json) VALUES (?, ?, ?)",
                [
                    (entity_id, entity.tenant_id, self._dump(entity.model_dump(mode="json")))
                    for entity_id, entity in payload.items()
                ],
            )

    @property
    def claims(self) -> dict[str, ClaimRef]:
        rows = self._conn.execute("SELECT claim_id, claim_json FROM claims ORDER BY claim_id").fetchall()
        return {
            row["claim_id"]: ClaimRef.model_validate(self._load_json(row["claim_json"]))
            for row in rows
        }

    @claims.setter
    def claims(self, payload: dict[str, ClaimRef]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM claims")
            self._conn.executemany(
                "INSERT INTO claims(claim_id, tenant_id, source_id, claim_json) VALUES (?, ?, ?, ?)",
                [
                    (claim_id, claim.tenant_id, claim.source_id, self._dump(claim.model_dump(mode="json")))
                    for claim_id, claim in payload.items()
                ],
            )

    @property
    def edges(self) -> dict[str, list[str]]:
        rows = self._conn.execute("SELECT entity_id, edge_json FROM edges ORDER BY entity_id").fetchall()
        return {row["entity_id"]: list(self._load_json(row["edge_json"])) for row in rows}

    @edges.setter
    def edges(self, payload: dict[str, list[str]]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM edges")
            self._conn.executemany(
                "INSERT INTO edges(entity_id, edge_json) VALUES (?, ?)",
                [(entity_id, self._dump(claim_ids)) for entity_id, claim_ids in payload.items()],
            )

    @property
    def communities(self) -> dict[str, list[str]]:
        rows = self._conn.execute(
            "SELECT community_id, community_json FROM communities ORDER BY community_id"
        ).fetchall()
        return {row["community_id"]: list(self._load_json(row["community_json"])) for row in rows}

    @communities.setter
    def communities(self, payload: dict[str, list[str]]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM communities")
            self._conn.executemany(
                "INSERT INTO communities(community_id, community_json) VALUES (?, ?)",
                [(community_id, self._dump(claim_ids)) for community_id, claim_ids in payload.items()],
            )

    @property
    def deleted_claims(self) -> set[str]:
        rows = self._conn.execute("SELECT claim_id FROM deleted_claims ORDER BY claim_id").fetchall()
        return {row["claim_id"] for row in rows}

    @deleted_claims.setter
    def deleted_claims(self, payload: set[str]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM deleted_claims")
            self._conn.executemany(
                "INSERT INTO deleted_claims(claim_id) VALUES (?)",
                [(claim_id,) for claim_id in sorted(payload)],
            )

    def _load_defaults(self, *, snapshot_id: str) -> None:
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
        self.deleted_claims = set()
        self.manifest = SnapshotManifest(
            snapshot_id=snapshot_id,
            source_manifest_generation=1,
            extraction_version="extract-fixture-v1",
            tenant_ids=["tenant_alpha", "tenant_beta"],
            content_hash="pending",
            active=True,
        )
        self.manifest = self.manifest.model_copy(update={"content_hash": self.content_hash(), "active": True})

    def _state_payload(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.model_dump(mode="json"),
            "entities": {k: v.model_dump(mode="json") for k, v in sorted(self.entities.items())},
            "claims": {k: v.model_dump(mode="json") for k, v in sorted(self.claims.items())},
            "edges": {k: list(v) for k, v in sorted(self.edges.items())},
            "communities": {k: list(v) for k, v in sorted(self.communities.items())},
            "deleted_claims": sorted(self.deleted_claims),
        }

    def _expected_content_hash(self, payload: dict[str, object]) -> str:
        return sha_json(
            {
                "entities": payload["entities"],
                "claims": payload["claims"],
                "deleted": payload["deleted_claims"],
            }
        )

    def _load_state_payload(self, payload: dict[str, object]) -> None:
        manifest = SnapshotManifest.model_validate(payload["manifest"])
        entities = {
            entity_id: Entity.model_validate(entity_payload)
            for entity_id, entity_payload in dict(payload["entities"]).items()
        }
        claims = {
            claim_id: ClaimRef.model_validate(claim_payload)
            for claim_id, claim_payload in dict(payload["claims"]).items()
        }
        edges = {entity_id: list(claim_ids) for entity_id, claim_ids in dict(payload["edges"]).items()}
        communities = {
            community_id: list(claim_ids)
            for community_id, claim_ids in dict(payload["communities"]).items()
        }
        deleted_claims = set(payload["deleted_claims"])
        expected_hash = self._expected_content_hash(payload)
        if manifest.content_hash != expected_hash:
            raise ValueError("tampered snapshot content hash")
        with self._conn:
            self._conn.execute("DELETE FROM entities")
            self._conn.executemany(
                "INSERT INTO entities(entity_id, tenant_id, entity_json) VALUES (?, ?, ?)",
                [
                    (entity_id, entity.tenant_id, self._dump(entity.model_dump(mode="json")))
                    for entity_id, entity in entities.items()
                ],
            )
            self._conn.execute("DELETE FROM claims")
            self._conn.executemany(
                "INSERT INTO claims(claim_id, tenant_id, source_id, claim_json) VALUES (?, ?, ?, ?)",
                [
                    (claim_id, claim.tenant_id, claim.source_id, self._dump(claim.model_dump(mode="json")))
                    for claim_id, claim in claims.items()
                ],
            )
            self._conn.execute("DELETE FROM edges")
            self._conn.executemany(
                "INSERT INTO edges(entity_id, edge_json) VALUES (?, ?)",
                [(entity_id, self._dump(claim_ids)) for entity_id, claim_ids in edges.items()],
            )
            self._conn.execute("DELETE FROM communities")
            self._conn.executemany(
                "INSERT INTO communities(community_id, community_json) VALUES (?, ?)",
                [(community_id, self._dump(claim_ids)) for community_id, claim_ids in communities.items()],
            )
            self._conn.execute("DELETE FROM deleted_claims")
            self._conn.executemany(
                "INSERT INTO deleted_claims(claim_id) VALUES (?)",
                [(claim_id,) for claim_id in sorted(deleted_claims)],
            )
            self._conn.execute(
                """
                INSERT INTO snapshot_meta(key, value) VALUES ('manifest', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (self._dump(manifest.model_dump(mode="json")),),
            )

    def _persist_version(self, payload: dict[str, object]) -> None:
        manifest = SnapshotManifest.model_validate(payload["manifest"])
        if manifest.content_hash != self._expected_content_hash(payload):
            raise ValueError("snapshot manifest hash mismatch")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO snapshot_versions(snapshot_id, payload_json) VALUES (?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (manifest.snapshot_id, self._dump(payload)),
            )

    def list_snapshot_ids(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT snapshot_id FROM snapshot_versions ORDER BY snapshot_id"
        ).fetchall()
        return [row["snapshot_id"] for row in rows]

    def clone(self, snapshot_id: str) -> GraphSnapshot:
        payload = self._state_payload()
        clone = GraphSnapshot(snapshot_id=snapshot_id)
        manifest = SnapshotManifest.model_validate(payload["manifest"]).model_copy(
            update={"snapshot_id": snapshot_id, "active": False}
        )
        candidate_payload = {**payload, "manifest": manifest.model_dump(mode="json")}
        candidate_payload["manifest"]["content_hash"] = self._expected_content_hash(candidate_payload)
        clone._load_state_payload(candidate_payload)
        clone.manifest = SnapshotManifest.model_validate(candidate_payload["manifest"])
        return clone

    def store_snapshot(self, snapshot: GraphSnapshot) -> None:
        self._persist_version(snapshot._state_payload())

    def load_snapshot(self, snapshot_id: str) -> None:
        row = self._conn.execute(
            "SELECT payload_json FROM snapshot_versions WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        payload = self._load_json(row["payload_json"])
        payload["manifest"]["active"] = True
        self._load_state_payload(payload)
        self.manifest = self.manifest.model_copy(update={"active": True})

    def _record_activation(self, activation: SnapshotActivation) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO snapshot_activations(activation_id, activation_json) VALUES (?, ?)",
                (activation.activation_id, self._dump(activation.model_dump(mode="json"))),
            )

    def activation_history(self) -> list[SnapshotActivation]:
        rows = self._conn.execute(
            "SELECT activation_json FROM snapshot_activations ORDER BY rowid"
        ).fetchall()
        return [SnapshotActivation.model_validate(self._load_json(row["activation_json"])) for row in rows]

    def activate_snapshot(
        self,
        snapshot_id: str,
        *,
        reason: str,
        activation_id: str,
        rollback_of: str | None = None,
    ) -> SnapshotActivation:
        previous_snapshot_id = self.manifest.snapshot_id
        self.load_snapshot(snapshot_id)
        activation = SnapshotActivation(
            activation_id=activation_id,
            previous_snapshot_id=previous_snapshot_id,
            activated_snapshot_id=snapshot_id,
            reason=reason,
            rollback_of=rollback_of,
        )
        self._record_activation(activation)
        return activation

    def repair_receipt(self, repair_id: str) -> RepairReceipt | None:
        row = self._conn.execute(
            "SELECT receipt_json FROM repair_receipts WHERE repair_id = ?",
            (repair_id,),
        ).fetchone()
        if row is None:
            return None
        return RepairReceipt.model_validate(self._load_json(row["receipt_json"]))

    def record_repair_receipt(self, receipt: RepairReceipt) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO repair_receipts(repair_id, receipt_json) VALUES (?, ?)",
                (receipt.repair_id, self._dump(receipt.model_dump(mode="json"))),
            )

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

    def update_claim(self, claim: ClaimRef) -> None:
        claims = self.claims
        claims[claim.claim_id] = claim
        self.claims = claims

    def mark_deleted(self, claim_id: str) -> None:
        deleted = self.deleted_claims
        deleted.add(claim_id)
        self.deleted_claims = deleted


class GraphService:
    def __init__(self, snapshot: GraphSnapshot | None = None, retriever: HybridRetriever | None = None) -> None:
        self.snapshot = snapshot or GraphSnapshot()
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
        existing = self.snapshot.repair_receipt(repair_id)
        if existing is not None:
            return existing
        before = self.snapshot
        previous_snapshot_id = before.manifest.snapshot_id
        before_hash = self._unrelated_hash(exclude_source=source_id)
        candidate = before.clone(snapshot_id=f"{previous_snapshot_id}-{repair_id}")
        if action == "correct":
            candidate.update_claim(
                candidate.claims["claim_remote_days_v2"].model_copy(update={"value": "2", "confidence": 0.99})
            )
            affected = ["claim_remote_days_v2"]
        elif action == "supersede":
            candidate.update_claim(
                candidate.claims["claim_remote_days_old"].model_copy(update={"status": ClaimStatus.SUPERSEDED})
            )
            affected = ["claim_remote_days_old"]
        elif action == "delete":
            candidate.mark_deleted("claim_remote_days_conflict")
            affected = ["claim_remote_days_conflict"]
        else:
            raise ValueError(action)
        candidate.manifest = candidate.manifest.model_copy(update={"content_hash": candidate.content_hash(), "active": False})
        self.snapshot.store_snapshot(candidate)
        activation = self.snapshot.activate_snapshot(
            candidate.manifest.snapshot_id,
            reason=f"repair:{action}",
            activation_id=f"activate-{repair_id}",
        )
        after_hash = self._unrelated_hash(exclude_source=source_id)
        receipt = RepairReceipt(
            repair_id=repair_id,
            action=action,  # type: ignore[arg-type]
            source_id=source_id,
            activation_id=activation.activation_id,
            previous_snapshot_id=previous_snapshot_id,
            candidate_snapshot_id=candidate.manifest.snapshot_id,
            activated_snapshot_id=activation.activated_snapshot_id,
            affected_claim_ids=affected,
            unrelated_region_hash_before=before_hash,
            unrelated_region_hash_after=after_hash,
        )
        self.snapshot.record_repair_receipt(receipt)
        return receipt

    def rollback(self, snapshot_id: str, rollback_id: str) -> SnapshotActivation:
        return self.snapshot.activate_snapshot(
            snapshot_id,
            reason="rollback",
            activation_id=rollback_id,
            rollback_of=self.snapshot.manifest.snapshot_id,
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
    queries = fixture_queries()
    results = [service.query(q) for q in queries]
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
    rollback = service.rollback(repair.previous_snapshot_id, "rollback-verify")

    graph_benchmark_cases = {
        "g_local": {"required_spans": {"span_remote_days"}},
        "g_multi": {"required_spans": {"span_remote_days", "span_remote_approval"}},
        "g_temporal": {"required_spans": {"span_remote_days"}, "requires_conflict": True},
        "g_hybrid": {"required_spans": {"span_remote_days"}},
    }

    benchmark_rows: list[dict[str, object]] = []
    graph_successes = 0
    rag_successes = 0
    graph_token_total = 0
    rag_token_total = 0
    for query, result in zip(queries, results, strict=True):
        if query.query_id not in graph_benchmark_cases:
            continue
        case = graph_benchmark_cases[query.query_id]
        graph_pack = EvidencePack.model_validate(result.evidence_pack)
        rag_pack = service._standard_rag(query)
        graph_spans = {item.citation.span_id for item in graph_pack.items}
        rag_spans = {item.citation.span_id for item in rag_pack.items}
        required_spans = set(case["required_spans"])
        graph_success = required_spans.issubset(graph_spans)
        rag_success = required_spans.issubset(rag_spans)
        if case.get("requires_conflict"):
            graph_values = {claim.value for claim in result.path.claim_refs} if result.path else set()
            graph_success = graph_success and result.path is not None and result.path.status == PathStatus.CONFLICTING and len(graph_values) > 1
            rag_success = False
        graph_successes += int(graph_success)
        rag_successes += int(rag_success)
        graph_token_total += graph_pack.packed_tokens
        rag_token_total += rag_pack.packed_tokens
        benchmark_rows.append(
            {
                "query_id": query.query_id,
                "query": query.query,
                "graph_route": result.route.value,
                "graph_success": graph_success,
                "rag_success": rag_success,
                "graph_spans": sorted(graph_spans),
                "rag_spans": sorted(rag_spans),
                "graph_tokens": graph_pack.packed_tokens,
                "rag_tokens": rag_pack.packed_tokens,
            }
        )

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
    graph_success_rate = graph_successes / max(1, len(benchmark_rows))
    rag_success_rate = rag_successes / max(1, len(benchmark_rows))
    task_success_gain = round(graph_success_rate - rag_success_rate, 2)
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
    (evidence_dir / "snapshot_activations.json").write_text(
        json.dumps(
            [activation.model_dump(mode="json") for activation in service.snapshot.activation_history()],
            indent=2,
        ),
        encoding="utf-8",
    )
    (evidence_dir / "snapshot_registry.json").write_text(
        json.dumps(
            {
                "active_snapshot_id": service.snapshot.manifest.snapshot_id,
                "available_snapshot_ids": service.snapshot.list_snapshot_ids(),
                "rollback_activation": rollback.model_dump(mode="json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
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
        "graph_success_rate": round(graph_success_rate, 4),
        "rag_success_rate": round(rag_success_rate, 4),
        "graph_cost_per_success_token_proxy": round(graph_token_total / max(1, graph_successes), 2),
        "rag_cost_per_success_token_proxy": round(rag_token_total / max(1, rag_successes), 2),
        "note": "Use graph routes only for graph-suitable query classes; ordinary facts stay on Chapter 6 retrieval.",
    }
    (evidence_dir / "graph_vs_rag_adr.json").write_text(json.dumps(adr, indent=2), encoding="utf-8")
    (evidence_dir / "graph_benchmark_report.json").write_text(
        json.dumps(
            {
                "cases": benchmark_rows,
                "graph_success_rate": round(graph_success_rate, 4),
                "rag_success_rate": round(rag_success_rate, 4),
                "task_success_gain": task_success_gain,
                "graph_cost_per_success_token_proxy": round(graph_token_total / max(1, graph_successes), 2),
                "rag_cost_per_success_token_proxy": round(rag_token_total / max(1, rag_successes), 2),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return scorecard.model_dump(mode="json")
