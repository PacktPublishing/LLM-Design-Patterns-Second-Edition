"""Chapter 7 graph retrieval tests."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from policyops.graph import (
    GraphQuery,
    GraphRoute,
    GraphSnapshot,
    GraphService,
    PathStatus,
    fixture_queries,
    run_graph_verification,
)
from policyops.retrieval import EvidencePack, Sufficiency


def _query(text: str, **overrides) -> GraphQuery:
    data = {
        "query_id": "g-test",
        "query": text,
        "tenant_id": "tenant_alpha",
        "actor_id": "actor_reader",
        "allowed_labels": ["policy:read"],
    }
    data.update(overrides)
    return GraphQuery(**data)


def test_router_keeps_ordinary_question_on_standard_rag() -> None:
    service = GraphService()
    result = service.query(_query("What is the weather?"))
    assert result.route == GraphRoute.STANDARD_RAG
    assert result.path is None


def test_local_graph_path_resolves_to_source_linked_evidence() -> None:
    service = GraphService()
    result = service.query(_query("remote work days"))
    assert result.route == GraphRoute.LOCAL_GRAPH
    assert result.path is not None
    assert result.path.status == PathStatus.SUPPORTED
    pack = EvidencePack.model_validate(result.evidence_pack)
    assert pack.sufficiency == Sufficiency.SUFFICIENT
    assert {item.citation.span_id for item in pack.items}


def test_multi_hop_graph_returns_claim_chain() -> None:
    service = GraphService()
    result = service.query(_query("remote work approval requires relationship"))
    assert result.route == GraphRoute.MULTI_HOP_GRAPH
    assert result.path is not None
    assert {"claim_remote_days_v2", "claim_remote_approval"}.issubset(
        {claim.claim_id for claim in result.path.claim_refs}
    )


def test_temporal_contradiction_preserves_competing_claims() -> None:
    service = GraphService()
    result = service.query(_query("remote days conflict", as_of=date(2025, 6, 1)))
    assert result.route == GraphRoute.TEMPORAL_GRAPH
    assert result.path is not None
    assert result.path.status == PathStatus.CONFLICTING
    assert "unresolved_temporal_conflict" in result.path.reason_codes
    assert len({claim.value for claim in result.path.claim_refs}) > 1


def test_as_of_date_filters_superseded_claims() -> None:
    service = GraphService()
    result = service.query(_query("remote days as of 2024", as_of=date(2024, 6, 1)))
    assert result.path is not None
    assert {claim.value for claim in result.path.claim_refs} == {"5"}


def test_hybrid_alias_route_uses_graph_without_losing_evidence_boundary() -> None:
    service = GraphService()
    result = service.query(_query("telework alias remote"))
    assert result.route == GraphRoute.HYBRID_GRAPH_VECTOR
    pack = EvidencePack.model_validate(result.evidence_pack)
    assert pack.items
    assert all(item.citation.content_hash.startswith("sha256:") for item in pack.items)


def test_cross_tenant_query_never_returns_beta_claims() -> None:
    service = GraphService()
    result = service.query(_query("beta remote relationship"))
    if result.path:
        assert all(claim.tenant_id == "tenant_alpha" for claim in result.path.claim_refs)
    pack = EvidencePack.model_validate(result.evidence_pack)
    assert all(item.citation.source_id != "policy_beta" for item in pack.items)


def test_traversal_timeout_returns_partial_uncited_result() -> None:
    service = GraphService()
    result = service.query(_query("remote approval relationship"), force_timeout=True)
    assert result.path is not None
    assert result.path.status == PathStatus.PARTIAL
    assert "graph_timeout" in result.warnings
    pack = EvidencePack.model_validate(result.evidence_pack)
    assert pack.sufficiency == Sufficiency.INSUFFICIENT


def test_hop_budget_limits_multi_hop_path() -> None:
    service = GraphService()
    result = service.query(_query("remote work approval requires relationship", max_hops=1))
    assert result.path is not None
    assert len(result.path.claim_refs) <= 1
    assert result.path.status in {PathStatus.PARTIAL, PathStatus.SUPPORTED}


def test_repair_delete_atomic_swap_preserves_unrelated_region_hash() -> None:
    service = GraphService()
    receipt = service.repair("delete", "policy_conflict", "repair-1")
    assert receipt.atomic is True
    assert receipt.activated_snapshot_id == receipt.candidate_snapshot_id
    assert receipt.unrelated_region_hash_before == receipt.unrelated_region_hash_after
    result = service.query(_query("remote days conflict", as_of=date(2025, 6, 1)))
    assert result.path is not None
    assert "claim_remote_days_conflict" not in {claim.claim_id for claim in result.path.claim_refs}


def test_repair_replay_returns_original_receipt_without_new_activation(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite3"
    service = GraphService(snapshot=GraphSnapshot(db_path=db_path))
    first = service.repair("delete", "policy_conflict", "repair-replay")
    second = service.repair("delete", "policy_conflict", "repair-replay")

    assert second == first
    assert [activation.activation_id for activation in service.snapshot.activation_history()] == [
        "activate-graph-snapshot-v1",
        "activate-repair-replay",
    ]


def test_rollback_restores_prior_snapshot_and_persists_activation_history(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite3"
    service = GraphService(snapshot=GraphSnapshot(db_path=db_path))
    receipt = service.repair("delete", "policy_conflict", "repair-rollback")
    rollback = service.rollback(receipt.previous_snapshot_id, "rollback-1")

    assert rollback.activated_snapshot_id == receipt.previous_snapshot_id
    result = service.query(_query("remote days conflict", as_of=date(2025, 6, 1)))
    assert result.path is not None
    assert "claim_remote_days_conflict" in {claim.claim_id for claim in result.path.claim_refs}

    reloaded = GraphService(snapshot=GraphSnapshot(db_path=db_path))
    assert reloaded.snapshot.manifest.snapshot_id == receipt.previous_snapshot_id
    assert [activation.activation_id for activation in reloaded.snapshot.activation_history()] == [
        "activate-graph-snapshot-v1",
        "activate-repair-rollback",
        "rollback-1",
    ]


def test_fixture_verification_writes_scorecard_and_adr(tmp_path: Path) -> None:
    scorecard = run_graph_verification(tmp_path)
    assert scorecard["gates_passed"] is True
    assert (tmp_path / "graph_scorecard.json").exists()
    assert (tmp_path / "graph_vs_rag_adr.json").exists()
    assert (tmp_path / "graph_benchmark_report.json").exists()
    assert (tmp_path / "snapshot_activations.json").exists()
    assert (tmp_path / "snapshot_registry.json").exists()
    benchmark = json.loads((tmp_path / "graph_benchmark_report.json").read_text(encoding="utf-8"))
    assert benchmark["task_success_gain"] >= 0.15
    assert benchmark["graph_success_rate"] > benchmark["rag_success_rate"]


def test_fixture_query_routes_are_deterministic() -> None:
    service = GraphService()
    first = [service.query(query).model_dump(mode="json") for query in fixture_queries()]
    second = [service.query(query).model_dump(mode="json") for query in fixture_queries()]
    assert first == second


def test_sqlite_backed_graph_snapshot_persists_repairs_across_fresh_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite3"
    snapshot = GraphSnapshot(db_path=db_path)
    snapshot.mark_deleted("claim_remote_days_conflict")
    snapshot.update_claim(
        snapshot.claims["claim_remote_days_v2"].model_copy(update={"confidence": 0.99})
    )
    snapshot.manifest = snapshot.manifest.model_copy(update={"content_hash": snapshot.content_hash()})

    reloaded = GraphSnapshot(db_path=db_path)

    assert "claim_remote_days_conflict" in reloaded.deleted_claims
    assert reloaded.claims["claim_remote_days_v2"].confidence == 0.99


def test_sqlite_backed_graph_service_persists_repair_receipts(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.sqlite3"
    service = GraphService(snapshot=GraphSnapshot(db_path=db_path))
    receipt = service.repair("delete", "policy_conflict", "repair-persisted")

    reloaded = GraphService(snapshot=GraphSnapshot(db_path=db_path))

    assert reloaded.snapshot.repair_receipt("repair-persisted") == receipt
