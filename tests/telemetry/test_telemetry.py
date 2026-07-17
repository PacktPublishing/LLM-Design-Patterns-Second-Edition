"""Telemetry redaction tests — only allow-listed attributes are recorded."""

from __future__ import annotations

from policyops.telemetry import ALLOWED_ATTRS, clear_spans, recorded_spans, span


def test_span_redacts_non_allowlisted_attributes() -> None:
    clear_spans()
    with span(
        "policyops.answer",
        {
            "tenant_id": "tenant_alpha",
            "actor_id": "actor_reader",
            "authorization_token": "sk-should-not-appear",
            "question": "raw user content that must not leak",
        },
    ):
        pass
    spans = [s for s in recorded_spans() if s["name"] == "policyops.answer"]
    assert spans, "expected the policyops.answer span to be recorded"
    attrs = spans[-1]["attributes"]
    assert attrs.get("tenant_id") == "tenant_alpha"
    assert "authorization_token" not in attrs
    assert "question" not in attrs
    assert set(attrs).issubset(ALLOWED_ATTRS)
