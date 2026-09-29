"""Measured Chapter 1 foundation verification."""

from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import median
from typing import Any

from fastapi.testclient import TestClient

from policyops.adapters.replay import ReplayModelClient
from policyops.api import create_app
from policyops.composition import AppContainer
from policyops.config import Settings
from policyops.services import AnswerService
from policyops.telemetry import ALLOWED_ATTRS, clear_spans, recorded_spans

HEADERS = {
    "X-Tenant-Id": "tenant_alpha",
    "X-Actor-Id": "actor_reader",
    "X-Request-Id": "req_fixture_001",
    "X-Trace-Id": "trace_fixture_001",
    "Content-Type": "application/json",
}
FORBIDDEN_ATTRS = {"prompt", "question", "answer_text", "authorization_token"}


def _container(*, fixture_pack: Path, fault_scenario: str | None = None) -> tuple[AppContainer, ReplayModelClient]:
    settings = Settings(
        profile="fixture",
        adapter="replay",
        fixture_pack=fixture_pack,
        fault_scenario=fault_scenario,
        lab_id="ch01",
    )
    replay = ReplayModelClient(fixture_pack, fault_scenario=fault_scenario)
    return (
        AppContainer(
            settings=settings,
            client=replay,
            answer_service=AnswerService(replay),
        ),
        replay,
    )


def _request_scenario(
    name: str,
    *,
    fixture_pack: Path,
    method: str,
    path: str,
    fault_scenario: str | None = None,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    container, replay = _container(fixture_pack=fixture_pack, fault_scenario=fault_scenario)
    client = TestClient(create_app(container))
    clear_spans()
    before = replay.call_count
    started = time.perf_counter_ns()
    response = client.request(method, path, headers=headers, json=json_body)
    elapsed_ms = max(1, int((time.perf_counter_ns() - started) / 1_000_000))
    spans = recorded_spans()
    return {
        "scenario": name,
        "status_code": response.status_code,
        "code": response.json().get("code") if "application/json" in response.headers.get("content-type", "") else None,
        "latency_ms": elapsed_ms,
        "model_calls": replay.call_count - before,
        "spans": spans,
        "body": response.json() if "application/json" in response.headers.get("content-type", "") else None,
    }


def run_foundation_verification(evidence_dir: Path, fixture_pack: Path | None = None) -> dict[str, Any]:
    fixture_pack = fixture_pack or Path("labs/ch01/fixtures")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    success = _request_scenario(
        "answer_success",
        fixture_pack=fixture_pack,
        method="POST",
        path="/v1/answer",
        headers=HEADERS,
        json_body={"question": "How many remote days are allowed?"},
    )
    missing_identity = _request_scenario(
        "missing_identity",
        fixture_pack=fixture_pack,
        method="POST",
        path="/v1/answer",
        headers={"Content-Type": "application/json"},
        json_body={"question": "How many remote days are allowed?"},
    )
    tenant_conflict = _request_scenario(
        "tenant_conflict",
        fixture_pack=fixture_pack,
        method="POST",
        path="/v1/answer",
        headers=HEADERS,
        json_body={"question": "How many remote days are allowed?", "tenant_id": "tenant_beta"},
    )
    invalid_json = _request_scenario(
        "invalid_json",
        fixture_pack=fixture_pack,
        method="POST",
        path="/v1/answer",
        fault_scenario="invalid_json",
        headers=HEADERS,
        json_body={"question": "boom"},
    )
    timeout = _request_scenario(
        "timeout",
        fixture_pack=fixture_pack,
        method="POST",
        path="/v1/answer",
        fault_scenario="timeout",
        headers=HEADERS,
        json_body={"question": "boom"},
    )
    upstream = _request_scenario(
        "upstream_error",
        fixture_pack=fixture_pack,
        method="POST",
        path="/v1/answer",
        fault_scenario="upstream_error",
        headers=HEADERS,
        json_body={"question": "boom"},
    )
    live = _request_scenario(
        "health_live",
        fixture_pack=fixture_pack,
        method="GET",
        path="/health/live",
    )
    ready = _request_scenario(
        "health_ready",
        fixture_pack=fixture_pack,
        method="GET",
        path="/health/ready",
    )
    scenarios = [success, missing_identity, tenant_conflict, invalid_json, timeout, upstream, live, ready]
    request_report = {
        "scenarios": scenarios,
        "error_classification": {
            f"{scenario['status_code']}:{scenario['code'] or 'ok'}": sum(
                1
                for candidate in scenarios
                if candidate["status_code"] == scenario["status_code"] and (candidate["code"] or "ok") == (scenario["code"] or "ok")
            )
            for scenario in scenarios
            if scenario["status_code"] >= 400
        },
    }
    latencies = [scenario["latency_ms"] for scenario in scenarios if scenario["scenario"] in {"answer_success", "invalid_json", "timeout", "upstream_error"}]
    success_span_names = {span["name"] for span in success["spans"]}
    required_spans = {"http.request", "policyops.answer", "model.generate", "answer.validate"}
    trace_payload = {
        "sample_spans": success["spans"],
        "required_spans": sorted(required_spans),
        "required_spans_present": sorted(required_spans & success_span_names),
        "allowed_attributes": sorted(ALLOWED_ATTRS),
        "forbidden_attributes": sorted(FORBIDDEN_ATTRS),
        "redaction_safe": all(
            set(span.get("attributes", {}).keys()).issubset(ALLOWED_ATTRS)
            and not (set(span.get("attributes", {}).keys()) & FORBIDDEN_ATTRS)
            for span in success["spans"]
        ),
    }
    zero_model_call_rejections = sum(
        1 for scenario in (missing_identity, tenant_conflict) if scenario["model_calls"] == 0
    )
    scorecard = {
        "lab": "ch01",
        "profile": "fixture",
        "configuration_id": ready["body"]["configuration_id"],
        "fixture_pack_hash": _container(fixture_pack=fixture_pack)[1].fixture_pack_hash(),
        "request_count": len(scenarios),
        "p50_latency_ms": median(latencies),
        "p95_latency_ms": max(latencies),
        "error_classification": request_report["error_classification"],
        "zero_model_call_rejections": zero_model_call_rejections,
        "required_spans_present": trace_payload["required_spans_present"],
        "redaction_safe": trace_payload["redaction_safe"],
        "note": "Fixture latency is verification evidence, not provider performance.",
    }
    scorecard["gates_passed"] = (
        success["status_code"] == 200
        and live["status_code"] == 200
        and ready["status_code"] == 200
        and missing_identity["status_code"] == 401
        and tenant_conflict["status_code"] == 403
        and invalid_json["status_code"] == 502
        and timeout["status_code"] == 503
        and upstream["status_code"] == 503
        and zero_model_call_rejections == 2
        and trace_payload["redaction_safe"]
        and required_spans.issubset(success_span_names)
    )
    (evidence_dir / "request_report.json").write_text(json.dumps(request_report, indent=2), encoding="utf-8")
    (evidence_dir / "foundation_scorecard.json").write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    return {"gates_passed": scorecard["gates_passed"], "scorecard": scorecard, "trace_redaction": trace_payload}
