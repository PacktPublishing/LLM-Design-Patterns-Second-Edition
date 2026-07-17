"""Configuration fail-closed and fingerprint tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from policyops.config import Settings, load_settings
from policyops.contracts import DomainError


def test_secure_config_fails_closed_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLICYOPS_REQUIRE_SECURE_CONFIG", "true")
    monkeypatch.delenv("POLICYOPS_RUNTIME_TOKEN", raising=False)
    with pytest.raises(DomainError) as exc:
        load_settings()
    assert exc.value.code.value == "CONFIG_INVALID"
    assert exc.value.http_status == 503


def test_missing_fixture_pack_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "nope"
    monkeypatch.setenv("POLICYOPS_ADAPTER", "replay")
    monkeypatch.setenv("POLICYOPS_FIXTURE_PACK", str(missing))
    monkeypatch.delenv("POLICYOPS_REQUIRE_SECURE_CONFIG", raising=False)
    with pytest.raises(DomainError) as exc:
        load_settings()
    assert exc.value.code.value == "CONFIG_INVALID"


def test_fingerprint_is_deterministic_and_secret_free() -> None:
    s1 = Settings(fixture_pack=Path("labs/ch01/fixtures"))
    s2 = Settings(fixture_pack=Path("labs/ch01/fixtures"))
    fp = s1.fingerprint()
    assert fp == s2.fingerprint()
    assert fp.startswith("sha256:")
    # Fingerprint hashes only non-secret keys; a runtime token must not appear.
    assert "RUNTIME_TOKEN" not in fp
    assert "sk-" not in fp


def test_fingerprint_changes_with_configuration_versions() -> None:
    base = Settings(fixture_pack=Path("labs/ch01/fixtures"))
    bumped = Settings(
        fixture_pack=Path("labs/ch01/fixtures"),
        configuration_versions={"model": "replay-v2", "policy": "policy-v1"},
    )
    assert base.fingerprint() != bumped.fingerprint()
