"""Deterministic replay ModelClient — mandatory fixture profile."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from policyops.contracts import (
    Answer,
    ErrorCode,
    ModelFailure,
    ModelFailureResult,
    ModelRequest,
    ModelResult,
    ModelSuccess,
    RetryClass,
    RunContext,
    Usage,
)
from policyops.util import fake_now


class ReplayModelClient:
    """Resolves (scenario_id, configuration_id) to fixture JSON. Never networks."""

    def __init__(
        self,
        fixture_pack: Path,
        *,
        fault_scenario: str | None = None,
        configuration_id: str | None = None,
    ) -> None:
        self.fixture_pack = Path(fixture_pack)
        self.fault_scenario = fault_scenario
        self.configuration_id = configuration_id
        self._scenarios = self._load_scenarios()
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def _load_scenarios(self) -> dict[str, Any]:
        path = self.fixture_pack / "replay" / "scenarios.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def fixture_pack_hash(self) -> str:
        digest = hashlib.sha256()
        root = self.fixture_pack
        if not root.exists():
            return "sha256:" + ("0" * 64)
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            digest.update(str(path.relative_to(root)).replace("\\", "/").encode())
            digest.update(path.read_bytes())
        return f"sha256:{digest.hexdigest()}"

    async def ready(self) -> bool:
        return bool(self._scenarios) and (self.fixture_pack / "replay" / "scenarios.json").exists()

    async def generate(self, request: ModelRequest, context: RunContext) -> ModelResult:
        self._call_count += 1
        if self.configuration_id and context.configuration_id != self.configuration_id:
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.CONFIG_INVALID,
                    retry_class=RetryClass.CONFIG,
                    message="configuration fingerprint does not match replay fixture binding",
                    correlation_token=context.request_id,
                )
            )
        scenario_id = self.fault_scenario or self._select_scenario(request, context)
        scenario = self._scenarios.get(scenario_id)
        if scenario is None:
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.MODEL_CAPACITY,
                    retry_class=RetryClass.UPSTREAM,
                    message="replay scenario unavailable",
                    correlation_token=context.request_id,
                )
            )

        kind = scenario.get("kind", "success")
        if kind == "timeout":
            delay_ms = int(scenario.get("delay_ms", 50))
            remaining_ms = int((context.deadline_at - fake_now()).total_seconds() * 1000)
            if remaining_ms <= 0 or delay_ms > remaining_ms:
                return ModelFailureResult(
                    failure=ModelFailure(
                        code=ErrorCode.DEADLINE_EXCEEDED,
                        retry_class=RetryClass.CALLER,
                        message="adapter deadline exceeded",
                        correlation_token=context.request_id,
                    )
                )
            await asyncio.sleep(delay_ms / 1000)
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.DEADLINE_EXCEEDED,
                    retry_class=RetryClass.CALLER,
                    message="adapter deadline exceeded",
                    correlation_token=context.request_id,
                )
            )
        if kind == "upstream_error":
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.MODEL_CAPACITY,
                    retry_class=RetryClass.UPSTREAM,
                    message="upstream capacity exhausted",
                    correlation_token=context.request_id,
                )
            )
        if kind in {"invalid_json", "schema_invalid"}:
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.MODEL_BAD_OUTPUT,
                    retry_class=RetryClass.NONE,
                    message=(
                        "adapter returned malformed JSON"
                        if kind == "invalid_json"
                        else "adapter returned schema-invalid output"
                    ),
                    correlation_token=context.request_id,
                )
            )

        payload = scenario["answer"]
        usage_payload = scenario.get(
            "usage",
            {"input_tokens": 12, "output_tokens": 40, "adapter": "replay"},
        )
        try:
            answer = Answer.model_validate(payload)
            usage = Usage.model_validate(usage_payload)
        except Exception:
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.MODEL_BAD_OUTPUT,
                    retry_class=RetryClass.NONE,
                    message="adapter output failed validation",
                    correlation_token=context.request_id,
                )
            )
        return ModelSuccess(answer=answer, usage=usage)

    def _select_scenario(self, request: ModelRequest, context: RunContext) -> str:
        mapping = self._scenarios.get("_routing", {})
        if isinstance(mapping, dict):
            if request.question in mapping:
                return mapping[request.question]
            if context.idempotency_key and context.idempotency_key in mapping:
                return mapping[context.idempotency_key]
        return "success_basic"
