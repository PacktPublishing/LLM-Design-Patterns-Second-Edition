"""Optional local-model adapter backed by a local subprocess runtime."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
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


class LocalModelClient:
    """Translate domain contracts to a local process and back again.

    This adapter stays provider-neutral at the application boundary while using
    a small local runtime process as its execution seam. The runtime is bundled
    with the repository so the adapter remains offline and reproducible.
    """

    def __init__(self, fixture_pack: Path, *, fault_scenario: str | None = None) -> None:
        self.fixture_pack = Path(fixture_pack)
        self.fault_scenario = fault_scenario
        runtime_script = Path(__file__).with_name("runtime.py")
        self._runner = [
            sys.executable,
            str(runtime_script),
            "--policy-root",
            str(self.fixture_pack / "policy"),
        ]

    async def ready(self) -> bool:
        if not (self.fixture_pack / "policy").exists():
            return False
        completed = await asyncio.to_thread(
            subprocess.run,
            [*self._runner, "--health"],
            capture_output=True,
            text=True,
        )
        return completed.returncode == 0 and completed.stdout.strip() == "ok"

    async def generate(self, request: ModelRequest, context: RunContext) -> ModelResult:
        if self.fault_scenario == "timeout":
            return await self._timeout_failure(context)

        payload = {
            "request": request.model_dump(mode="json"),
            "context": context.model_dump(mode="json"),
            "fault_scenario": self.fault_scenario,
        }
        try:
            raw = await self._invoke_runtime(payload, context)
        except TimeoutError:
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.DEADLINE_EXCEEDED,
                    retry_class=RetryClass.CALLER,
                    message="local adapter deadline exceeded",
                    correlation_token=context.request_id,
                )
            )
        except OSError:
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.MODEL_CAPACITY,
                    retry_class=RetryClass.UPSTREAM,
                    message="local runtime unavailable",
                    correlation_token=context.request_id,
                )
            )

        try:
            response = json.loads(raw)
        except json.JSONDecodeError:
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.MODEL_BAD_OUTPUT,
                    retry_class=RetryClass.NONE,
                    message="local runtime returned malformed JSON",
                    correlation_token=context.request_id,
                )
            )

        kind = response.get("kind")
        if kind == "failure":
            try:
                failure = ModelFailure.model_validate(response["failure"])
            except Exception:
                return ModelFailureResult(
                    failure=ModelFailure(
                        code=ErrorCode.MODEL_BAD_OUTPUT,
                        retry_class=RetryClass.NONE,
                        message="local runtime returned invalid failure payload",
                        correlation_token=context.request_id,
                    )
                )
            return ModelFailureResult(failure=failure)

        try:
            answer = Answer.model_validate(response["answer"])
            usage = Usage.model_validate(response["usage"])
        except Exception:
            return ModelFailureResult(
                failure=ModelFailure(
                    code=ErrorCode.MODEL_BAD_OUTPUT,
                    retry_class=RetryClass.NONE,
                    message="local runtime returned schema-invalid output",
                    correlation_token=context.request_id,
                )
            )
        usage.adapter = "local"
        return ModelSuccess(answer=answer, usage=usage)

    async def _invoke_runtime(self, payload: dict[str, Any], context: RunContext) -> str:
        remaining = max(
            0.01,
            (context.deadline_at.astimezone(UTC) - datetime.now(UTC)).total_seconds(),
        )
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                self._runner,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("local runtime timed out") from exc
        if completed.returncode != 0:
            return json.dumps(
                {
                    "kind": "failure",
                    "failure": {
                        "schema_version": "1.0",
                        "code": ErrorCode.MODEL_CAPACITY.value,
                        "retry_class": RetryClass.UPSTREAM.value,
                        "message": "local runtime process failed",
                        "correlation_token": context.request_id,
                    },
                }
            )
        return completed.stdout

    async def _timeout_failure(self, context: RunContext) -> ModelResult:
        await asyncio.sleep(0)
        return ModelFailureResult(
            failure=ModelFailure(
                code=ErrorCode.DEADLINE_EXCEEDED,
                retry_class=RetryClass.CALLER,
                message="local adapter deadline exceeded",
                correlation_token=context.request_id,
            )
        )
