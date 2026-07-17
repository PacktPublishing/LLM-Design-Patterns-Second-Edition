"""Canonical JSON and fake-clock determinism tests."""

from __future__ import annotations

from datetime import UTC, datetime

from policyops.util import canonical_json, fake_now


def test_canonical_json_is_key_order_stable() -> None:
    a = canonical_json({"b": 1, "a": 2, "c": {"y": 1, "x": 2}})
    b = canonical_json({"c": {"x": 2, "y": 1}, "a": 2, "b": 1})
    assert a == b
    assert a == '{"a":2,"b":1,"c":{"x":2,"y":1}}'


def test_canonical_json_serializes_datetime_as_utc_z() -> None:
    ts = datetime(2030, 1, 1, 12, 30, 0, tzinfo=UTC)
    assert canonical_json({"at": ts}) == '{"at":"2030-01-01T12:30:00Z"}'


def test_fake_now_is_fixed() -> None:
    assert fake_now() == fake_now()
    assert fake_now().tzinfo is not None
    assert fake_now().year == 2030
