"""Chapter 15 governance release-gate tests."""

from __future__ import annotations

from policyops.governance import (
    Decision,
    EvidenceResolver,
    GovernanceFixture,
    GovernanceVerification,
    NoticeGenerator,
    ReasonCode,
    ReleaseGate,
    RightsOrchestrator,
    RightsRequest,
    run_governance_faults,
    run_governance_verification,
)


def test_fixture_inventory_and_high_risks_have_human_owners() -> None:
    fixture = GovernanceFixture()
    owners = {owner.owner_id for owner in fixture.owners() if owner.current}
    assert set(fixture.inventory().owners).issubset(owners)
    assert all(risk.owner_id in owners for risk in fixture.risks())
    assert all(control.owner_id in owners for control in fixture.controls())


def test_clean_release_gate_returns_go_with_deterministic_digest() -> None:
    gate = ReleaseGate()
    one = gate.review()
    two = gate.review()
    assert one.decision == Decision.GO
    assert one.decision_digest == two.decision_digest
    assert one.reasons == []


def test_missing_owner_stale_tampered_failed_and_self_approval_return_no_go() -> None:
    verifier = GovernanceVerification()
    decisions = verifier.invalid_evidence_decisions()
    reasons = {reason.reason_code for decision in decisions for reason in decision.reasons}
    assert all(decision.decision == Decision.NO_GO for decision in decisions)
    assert ReasonCode.OWNER_MISSING in reasons
    assert ReasonCode.EVIDENCE_STALE in reasons
    assert ReasonCode.EVIDENCE_TAMPERED in reasons
    assert ReasonCode.TEST_FAILED in reasons
    assert ReasonCode.APPROVER_NOT_INDEPENDENT in reasons
    assert ReasonCode.RIGHTS_INCOMPLETE in reasons


def test_rights_receipt_covers_all_inventory_stores_and_blocks_partial_coverage() -> None:
    inventory = GovernanceFixture().inventory()
    orchestrator = RightsOrchestrator(inventory)
    request = RightsRequest(
        request_id="delete-test",
        tenant_id="tenant-alpha",
        subject_id="subject-42",
        request_type="deletion",
        authenticated=True,
        scope="policyops user records",
    )
    complete = orchestrator.process(request)
    partial = orchestrator.process(request, miss_store="memory_ledger")
    unauthenticated = orchestrator.process(request.model_copy(update={"authenticated": False}))
    assert complete.complete is True
    assert {store.store for store in complete.stores} == set(inventory.stores)
    assert partial.complete is False
    assert unauthenticated.complete is False


def test_rights_requests_reuse_scoped_workflow_and_persist_per_store_task_state() -> None:
    inventory = GovernanceFixture().inventory()
    orchestrator = RightsOrchestrator(inventory)
    request = RightsRequest(
        request_id="delete-test",
        tenant_id="tenant-alpha",
        subject_id="subject-42",
        request_type="deletion",
        authenticated=True,
        scope="policyops user records",
    )
    first = orchestrator.process(request, miss_store="trace_store")
    second = orchestrator.process(request.model_copy(update={"request_id": "delete-test-retry"}))
    workflow = orchestrator.workflow(request)
    assert first.workflow_id == second.workflow_id
    assert first.request_digest == second.request_digest
    assert len(workflow) == len(inventory.stores)
    assert all(task.status == "completed" for task in workflow)
    assert all(task.verifier_passed for task in workflow)


def test_signature_role_mismatch_is_rejected() -> None:
    fixture = GovernanceFixture()
    evidence = fixture.evidence()[0]
    forged = evidence.model_copy(
        update={
            "signature": evidence.signature.model_copy(update={"issuer_role": "release_approver"}),
        }
    )
    reasons = EvidenceResolver(fixture.owners()).validate(forged)
    assert ReasonCode.SIGNATURE_INVALID in reasons


def test_non_human_signer_is_rejected_for_release_evidence() -> None:
    fixture = GovernanceFixture()
    evidence = fixture.evidence()[0]
    forged = evidence.model_copy(
        update={
            "signature": evidence.signature.model_copy(update={"issuer": "agent-policyops", "issuer_role": "agent"}),
        }
    )
    reasons = EvidenceResolver(fixture.owners()).validate(forged)
    assert ReasonCode.SIGNATURE_INVALID in reasons


def test_transparency_notice_is_generated_from_inventory() -> None:
    inventory = GovernanceFixture().inventory()
    notice = NoticeGenerator().render(inventory)
    assert set(notice.tools_and_actions).issubset(set(inventory.tools))
    assert "AI" in notice.ai_involvement
    assert "deletion" in notice.rights_channels


def test_governance_scorecard_passes_after_authorized_remediation() -> None:
    scorecard, evidence = GovernanceVerification().scorecard()
    assert scorecard.gates_passed is True
    assert scorecard.high_risk_paths_resolved is True
    assert scorecard.invalid_evidence_cases_blocked >= 5
    assert scorecard.agent_self_approval_denied is True
    assert {receipt["request_id"] for receipt in evidence["rights_receipts"]} == {
        "rights-correct-001",
        "rights-export-001",
        "rights-delete-001",
    }
    assert evidence["graph"]["nodes"]
    assert evidence["graph"]["edges"]
    assert evidence["final_decision"]["decision"] == "GO"


def test_control_evidence_graph_contains_mandatory_risk_control_and_evidence_paths() -> None:
    evidence = GovernanceVerification().scorecard()[1]
    graph = evidence["graph"]
    node_ids = {node["node_id"] for node in graph["nodes"]}
    edges = {(edge["from"], edge["relation"], edge["to"]) for edge in graph["edges"]}
    assert "risk-high-impact-ticket" in node_ids
    assert "control-deployment" in node_ids
    assert "ev-ch14-deploy" in node_ids
    assert ("risk-high-impact-ticket", "MITIGATED_BY", "control-deployment") in edges
    assert ("control-deployment", "VERIFIED_BY", "ev-ch14-deploy") in edges
    assert any(edge[1] == "APPROVED_BY_POLICY" for edge in edges)


def test_governance_verifier_writes_required_evidence(tmp_path) -> None:
    payload = run_governance_verification(tmp_path)
    assert payload["gates_passed"] is True
    required = [
        "system_inventory.json",
        "risk_autonomy_records.json",
        "ownership_records.json",
        "approval_matrix.json",
        "control_evidence_graph.json",
        "evidence_index.json",
        "rights_receipts.json",
        "transparency_notice.json",
        "invalid_evidence_decisions.json",
        "release_decision.json",
        "governance_scorecard.json",
    ]
    for name in required:
        assert (tmp_path / name).exists(), name
    receipts = __import__("json").loads((tmp_path / "rights_receipts.json").read_text(encoding="utf-8"))
    assert {receipt["request_id"] for receipt in receipts} == {
        "rights-correct-001",
        "rights-export-001",
        "rights-delete-001",
    }
    graph = __import__("json").loads((tmp_path / "control_evidence_graph.json").read_text(encoding="utf-8"))
    assert graph["graph_version"] == "1"
    assert graph["nodes"]
    assert graph["edges"]


def test_governance_fault_drills_cover_required_scenarios(tmp_path) -> None:
    payload = run_governance_faults(tmp_path, "all")
    assert payload["passed"] is True
    assert payload["results"] == {
        "determinism": True,
        "failed": True,
        "owner": True,
        "rights": True,
        "separation": True,
        "stale": True,
        "tamper": True,
    }
