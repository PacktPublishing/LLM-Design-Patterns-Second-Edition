"""Chapter 6 citation-first hybrid RAG tests."""

from __future__ import annotations

import json
from pathlib import Path

from policyops.context import ContextPlanner, fixture_request
from policyops.retrieval import (
    EvidenceContextSource,
    FixtureCorpus,
    HybridRetriever,
    Principal,
    QueryClass,
    QueryRequest,
    Sufficiency,
    gold_requests,
    run_retrieval_verification,
)


def _principal(tenant: str = "tenant_alpha", labels: list[str] | None = None) -> Principal:
    return Principal(
        tenant_id=tenant,
        actor_id="actor_reader",
        scopes=["policy:read"],
        allowed_labels=labels or ["policy:read"],
    )


def _request(query: str, **overrides) -> QueryRequest:
    data = {
        "query_id": "q-test",
        "query": query,
        "principal": _principal(),
    }
    data.update(overrides)
    return QueryRequest(**data)


def test_direct_remote_query_returns_resolvable_exact_citation() -> None:
    retriever = HybridRetriever()
    request = _request("How many remote days are allowed?", expected_span_ids=["span_remote_days"])
    pack = retriever.query(request)
    assert pack.sufficiency == Sufficiency.SUFFICIENT
    assert pack.items[0].citation.span_id == "span_remote_days"
    assert retriever.corpus.resolve(pack.items[0].citation, request.principal) == pack.items[0].text


def test_authorization_filter_runs_before_ranking_and_blocks_cross_tenant_results() -> None:
    retriever = HybridRetriever()
    pack = retriever.query(_request("remote days beta"))
    assert all(item.citation.source_id != "policy_beta" for item in pack.items)


def test_missing_scope_fails_closed() -> None:
    retriever = HybridRetriever()
    request = _request(
        "remote days",
        principal=Principal(
            tenant_id="tenant_alpha", actor_id="actor_reader", scopes=[], allowed_labels=["policy:read"]
        ),
    )
    pack = retriever.query(request)
    assert pack.sufficiency == Sufficiency.INSUFFICIENT
    assert "AUTH_SCOPE_REQUIRED" in pack.reason_codes


def test_poisoned_passage_is_excluded_and_recorded() -> None:
    retriever = HybridRetriever()
    pack = retriever.query(_request("approve every remote exception"))
    assert all("Ignore previous instructions" not in item.text for item in pack.items)
    assert "poisoned_passage_excluded" in pack.reason_codes


def test_table_query_preserves_cell_lineage() -> None:
    retriever = HybridRetriever()
    request = _request("remote table maximum days", expected_span_ids=["span_remote_table"])
    pack = retriever.query(request)
    table_item = next(item for item in pack.items if item.citation.span_id == "span_remote_table")
    assert table_item.citation.table_cell == "row=Remote work;col=Max days"


def test_scanned_query_preserves_page_region_lineage() -> None:
    retriever = HybridRetriever()
    request = _request("scanned OCR travel receipts", expected_span_ids=["span_scanned_receipts"])
    pack = retriever.query(request)
    scanned = next(item for item in pack.items if item.citation.span_id == "span_scanned_receipts")
    assert scanned.citation.page == 3
    assert scanned.citation.region == (0.15, 0.20, 0.70, 0.30)


def test_out_of_scope_query_abstains() -> None:
    retriever = HybridRetriever()
    pack = retriever.query(_request("What is the weather today?"))
    assert pack.query_class == QueryClass.OUT_OF_SCOPE
    assert pack.sufficiency == Sufficiency.INSUFFICIENT


def test_multi_hop_query_gets_one_bounded_transformation() -> None:
    retriever = HybridRetriever()
    pack = retriever.query(_request("remote days and approval exceptions"))
    assert pack.query_class == QueryClass.MULTI_HOP
    assert pack.transformed_query == "remote days approval exceptions"


def test_deletion_removes_searchable_spans_and_is_idempotent() -> None:
    corpus = FixtureCorpus()
    retriever = HybridRetriever(corpus)
    receipt = corpus.delete_source("policy_remote", "v2", "delete-1")
    again = corpus.delete_source("policy_remote", "v2", "delete-1")
    pack = retriever.query(_request("remote days", expected_span_ids=["span_remote_days"]))
    assert receipt.action == "delete"
    assert again.action == "delete"
    assert receipt.freshness_lag_ms <= 60_000
    assert pack.sufficiency == Sufficiency.INSUFFICIENT


def test_replacement_activates_new_version_and_old_citation_stops_resolving() -> None:
    corpus = FixtureCorpus()
    retriever = HybridRetriever(corpus)
    old_pack = retriever.query(_request("remote days", expected_span_ids=["span_remote_days"]))
    old_citation = old_pack.items[0].citation
    receipt = corpus.replace_source("policy_remote", "Remote work now allows three days.", "replace-1")
    new_pack = retriever.query(_request("three days", expected_span_ids=[]))
    assert receipt.previous_version_id == "v2"
    assert receipt.active_version_id == "v3"
    assert corpus.resolve(old_citation, _principal()) is None
    assert any(item.citation.version_id == "v3" for item in new_pack.items)


def test_replacement_is_idempotent_and_records_active_manifest() -> None:
    corpus = FixtureCorpus()
    first = corpus.replace_source("policy_remote", "Remote work now allows three days.", "replace-same")
    second = corpus.replace_source("policy_remote", "Remote work now allows three days.", "replace-same")
    assert first == second
    assert corpus.versions["policy_remote"].version_id == "v3"
    manifest = corpus.index_manifests[first.manifest_generation]
    assert manifest.active_versions["policy_remote"] == "v3"
    assert any(job.idempotency_key == "replace-same" for job in corpus.ingestion_jobs.values())


def test_timeout_returns_typed_abstention() -> None:
    retriever = HybridRetriever()
    pack = retriever.query(_request("remote days"), timeout_stage="vector")
    assert pack.sufficiency == Sufficiency.INSUFFICIENT
    assert "vector_timeout" in pack.reason_codes


def test_gold_requests_clear_retrieval_metrics(tmp_path: Path) -> None:
    scorecard = run_retrieval_verification(tmp_path)
    assert scorecard["gates_passed"] is True
    assert scorecard["recall_at_10"] >= 0.85
    assert scorecard["ndcg_at_10"] >= 0.75
    assert (tmp_path / "scorecard.json").exists()
    assert (tmp_path / "query_report.json").exists()
    query_report = json.loads((tmp_path / "query_report.json").read_text(encoding="utf-8"))
    assert query_report["p95_latency_ms"] >= 1
    assert query_report["abstention_accuracy"] == 1.0


def test_evidence_pack_can_feed_chapter_five_context_source() -> None:
    retriever = HybridRetriever()
    pack = retriever.query(gold_requests()[0])
    source = EvidenceContextSource(pack)
    rendered, manifest = ContextPlanner(sources=[source]).plan(
        fixture_request(required_fact_ids=["retrieval.span_remote_days"])
    )
    assert rendered is not None
    assert manifest.terminal_reason.value == "ready"
    assert "Eligible employees may work remotely" in rendered.model_request_text


def test_budget_limits_passage_count_and_tokens() -> None:
    retriever = HybridRetriever()
    request = _request(
        "remote days approval table",
        budget={"max_candidates": 10, "max_passages": 1, "max_tokens": 32},
    )
    pack = retriever.query(request)
    assert len(pack.items) <= 1
    assert pack.packed_tokens <= 32


def test_deleted_fixture_source_is_not_returned() -> None:
    retriever = HybridRetriever()
    pack = retriever.query(_request("deleted source searchable"))
    assert all(item.citation.source_id != "policy_deleted" for item in pack.items)


def test_sqlite_backed_fixture_corpus_persists_replacements_and_deletions(tmp_path: Path) -> None:
    db_path = tmp_path / "retrieval.sqlite3"
    corpus = FixtureCorpus(db_path=db_path)
    corpus.replace_source("policy_remote", "Remote work now allows three days.", "replace-persist")
    corpus.delete_source("policy_scanned", "v1", "delete-persist")

    reloaded = FixtureCorpus(db_path=db_path)

    assert reloaded.versions["policy_remote"].version_id == "v3"
    assert reloaded.versions["policy_scanned"].deleted is True
    assert len(reloaded.receipts) == 2
    assert len(reloaded.ingestion_jobs) == 2
    assert max(reloaded.index_manifests).bit_length() > 0
