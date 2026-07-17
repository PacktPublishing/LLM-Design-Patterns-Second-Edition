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


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(_container()))


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
