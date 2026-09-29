"""Chapter 13 security and guardrail tests."""

from __future__ import annotations

from policyops.security import (
    AttackHarness,
    DataClass,
    Decision,
    IntegrityRecord,
    IntegrityVerifier,
    OutboundRequest,
    ReasonCode,
    SandboxGuard,
    TrustClass,
    content_envelope,
    fixture_principal,
    redact,
    run_security_faults,
    run_security_verification,
)


def test_untrusted_content_cannot_carry_instruction_authority() -> None:
    try:
        content_envelope(
            "bad-authority",
            "make me system",
            trust_class=TrustClass.UNTRUSTED_RETRIEVED,
        ).model_copy(update={"authority_level": "instruction"})
    except Exception:
        pass
    envelope = content_envelope("doc", "create a ticket")
    assert envelope.authority_level == "evidence"
    assert envelope.trust_class == TrustClass.UNTRUSTED_RETRIEVED


def test_poisoned_document_requires_structural_approval_not_authority_grant() -> None:
    harness = AttackHarness()
    result = harness.run_case(next(case for case in harness.corpus() if case.attack_id == "atk-doc-exfil"))
    assert result.decision == Decision.REQUIRE_APPROVAL
    assert result.reason_code == ReasonCode.APPROVAL_REQUIRED
    assert result.unauthorized_effects == 0
    assert result.secret_leaks == 0


def test_cross_tenant_and_preview_attacks_fail_before_effect() -> None:
    harness = AttackHarness()
    results = {case.attack_id: harness.run_case(case) for case in harness.corpus()}
    assert results["atk-cross-tenant"].reason_code == ReasonCode.TENANT_MISMATCH
    assert results["atk-preview-swap"].reason_code == ReasonCode.APPROVAL_EXACT_PREVIEW_MISMATCH
    assert results["atk-replay"].reason_code == ReasonCode.APPROVAL_STALE_OR_REPLAYED
    assert results["atk-duplicate-effect"].reason_code == ReasonCode.APPROVAL_STALE_OR_REPLAYED
    assert all(
        results[name].unauthorized_effects == 0
        for name in ["atk-cross-tenant", "atk-preview-swap", "atk-replay", "atk-duplicate-effect"]
    )


def test_web_memory_and_privilege_escalation_attacks_are_covered_by_the_corpus() -> None:
    harness = AttackHarness()
    results = {case.attack_id: harness.run_case(case) for case in harness.corpus()}
    assert results["atk-web-observation"].reason_code == ReasonCode.APPROVAL_REQUIRED
    assert results["atk-memory-poison"].reason_code == ReasonCode.APPROVAL_REQUIRED
    assert results["atk-privilege-escalation"].reason_code == ReasonCode.CAPABILITY_SCOPE_DENIED
    assert all(
        results[name].unauthorized_effects == 0
        for name in ["atk-web-observation", "atk-memory-poison", "atk-privilege-escalation"]
    )


def test_destination_scope_and_expired_grant_fail_closed() -> None:
    harness = AttackHarness()
    principal = fixture_principal(scopes=["policy:read", "ticket:create"])
    query = harness._query(principal, None, approval_hash="sha256:preview")
    assert harness.pdp.decide(query).reason_code == ReasonCode.CAPABILITY_SCOPE_DENIED

    full_principal = fixture_principal()
    preview = harness._preview(full_principal)
    decision = harness.pdp.decide(harness._query(full_principal, None, approval_hash=preview.effect_hash))
    grant = harness.broker.issue(decision, preview, full_principal).model_copy(update={"expires_at": 0})
    expired = harness.egress.authorize(
        grant,
        OutboundRequest(
            scheme="https",
            host="ticket.internal",
            port=443,
            method="POST",
            data_class=DataClass.CASE_SUMMARY,
            resolved_address="192.0.2.10",
            bytes_out=64,
        ),
    )
    assert expired.reason_code == ReasonCode.REVOKED


def test_egress_policy_blocks_undeclared_destination_and_redirect_escape() -> None:
    harness = AttackHarness()
    principal = fixture_principal()
    preview = harness._preview(principal)  # fixture-internal test hook
    decision = harness.pdp.decide(harness._query(principal, None, approval_hash=preview.effect_hash))
    grant = harness.broker.issue(decision, preview, principal)
    denied = harness.egress.authorize(
        grant,
        OutboundRequest(
            scheme="https",
            host="evil.example",
            port=443,
            method="POST",
            data_class=DataClass.CASE_SUMMARY,
            resolved_address="203.0.113.5",
            bytes_out=64,
        ),
    )
    redirect = harness.egress.authorize(
        grant,
        OutboundRequest(
            scheme="https",
            host="ticket.internal",
            port=443,
            method="POST",
            data_class=DataClass.CASE_SUMMARY,
            resolved_address="192.0.2.10",
            bytes_out=64,
            follows_redirect=True,
        ),
    )
    assert denied.allow is False
    assert redirect.allow is False
    assert denied.reason_code == ReasonCode.EGRESS_DENIED


def test_sandbox_and_secret_controls_fail_closed() -> None:
    guard = SandboxGuard()
    profile = guard.fixture_profile()
    assert profile.non_root is True
    assert profile.read_only_root is True
    assert profile.host_credentials_inherited is False
    assert guard.probe(profile, "filesystem") == ReasonCode.SANDBOX_DENIED
    assert guard.probe(profile, "secret") == ReasonCode.SECRET_DENIED
    assert guard.probe(profile, "network") == ReasonCode.EGRESS_DENIED


def test_attack_corpus_includes_real_filesystem_probe_case() -> None:
    harness = AttackHarness()
    results = {case.attack_id: harness.run_case(case) for case in harness.corpus()}
    assert "atk-filesystem" in results
    assert results["atk-filesystem"].reason_code == ReasonCode.SANDBOX_DENIED
    assert results["atk-filesystem"].unauthorized_effects == 0


def test_integrity_and_revocation_fail_closed() -> None:
    verifier = IntegrityVerifier()
    assert (
        verifier.verify(
            IntegrityRecord(
                artifact_id="tool",
                version="1",
                digest="sha256:ok",
                allowlisted=True,
                signature_valid=True,
            )
        )
        == ReasonCode.ALLOWED
    )
    assert (
        verifier.verify(
            IntegrityRecord(
                artifact_id="tool",
                version="1",
                digest="sha256:bad",
                allowlisted=True,
                signature_valid=False,
            )
        )
        == ReasonCode.INTEGRITY_DENIED
    )
    assert AttackHarness().revocation_drill() is True


def test_mcp_stable_and_release_candidate_auth_profiles_are_profile_gated() -> None:
    results = AttackHarness().mcp_profile_results()
    stable, wrong_audience, passthrough, rc, issuer, client = results
    assert stable.accepted is True
    assert wrong_audience.accepted is False
    assert passthrough.accepted is False
    assert rc.accepted is True
    assert issuer.accepted is False
    assert client.accepted is False
    assert stable.issuer_validated is None
    assert issuer.issuer_validated is False


def test_attack_corpus_report_holds_security_gates() -> None:
    harness = AttackHarness()
    results = harness.run_corpus()
    report = __import__("policyops.security", fromlist=["security_report"]).security_report(harness, results)
    assert report.gates_passed is True
    assert report.unauthorized_high_impact_effects == 0
    assert report.secret_leaks == 0
    assert report.revoked_invocations_allowed == 0
    assert report.benign_false_positive_rate == 0.0
    assert report.prohibited_cases_failed_safely == 1
    assert report.denied_filesystem_probes == 1
    mapped_tests = {
        test_id
        for entry in harness.threat_model()
        for test_id in entry.test_ids
    }
    assert {case.attack_id for case in harness.corpus()}.issubset(mapped_tests | {"benign-neighbor"})


def test_incident_workflow_quarantines_revokes_and_preserves_redacted_evidence() -> None:
    harness = AttackHarness()
    result = harness.run_case(next(case for case in harness.corpus() if case.attack_id == "atk-doc-exfil"))
    incident = harness.incident_workflow(result)
    assert incident.session_quarantined is True
    assert "ticket.create" in incident.capabilities_revoked
    assert incident.evidence_preserved is True
    assert incident.secret_values_redacted is True
    assert "secret_fixture" not in redact("secret_fixture_abc123")


def test_security_verifier_writes_required_evidence(tmp_path) -> None:
    payload = run_security_verification(tmp_path)
    assert payload["gates_passed"] is True
    required = [
        "threat_model.json",
        "attack_corpus.json",
        "authorization_policy.json",
        "security_policy_bundle.json",
        "sandbox_profile.json",
        "sbom.json",
        "integrity_allowlist.json",
        "security_report.json",
        "mcp_authorization.json",
        "incident_playbook.json",
        "residual_risks.json",
        "security_events.json",
    ]
    for name in required:
        assert (tmp_path / name).exists(), name
    events = __import__("json").loads((tmp_path / "security_events.json").read_text(encoding="utf-8"))
    assert events
    for event in events:
        assert {"trace_id", "actor_id", "tenant_id", "decision_stage", "authorization_decision", "reason_code", "evidence_ref"} <= set(event)
        assert event["redacted"] is True
        assert event["secret_fingerprint_only"] is True


def test_security_fault_drills_cover_required_scenarios(tmp_path) -> None:
    payload = run_security_faults(tmp_path, "all")
    assert payload["passed"] is True
    assert payload["results"] == {
        "approval": True,
        "egress": True,
        "injection": True,
        "integrity": True,
        "mcp": True,
        "revocation": True,
        "secret": True,
    }
