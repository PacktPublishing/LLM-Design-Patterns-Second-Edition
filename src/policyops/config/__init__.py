"""Configuration loading, validation, and non-secret fingerprinting."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from policyops.contracts import DomainError, ErrorCode, RetryClass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLICYOPS_", extra="ignore")

    profile: Literal["fixture", "local"] = "fixture"
    adapter: Literal["replay", "local"] = "replay"
    host: str = "127.0.0.1"
    port: int = 8080
    fixture_pack: Path = Path("labs/ch01/fixtures")
    fault_scenario: str | None = None
    require_secure_config: bool = False
    lab_id: str = "ch01"
    configuration_versions: dict[str, str] = Field(
        default_factory=lambda: {"model": "replay-v1", "policy": "policy-v1"}
    )

    def fingerprint(self) -> str:
        payload = {
            "profile": self.profile,
            "adapter": self.adapter,
            "lab_id": self.lab_id,
            "configuration_versions": dict(sorted(self.configuration_versions.items())),
            "fixture_pack": str(self.fixture_pack).replace("\\", "/"),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f"sha256:{digest}"


def load_settings() -> Settings:
    settings = Settings()
    if settings.require_secure_config:
        # Fail closed when secure mode is requested but secrets are missing.
        if not os.environ.get("POLICYOPS_RUNTIME_TOKEN"):
            raise DomainError(
                ErrorCode.CONFIG_INVALID,
                "secure configuration requires POLICYOPS_RUNTIME_TOKEN",
                retry_class=RetryClass.CONFIG,
                http_status=503,
            )
    if settings.adapter == "replay" and not settings.fixture_pack.exists():
        raise DomainError(
            ErrorCode.CONFIG_INVALID,
            f"fixture pack missing: {settings.fixture_pack}",
            retry_class=RetryClass.CONFIG,
            http_status=503,
        )
    return settings
