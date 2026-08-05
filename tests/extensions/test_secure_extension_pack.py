"""Chapter 9 secure extension-pack tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from policyops.context import ContextRequest, SourceKind
from policyops.extensions import (
    CapabilityContextSource,
    CapabilityResource,
    DomainErrorCode,
    ExtensionRuntime,
    ImpactClass,
    McpAdapter,
    McpProfile,
    PluginLoader,
    SecuredToolPort,
    SkillActivator,
    TicketInput,
    TicketStatus,
    fixture_context,
    fixture_manifest,
    fixture_ticket,
    run_extension_verification,
)


def test_preview_is_canonical_and_side_effect_free() -> None:
    port = SecuredToolPort()
    context = fixture_context()
    preview = port.preview_policy_ticket(fixture_ticket(), context)
    assert preview.effect_hash.startswith("sha256:")
    assert not port.repository.tickets
    assert preview.canonical_effect.source_refs == sorted(preview.canonical_effect.source_refs)


def test_missing_or_stale_approval_denies_before_repository_write() -> None:
    port = SecuredToolPort()
    context = fixture_context()
    preview = port.preview_policy_ticket(fixture_ticket(), context)
    denied = port.create_policy_ticket(preview, None, "idem-denied", context)
    assert denied.status == TicketStatus.DENIED
    assert denied.reason_code == DomainErrorCode.APPROVAL_REQUIRED
    assert not port.repository.tickets

    stale = port.approval_store.issuer.issue(
        preview,
        context,
        nonce="stale",
        expires_at=port.approval_store.now - 1,
    )
    denied_stale = port.create_policy_ticket(preview, stale, "idem-stale", context)
    assert denied_stale.reason_code == DomainErrorCode.APPROVAL_STALE
    assert not port.repository.tickets


def test_exact_effect_hash_and_actor_are_bound_to_approval() -> None:
    port = SecuredToolPort()
    context = fixture_context()
    preview = port.preview_policy_ticket(fixture_ticket(), context)
    changed_preview = port.preview_policy_ticket(
        TicketInput(
            tenant_id="tenant_alpha",
            title="Remote-work exception support",
            description="Create a different ticket after the approval was issued.",
            severity="medium",
            source_refs=["policy_remote:v2:span_remote_approval"],
        ),
        context,
    )
    approval = port.approval_store.issuer.issue(
        preview,
        context,
        nonce="exact",
        expires_at=port.approval_store.now + 60,
    )
    result = port.create_policy_ticket(changed_preview, approval, "idem-mismatch", context)
    assert result.status == TicketStatus.DENIED
    assert result.reason_code == DomainErrorCode.EFFECT_MISMATCH


def test_direct_and_mcp_paths_converge_on_same_toolport_and_idempotency() -> None:
    port = SecuredToolPort()
    context = fixture_context()
    mcp = McpAdapter(port)
    preview = mcp.preview(fixture_ticket(), context)
    approval = port.approval_store.issuer.issue(
        preview,
        context,
        nonce="mcp-1",
        expires_at=port.approval_store.now + 60,
    )
    first = mcp.create(preview, approval, "idem-one", context)
    duplicate = port.repository.create_once(preview, context, "idem-one")
    assert first.status == TicketStatus.CREATED
    assert duplicate.ticket_id == first.ticket_id
    assert len(port.repository.tickets) == 1


def test_sqlite_backed_ticket_and_audit_state_persist_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "extensions.sqlite"
    first = SecuredToolPort(db_path=db_path)
    context = fixture_context()
    preview = first.preview_policy_ticket(fixture_ticket(), context)
    approval = first.approval_store.issuer.issue(
        preview,
        context,
        nonce="persist-1",
        expires_at=first.approval_store.now + 60,
    )
    created = first.create_policy_ticket(preview, approval, "idem-persist", context)
    assert created.status == TicketStatus.CREATED

    second = SecuredToolPort(db_path=db_path)
    duplicate = second.repository.create_once(preview, context, "idem-persist")
    assert duplicate.ticket_id == created.ticket_id
    assert len(second.repository.tickets) == 1
    assert len(second.audit_store.events) == 1
    assert second.state_store.workflow_state["req-ch09:workflow"]["last_operation"] == "create_policy_ticket"
    assert second.state_store.resumable_results["req-ch09:idem-persist"]["ticket_id"] == created.ticket_id


def test_mcp_transport_persists_subscription_and_resumable_result_state(tmp_path: Path) -> None:
    db_path = tmp_path / "extensions.sqlite"
    port = SecuredToolPort(db_path=db_path)
    context = fixture_context()
    adapter = McpAdapter(port)
    preview = adapter.preview(fixture_ticket(), context)
    approval = port.approval_store.issuer.issue(
        preview,
        context,
        nonce="mcp-state",
        expires_at=port.approval_store.now + 60,
    )
    created = adapter.create(preview, approval, "idem-mcp-state", context)
    reopened = SecuredToolPort(db_path=db_path)
    assert reopened.state_store.subscriptions["tenant_alpha:2025-11-25:schema-help"]["status"] == "active"
    assert reopened.state_store.workflow_state["req-ch09:workflow"]["transport"] == "mcp"
    assert reopened.state_store.resumable_results["mcp:req-ch09:idem-mcp-state"]["ticket_id"] == created.ticket_id


def test_pre_hook_timeout_and_revocation_fail_closed() -> None:
    port = SecuredToolPort()
    context = fixture_context()
    preview = port.preview_policy_ticket(fixture_ticket(), context)
    approval = port.approval_store.issuer.issue(
        preview,
        context,
        nonce="timeout",
        expires_at=port.approval_store.now + 60,
    )
    port.pre_hook.force_timeout = True
    timeout = port.create_policy_ticket(preview, approval, "idem-timeout", context)
    assert timeout.reason_code == DomainErrorCode.HOOK_TIMEOUT
    assert not port.repository.tickets

    port.pre_hook.force_timeout = False
    port.registry.revoke(port.extension_id)
    revoked = port.create_policy_ticket(preview, approval, "idem-revoked", context)
    assert revoked.reason_code == DomainErrorCode.EXTENSION_REVOKED


def test_post_hook_failure_degrades_evidence_without_duplicating_mutation() -> None:
    port = SecuredToolPort()
    context = fixture_context()
    preview = port.preview_policy_ticket(fixture_ticket(), context)
    approval = port.approval_store.issuer.issue(
        preview,
        context,
        nonce="post-failure",
        expires_at=port.approval_store.now + 60,
    )
    port.audit_store.fail_next = True
    result = port.create_policy_ticket(preview, approval, "idem-post-failure", context)
    assert result.status == TicketStatus.CREATED
    assert result.evidence_status == "degraded"
    assert len(port.repository.tickets) == 1


def test_plugin_loader_rejects_tamper_revocation_and_excessive_permissions() -> None:
    loader = PluginLoader()
    manifest, files = fixture_manifest(loader)
    accepted = loader.install(manifest, files)
    assert accepted.accepted is True

    tampered_manifest, tampered_files = fixture_manifest(loader, tampered=True)
    tampered = loader.verify(tampered_manifest, tampered_files)
    assert tampered.accepted is False
    assert any(reason.startswith("hash_mismatch") for reason in tampered.reason_codes)

    loader.revoke("policyops-ticket-pack")
    revoked = loader.verify(manifest, files)
    assert revoked.accepted is False
    assert "revoked" in revoked.reason_codes

    risky = manifest.model_copy(update={"permissions": ["filesystem:any"]})
    risky.signature = loader.sign_manifest(risky)
    risky_check = loader.verify(risky, files)
    assert risky_check.accepted is False
    assert "excessive_permission" in risky_check.reason_codes


def test_runtime_lifecycle_stage_activate_disable_rollback_and_revoke(tmp_path: Path) -> None:
    runtime = ExtensionRuntime(tmp_path / "runtime")
    loader = runtime.loader
    initial = runtime.list_extensions()
    assert any(item.version == "1.0.0" and item.status.value == "active" for item in initial)

    manifest, files = fixture_manifest(loader, version="1.1.0", predecessor="1.0.0")
    staged = runtime.stage_package(manifest, files)
    assert staged.accepted is True

    activated = runtime.activate_extension("policyops-ticket-pack", "1.1.0")
    assert activated.version == "1.1.0"
    assert activated.status.value == "active"

    disabled = runtime.disable_extension("policyops-ticket-pack")
    assert disabled.status.value == "disabled"

    runtime.activate_extension("policyops-ticket-pack", "1.1.0")
    rolled_back = runtime.rollback_extension("policyops-ticket-pack")
    assert rolled_back.version == "1.0.0"
    assert rolled_back.status.value == "active"

    revoked = runtime.revoke_extension("policyops-ticket-pack")
    assert revoked.version == "1.0.0"
    assert revoked.status.value == "revoked"


def test_rc_mcp_profile_is_opt_in_and_fails_closed_by_default() -> None:
    port = SecuredToolPort()
    mcp = McpAdapter(port, profile=McpProfile.RC_2026_07_28)
    with pytest.raises(RuntimeError, match="unsupported_mcp_profile"):
        mcp.preview(fixture_ticket(), fixture_context())


def test_skill_activation_is_precise_and_requires_explicit_sensitive_mutation() -> None:
    activator = SkillActivator()
    scorecard = activator.benchmark()
    assert scorecard.gates_passed is True
    create_without_explicit = activator.evaluate(
        "ambiguous-create",
        "Create a policy exception ticket",
        explicit=False,
    )
    assert create_without_explicit.activated is False
    assert create_without_explicit.reason_code == "explicit_invocation_required"


def test_capability_context_source_exposes_metadata_without_invocation_or_secrets() -> None:
    resource = CapabilityResource(
        resource_id="cap-ticket-preview",
        name="preview_policy_ticket",
        impact=ImpactClass.READ,
        input_schema={"title": "str", "description": "str"},
        extension_id="policyops-ticket-pack",
        version="1.0.0",
        available=True,
    )
    source = CapabilityContextSource([resource])
    request = ContextRequest(
        request_id="ctx-cap",
        tenant_id="tenant_alpha",
        actor_id="actor_reader",
        task="answer",
        question="What capability is available?",
    )
    summaries = source.summaries(request)
    assert summaries[0].source_kind == SourceKind.CAPABILITY
    item = source.materialize(summaries[0].item_id)
    assert "approval" not in item.text.lower()
    assert "token" not in item.text.lower()
    assert "ToolPort" in item.text


def test_secret_in_ticket_description_is_rejected_before_preview() -> None:
    port = SecuredToolPort()
    with pytest.raises(ValueError, match=DomainErrorCode.VALIDATION_ERROR.value):
        port.preview_policy_ticket(
            TicketInput(
                tenant_id="tenant_alpha",
                title="Remote-work exception support",
                description="Please store sk-secret_1234567890 inside the ticket.",
                severity="medium",
                source_refs=["policy_remote:v2:span_remote_approval"],
            ),
            fixture_context(),
        )


def test_fixture_verification_writes_extension_evidence(tmp_path: Path) -> None:
    result = run_extension_verification(tmp_path)
    assert result["gates_passed"] is True
    assert (tmp_path / "tool_contract.json").exists()
    assert (tmp_path / "activation_scorecard.json").exists()
    assert (tmp_path / "package_verification.json").exists()
    assert (tmp_path / "compatibility_report.json").exists()
    assert (tmp_path / "lifecycle_controls.json").exists()
    assert (tmp_path / "explicit_state_store.json").exists()
    assert (tmp_path / "extension_scorecard.json").exists()
    explicit_state = json.loads((tmp_path / "explicit_state_store.json").read_text(encoding="utf-8"))
    assert "approval_nonces" in explicit_state
    assert "idempotency_results" in explicit_state
    assert explicit_state["approval_nonces"]
    assert explicit_state["idempotency_results"]
    compatibility = json.loads((tmp_path / "compatibility_report.json").read_text(encoding="utf-8"))
    assert compatibility["rc_opt_in"] is True
    assert compatibility["unsupported_features_fail_closed"] is True
    assert "package entrypoint layout" in compatibility["second_host_gaps"]
    lifecycle = json.loads((tmp_path / "lifecycle_controls.json").read_text(encoding="utf-8"))
    assert lifecycle["rolled_back"]["version"] == "1.0.0"
    assert lifecycle["revoked"]["status"] == "revoked"
