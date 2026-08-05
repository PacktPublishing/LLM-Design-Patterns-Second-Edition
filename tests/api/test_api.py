"""API tests for identity, health, and answer mapping."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from policyops.adapters.replay import ReplayModelClient
from policyops.api import create_app
from policyops.api.verification import run_foundation_verification
from policyops.capstone import CapstoneRuntime
from policyops.composition import AppContainer
from policyops.config import Settings
from policyops.deployment import DeploymentRuntime
from policyops.extensions import ExtensionRuntime
from policyops.harness import SessionRuntime
from policyops.orchestration import TriageRuntime
from policyops.telemetry import TelemetryRuntime
from policyops.services import AnswerService

FIXTURES = Path("labs/ch01/fixtures")
SNAPSHOT = Path("tests/api/openapi_snapshot.json")


def _container(fixture_pack: Path = FIXTURES) -> AppContainer:
    settings = Settings(
        profile="fixture",
        adapter="replay",
        fixture_pack=fixture_pack,
        lab_id="ch01",
    )
    replay = ReplayModelClient(fixture_pack)
    return AppContainer(
        settings=settings,
        client=replay,
        answer_service=AnswerService(replay),
    )


def _local_container(fixture_pack: Path = FIXTURES) -> AppContainer:
    from policyops.adapters.local import LocalModelClient

    settings = Settings(
        profile="local",
        adapter="local",
        fixture_pack=fixture_pack,
        lab_id="ch01",
        configuration_versions={"model": "local-v1", "policy": "policy-v1"},
    )
    client = LocalModelClient(fixture_pack)
    return AppContainer(
        settings=settings,
        client=client,
        answer_service=AnswerService(client),
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(_container())
    app.state.session_runtime = SessionRuntime(tmp_path / "runtime")
    app.state.triage_runtime = TriageRuntime(tmp_path / "triage-runtime")
    app.state.telemetry_runtime = TelemetryRuntime(tmp_path / "telemetry-runtime")
    app.state.extension_runtime = ExtensionRuntime(tmp_path / "extension-runtime")
    app.state.deployment_runtime = DeploymentRuntime(tmp_path / "deployment-runtime")
    app.state.capstone_runtime = CapstoneRuntime(tmp_path / "capstone-runtime")
    return TestClient(app)


def _headers(**extra: str) -> dict[str, str]:
    base = {
        "X-Tenant-Id": "tenant_alpha",
        "X-Actor-Id": "actor_reader",
        "X-Request-Id": "req_fixture_001",
        "X-Trace-Id": "trace_fixture_001",
        "Content-Type": "application/json",
    }
    base.update(extra)
    return base


def test_live(client: TestClient) -> None:
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "live"


def test_ready(client: TestClient) -> None:
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["configuration_id"].startswith("sha256:")


def test_startup_health_reports_ready(client: TestClient) -> None:
    r = client.get("/health/startup")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "policyops-api"
    assert body["startup"] == "ready"
    assert body["readiness"] == "ready"


def test_answer_success(client: TestClient) -> None:
    r = client.post(
        "/v1/answer",
        headers=_headers(),
        json={"question": "How many remote days are allowed?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]["citations"]
    assert body["trace_id"] == "trace_fixture_001"
    assert body["configuration_id"].startswith("sha256:")


def test_missing_identity_never_calls_model(client: TestClient) -> None:
    replay: ReplayModelClient = client.app.state.container.client  # type: ignore[attr-defined]
    before = replay.call_count
    r = client.post("/v1/answer", json={"question": "hi"})
    assert r.status_code == 401
    assert replay.call_count == before


def test_tenant_conflict_forbidden(client: TestClient) -> None:
    replay: ReplayModelClient = client.app.state.container.client  # type: ignore[attr-defined]
    before = replay.call_count
    r = client.post(
        "/v1/answer",
        headers=_headers(),
        json={"question": "hi", "tenant_id": "tenant_beta"},
    )
    assert r.status_code == 403
    assert replay.call_count == before


def test_actor_conflict_forbidden(client: TestClient) -> None:
    replay: ReplayModelClient = client.app.state.container.client  # type: ignore[attr-defined]
    before = replay.call_count
    r = client.post(
        "/v1/answer",
        headers=_headers(),
        json={"question": "hi", "actor_id": "actor_other"},
    )
    assert r.status_code == 403
    assert replay.call_count == before


def test_unsupported_content_type_rejected_before_model_call(client: TestClient) -> None:
    replay: ReplayModelClient = client.app.state.container.client  # type: ignore[attr-defined]
    before = replay.call_count
    r = client.post(
        "/v1/answer",
        headers={k: v for k, v in _headers().items() if k != "Content-Type"} | {"Content-Type": "text/plain"},
        content="question=hi",
    )
    assert r.status_code == 400
    assert r.json()["code"] == "VALIDATION_ERROR"
    assert replay.call_count == before


def test_openapi_has_answer_path(client: TestClient) -> None:
    schema = client.app.openapi()
    assert "/v1/answer" in schema["paths"]
    assert "/health/live" in schema["paths"]
    assert "/health/startup" in schema["paths"]
    assert "/v1/extensions" in schema["paths"]


def test_openapi_matches_snapshot(client: TestClient) -> None:
    """Guard the published contract surface against accidental drift.

    Regenerate intentionally with POLICYOPS_UPDATE_OPENAPI_SNAPSHOT=1.
    """
    schema = client.app.openapi()
    current = {
        "paths": sorted(schema["paths"].keys()),
        "schemas": sorted(schema["components"]["schemas"].keys()),
        "answer_post_responses": sorted(schema["paths"]["/v1/answer"]["post"]["responses"].keys()),
    }
    import os

    if os.environ.get("POLICYOPS_UPDATE_OPENAPI_SNAPSHOT") == "1":
        SNAPSHOT.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert current == expected


def test_insufficient_scope_forbidden_no_model_call(client: TestClient) -> None:
    replay: ReplayModelClient = client.app.state.container.client  # type: ignore[attr-defined]
    before = replay.call_count
    r = client.post(
        "/v1/answer",
        headers=_headers(**{"X-Authz-Scopes": "some:other"}),
        json={"question": "How many remote days are allowed?"},
    )
    assert r.status_code == 403
    body = r.json()
    assert body["code"] == "FORBIDDEN"
    assert "answer" not in body
    assert replay.call_count == before


def test_dependency_diagnostics_requires_operator_role(client: TestClient) -> None:
    forbidden = client.get("/diagnostics/dependencies", headers=_headers())
    assert forbidden.status_code == 403

    allowed = client.get(
        "/diagnostics/dependencies",
        headers=_headers(**{"X-Roles": "platform-engineer"}),
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload
    assert all("reason_code" in item and "bounded_detail" in item for item in payload)


def test_extension_lifecycle_routes_require_operator_role_and_mutate_state(client: TestClient) -> None:
    forbidden = client.get("/v1/extensions", headers=_headers())
    assert forbidden.status_code == 403

    allowed_headers = _headers(**{"X-Roles": "platform-engineer"})
    listed = client.get("/v1/extensions", headers=allowed_headers)
    assert listed.status_code == 200
    assert any(item["extension_id"] == "policyops-ticket-pack" for item in listed.json())

    disabled = client.post("/v1/extensions/policyops-ticket-pack:disable", headers=allowed_headers)
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"


def test_ready_returns_503_when_adapter_not_ready(tmp_path: Path) -> None:
    empty_pack = tmp_path / "empty_fixtures"
    empty_pack.mkdir()
    app = create_app(_container(empty_pack))
    client = TestClient(app)
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"


def test_answer_success_with_local_adapter(tmp_path: Path) -> None:
    app = create_app(_local_container())
    app.state.session_runtime = SessionRuntime(tmp_path / "runtime")
    app.state.triage_runtime = TriageRuntime(tmp_path / "triage-runtime")
    app.state.telemetry_runtime = TelemetryRuntime(tmp_path / "telemetry-runtime")
    client = TestClient(app)
    r = client.post(
        "/v1/answer",
        headers=_headers(),
        json={"question": "How many remote days are allowed?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]["text"].startswith("Employees may work remotely")
    assert body["usage"]["adapter"] == "local"


def test_foundation_verification_writes_measured_scorecard(tmp_path: Path) -> None:
    payload = run_foundation_verification(tmp_path)
    assert payload["gates_passed"] is True
    assert (tmp_path / "foundation_scorecard.json").exists()
    assert (tmp_path / "request_report.json").exists()
    scorecard = json.loads((tmp_path / "foundation_scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["zero_model_call_rejections"] == 2
    assert scorecard["p95_latency_ms"] >= scorecard["p50_latency_ms"] >= 1
    assert "http.request" in scorecard["required_spans_present"]
    assert scorecard["redaction_safe"] is True


def test_triage_run_create_inspect_and_idempotency(client: TestClient) -> None:
    created = client.post(
        "/v1/triage/runs",
        headers=_headers(),
        json={
            "scenario_id": "policy-triage-default",
            "variant": "orchestrator_worker",
            "idempotency_key": "triage-api-1",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["run"]["variant"] == "orchestrator_worker"
    assert body["delegated_tasks"]
    assert body["worker_results"]
    assert body["available_controls"] == []

    second = client.post(
        "/v1/triage/runs",
        headers=_headers(),
        json={
            "scenario_id": "policy-triage-default",
            "variant": "orchestrator_worker",
            "idempotency_key": "triage-api-1",
        },
    )
    assert second.status_code == 200
    assert second.json()["run"]["run_id"] == body["run"]["run_id"]

    inspect = client.get(f"/v1/triage/runs/{body['run']['run_id']}", headers=_headers())
    assert inspect.status_code == 200
    assert inspect.json()["run"]["run_id"] == body["run"]["run_id"]


def test_triage_pause_resume_cancel_routes(client: TestClient) -> None:
    created = client.post(
        "/v1/triage/runs",
        headers=_headers(),
        json={
            "scenario_id": "policy-triage-default",
            "variant": "orchestrator_worker",
            "budget": {"worker_limit": 1},
        },
    )
    assert created.status_code == 200
    run = created.json()["run"]
    run_id = run["run_id"]
    paused = client.post(
        f"/v1/triage/runs/{run_id}:pause",
        headers=_headers(),
        json={"expected_version": run["version"]},
    )
    assert paused.status_code == 200
    assert paused.json()["run"]["status"] == "paused"

    resumed = client.post(
        f"/v1/triage/runs/{run_id}:resume",
        headers=_headers(),
        json={"expected_version": paused.json()['run']['version']},
    )
    assert resumed.status_code == 200
    assert resumed.json()["run"]["status"] == "awaiting_review"

    cancelled = client.post(
        f"/v1/triage/runs/{run_id}:cancel",
        headers=_headers(),
        json={"expected_version": resumed.json()['run']['version']},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["run"]["status"] == "cancelled"


def test_ticket_preview_execute_and_run_inspect_routes(client: TestClient) -> None:
    ticket = {
        "tenant_id": "tenant_alpha",
        "title": "Remote-work exception support",
        "description": "Create a policy support ticket for a manager-approved remote-work exception.",
        "severity": "medium",
        "source_refs": ["policy_remote:v2:span_remote_approval"],
    }
    preview = client.post(
        "/v1/tickets/preview",
        headers=_headers(),
        json={"ticket": ticket},
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["result"]["status"] == "preview"
    assert preview_body["result"]["ticket_id"] is None

    execute = client.post(
        "/v1/tickets/execute",
        headers=_headers(),
        json={
            "ticket": ticket,
            "preview": preview_body["preview"],
            "idempotency_key": "ticket-api-1",
        },
    )
    assert execute.status_code == 200
    execute_body = execute.json()
    assert execute_body["result"]["status"] == "created"
    assert execute_body["result"]["ticket_id"].startswith("ticket_")
    assert execute_body["run"]["status"] == "executed"

    inspect = client.get(f"/v1/runs/{execute_body['run']['run_id']}", headers=_headers())
    assert inspect.status_code == 200
    assert inspect.json()["ticket_id"] == execute_body["result"]["ticket_id"]

    replay = client.post(
        "/v1/tickets/execute",
        headers=_headers(),
        json={
            "ticket": ticket,
            "preview": preview_body["preview"],
            "idempotency_key": "ticket-api-1",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["run"]["run_id"] == execute_body["run"]["run_id"]
    assert replay.json()["result"]["ticket_id"] == execute_body["result"]["ticket_id"]


def test_ticket_execute_conflict_returns_409(client: TestClient) -> None:
    preview = client.post(
        "/v1/tickets/preview",
        headers=_headers(),
        json={
            "ticket": {
                "tenant_id": "tenant_alpha",
                "title": "Remote-work exception support",
                "description": "Create a policy support ticket for a manager-approved remote-work exception.",
                "severity": "medium",
                "source_refs": ["policy_remote:v2:span_remote_approval"],
            }
        },
    )
    preview_body = preview.json()
    conflict = client.post(
        "/v1/tickets/execute",
        headers=_headers(),
        json={
            "ticket": {
                "tenant_id": "tenant_alpha",
                "title": "Changed request title",
                "description": "Create a policy support ticket for a manager-approved remote-work exception.",
                "severity": "medium",
                "source_refs": ["policy_remote:v2:span_remote_approval"],
            },
            "preview": preview_body["preview"],
            "idempotency_key": "ticket-api-conflict",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "CONFLICT"


def test_memory_routes_support_export_correct_and_delete(client: TestClient) -> None:
    exported = client.get("/v1/memory", headers=_headers())
    assert exported.status_code == 200
    records = exported.json()["records"]
    assert records
    record = records[0]

    corrected = client.post(
        "/v1/memory/correct",
        headers=_headers(),
        json={
            "record_id": record["record_id"],
            "expected_version": record["version"],
            "text": "Corrected memory text for chapter 16 runtime coverage.",
        },
    )
    assert corrected.status_code == 200
    corrected_body = corrected.json()
    assert corrected_body["correction"]["supersedes"] == record["record_id"]

    deleted = client.post(
        "/v1/memory/delete",
        headers=_headers(),
        json={
            "record_id": corrected_body["correction"]["record_id"],
            "expected_version": corrected_body["correction"]["version"],
        },
    )
    assert deleted.status_code == 200
    deleted_body = deleted.json()
    assert deleted_body["deletion_receipt"]["record_ids"]
    assert deleted_body["rights_receipt"]["complete"] is True


def test_triage_state_version_conflict_returns_409(client: TestClient) -> None:
    created = client.post(
        "/v1/triage/runs",
        headers=_headers(),
        json={"variant": "workflow"},
    )
    run_id = created.json()["run"]["run_id"]
    conflict = client.post(
        f"/v1/triage/runs/{run_id}:pause",
        headers=_headers(),
        json={"expected_version": 999},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "CONFLICT"


def test_operation_inspect_and_adjudication_routes(client: TestClient) -> None:
    operation = client.get(
        "/operations/corr-policyops-1201",
        headers=_headers(),
    )
    assert operation.status_code == 200
    payload = operation.json()
    assert payload["correlation_id"] == "corr-policyops-1201"
    assert payload["spans"]
    assert payload["artifacts"]["artifacts"]

    adjudication = client.post(
        "/adjudications",
        headers=_headers(),
        json={
            "correlation_id": "corr-policyops-1201",
            "failure_class": "product_failure",
            "expert_role": "policy operations lead",
            "expected_behavior": "Answer should cite the current reimbursement policy and ask for approval before creating a ticket.",
        },
    )
    assert adjudication.status_code == 200
    body = adjudication.json()
    assert body["adjudication"]["may_graduate"] is True
    assert body["evaluation_case"]["source_correlation_id"] == "corr-policyops-1201"


def test_operation_tenant_mismatch_forbidden(client: TestClient) -> None:
    mismatch = client.get(
        "/operations/corr-policyops-1201",
        headers=_headers(**{"X-Tenant-Id": "tenant_beta"}),
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["code"] == "FORBIDDEN"


def test_experiment_and_canary_stop_routes(client: TestClient) -> None:
    experiment = client.post(
        "/experiments",
        headers=_headers(),
        json={"candidate_profile": "accepted"},
    )
    assert experiment.status_code == 200
    body = experiment.json()
    assert body["ledger"]["decision"] == "keep"
    assert body["active_canary_id"] == "canary-ch12-active"

    stopped = client.post(
        "/canaries/canary-ch12-active/stop",
        headers=_headers(),
        json={"reason": "operator stopped canary"},
    )
    assert stopped.status_code == 200
    report = stopped.json()
    assert report["decision"] == "rollback"
    assert report["rollback_reason"] == "operator stopped canary"


def test_session_run_inspect_and_checkpoint_routes(client: TestClient) -> None:
    run = client.post(
        "/v1/sessions/session-api-1/run",
        headers=_headers(),
        json={"expected_version": 0, "owner_id": "worker-a", "fault": "before_effect"},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["session"]["session_id"] == "session-api-1"
    assert body["session"]["state"] == "action_ready"
    inspect = client.get("/v1/sessions/session-api-1", headers=_headers())
    assert inspect.status_code == 200
    assert inspect.json()["session"]["version"] >= 4
    events = client.get("/v1/sessions/session-api-1/events", headers=_headers())
    assert events.status_code == 200
    assert len(events.json()) >= 4
    checkpoint = client.get("/v1/sessions/session-api-1/checkpoint", headers=_headers())
    assert checkpoint.status_code == 200
    assert checkpoint.json() is None


def test_session_resume_completes_pending_effect(client: TestClient) -> None:
    client.post(
        "/v1/sessions/session-api-2/run",
        headers=_headers(),
        json={"expected_version": 0, "fault": "after_effect_before_ack"},
    )
    resume = client.post(
        "/v1/sessions/session-api-2/resume",
        headers=_headers(),
        json={"expected_version": 4, "owner_id": "worker-b"},
    )
    assert resume.status_code == 200
    body = resume.json()
    assert body["session"]["state"] == "verified"
    assert len(body["receipts"]) == 1
    checkpoint = client.get("/v1/sessions/session-api-2/checkpoint", headers=_headers())
    assert checkpoint.status_code == 200
    assert checkpoint.json()["state"]["state"] == "effect_delivered"


def test_session_conflict_returns_typed_409(client: TestClient) -> None:
    client.post(
        "/v1/sessions/session-api-3/run",
        headers=_headers(),
        json={"expected_version": 0, "fault": "before_effect"},
    )
    conflict = client.post(
        "/v1/sessions/session-api-3/resume",
        headers=_headers(),
        json={"expected_version": 999, "owner_id": "worker-b"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "CONFLICT"


def test_session_cancel_stops_future_reconcile(client: TestClient) -> None:
    client.post(
        "/v1/sessions/session-api-4/run",
        headers=_headers(),
        json={"expected_version": 0, "fault": "before_effect"},
    )
    cancel = client.post(
        "/v1/sessions/session-api-4/cancel",
        headers=_headers(),
        json={"expected_version": 4, "owner_id": "operator-a"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["session"]["state"] == "cancelled"
