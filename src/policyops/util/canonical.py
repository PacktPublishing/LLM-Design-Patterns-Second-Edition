"""Canonical JSON and fake-clock helpers for deterministic evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


_FAKE_NOW = datetime(2030, 1, 1, 0, 0, 0, tzinfo=UTC)


def fake_now() -> datetime:
    return _FAKE_NOW


def canonical_json(data: Any) -> str:
    """Byte-stable JSON: sorted keys, no whitespace, UTC datetimes as Z."""

    def default(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        raise TypeError(f"Object of type {type(obj)!r} is not JSON serializable")

    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=default)
