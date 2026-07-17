"""Answer application service — deadline, model call, fail-closed validation."""

from __future__ import annotations

from datetime import UTC, datetime

from policyops.contracts import (
    AnswerResponse,
    DomainError,
    ErrorCode,
    ModelRequest,
    RetryClass,
    RunContext,
)
from policyops.contracts.ports import ModelClient
from policyops.telemetry import span


class AnswerService:
    def __init__(self, client: ModelClient) -> None:
        self.client = client

    async def answer(self, request: ModelRequest, context: RunContext) -> AnswerResponse:
        with span(
            "policyops.answer",
            {
                "tenant_id": context.tenant_id,
                "actor_id": context.actor_id,
                "trace_id": context.trace_id,
                "request_id": context.request_id,
                "configuration_id": context.configuration_id,
            },
        ):
            now = datetime.now(UTC)
            if context.deadline_at <= now:
                raise DomainError(
                    ErrorCode.DEADLINE_EXCEEDED,
                    "request deadline already exceeded",
                    retry_class=RetryClass.CALLER,
                    http_status=503,
                    trace_id=context.trace_id,
                    request_id=context.request_id,
                )

            with span(
                "model.generate",
                {
                    "trace_id": context.trace_id,
                    "request_id": context.request_id,
                    "adapter": getattr(self.client, "__class__", type(self.client)).__name__,
                },
            ):
                result = await self.client.generate(request, context)

            with span("answer.validate", {"trace_id": context.trace_id}):
                if result.kind == "failure":
                    failure = result.failure
                    status = {
                        ErrorCode.DEADLINE_EXCEEDED: 503,
                        ErrorCode.MODEL_CAPACITY: 503,
                        ErrorCode.MODEL_BAD_OUTPUT: 502,
                        ErrorCode.CONFIG_INVALID: 503,
                    }.get(failure.code, 502)
                    raise DomainError(
                        failure.code,
                        failure.message,
                        retry_class=failure.retry_class,
                        http_status=status,
                        trace_id=context.trace_id,
                        request_id=context.request_id,
                    )

                # Re-validate success payload (fail closed).
                answer = result.answer
                usage = result.usage
                return AnswerResponse(
                    answer=answer,
                    usage=usage,
                    trace_id=context.trace_id,
                    configuration_id=context.configuration_id,
                    request_id=context.request_id,
                )
