"""API tests for identity, health, and answer mapping."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from policyops.adapters.replay import ReplayModelClient
from policyops.api import create_app
from policyops.composition import AppContainer
from policyops.config import Settings
from policyops.harness import SessionRuntime
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
