"""Fault drills — typed fail-closed errors."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from policyops.adapters.replay import ReplayModelClient
from policyops.api import create_app
from policyops.composition import AppContainer
from policyops.config import Settings
from policyops.services import AnswerService

FIXTURES = Path("labs/ch01/fixtures")


def _client(fault: str) -> TestClient:
    settings = Settings(
        profile="fixture",
        adapter="replay",
        fixture_pack=FIXTURES,
        fault_scenario=fault,
        lab_id="ch01",
    )
    replay = ReplayModelClient(FIXTURES, fault_scenario=fault)
    container = AppContainer(
        settings=settings,
        client=replay,
        answer_service=AnswerService(replay),
    )
    return TestClient(create_app(container))


HEADERS = {
    "X-Tenant-Id": "tenant_alpha",
    "X-Actor-Id": "actor_reader",
    "Content-Type": "application/json",
}


@pytest.mark.parametrize(
    ("fault", "status", "code"),
    [
        ("timeout", 503, "DEADLINE_EXCEEDED"),
        ("invalid_json", 502, "MODEL_BAD_OUTPUT"),
        ("schema_invalid", 502, "MODEL_BAD_OUTPUT"),
        ("upstream_error", 503, "MODEL_CAPACITY"),
    ],
)
def test_fault_scenarios(fault: str, status: int, code: str) -> None:
    client = _client(fault)
    r = client.post("/v1/answer", headers=HEADERS, json={"question": "boom"})
    assert r.status_code == status
    body = r.json()
    assert body["code"] == code
    assert "answer" not in body
