"""FastAPI boundary — identity headers, answer + health routes."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from policyops.composition import AppContainer, build_container
from policyops.contracts import (
    AnswerResponse,
    AuthorizationContext,
    Budget,
    DomainError,
    ErrorCode,
    ModelRequest,
    RetryClass,
    RunContext,
)
from policyops.telemetry import setup_telemetry, span
from policyops.util import fake_now


def create_app(container: AppContainer | None = None) -> FastAPI:
    setup_telemetry()
    application = FastAPI(title="PolicyOps", version="0.1.0")
    application.state.container = container or build_container()

    @application.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_problem().model_dump())

    @application.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        problem = DomainError(
            ErrorCode.VALIDATION_ERROR,
            "request validation failed",
            retry_class=RetryClass.NONE,
            http_status=400,
        ).to_problem()
        payload = problem.model_dump()
        payload["details"] = {"errors": json.loads(json.dumps(exc.errors(), default=str))}
        return JSONResponse(status_code=400, content=payload)

    @application.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @application.get("/health/ready")
    async def ready(request: Request) -> Response:
        c: AppContainer = request.app.state.container
        settings = c.settings
        try:
            ok = await c.client.ready()
        except Exception:
            ok = False
        body = {
            "status": "ready" if ok else "not_ready",
            "configuration_id": settings.fingerprint(),
            "adapter": settings.adapter,
            "profile": settings.profile,
        }
        return JSONResponse(status_code=200 if ok else 503, content=body)

    @application.post("/v1/answer", response_model=AnswerResponse)
    async def answer(
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
        x_trace_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
        x_authz_scopes: str | None = Header(default=None),
        x_authz_decision_id: str | None = Header(default=None),
        content_type: str | None = Header(default=None),
    ) -> AnswerResponse:
        with span(
            "http.request",
            {"http.method": "POST", "http.route": "/v1/answer"},
        ):
            if content_type is None or "application/json" not in content_type.lower():
                raise DomainError(
                    ErrorCode.VALIDATION_ERROR,
                    "unsupported content type",
                    retry_class=RetryClass.NONE,
                    http_status=400,
                )

            if not x_tenant_id or not x_actor_id:
                raise DomainError(
                    ErrorCode.UNAUTHORIZED,
                    "missing tenant or actor identity",
                    retry_class=RetryClass.NONE,
                    http_status=401,
                )

            try:
                raw: dict[str, Any] = await request.json()
            except Exception as exc:
                raise DomainError(
                    ErrorCode.VALIDATION_ERROR,
                    "malformed JSON body",
                    retry_class=RetryClass.NONE,
                    http_status=400,
                ) from exc

            for key, expected in (("tenant_id", x_tenant_id), ("actor_id", x_actor_id)):
                if key in raw and raw[key] != expected:
                    raise DomainError(
                        ErrorCode.FORBIDDEN,
                        f"{key} conflicts with authenticated context",
                        retry_class=RetryClass.NONE,
                        http_status=403,
                    )

            body_data = {k: v for k, v in raw.items() if k not in {"tenant_id", "actor_id"}}
            try:
                body = ModelRequest.model_validate(body_data)
            except Exception as exc:
                raise DomainError(
                    ErrorCode.VALIDATION_ERROR,
                    "request validation failed",
                    retry_class=RetryClass.NONE,
                    http_status=400,
                ) from exc

            roles = [r.strip() for r in (x_roles or "policy-reader").split(",") if r.strip()]
            scopes = [
                s.strip() for s in (x_authz_scopes or "policy:read").split(",") if s.strip()
            ]
            request_id = x_request_id or f"req_{uuid4().hex[:12]}"
            trace_id = x_trace_id or f"trace_{uuid4().hex[:12]}"
            c: AppContainer = request.app.state.container
            settings = c.settings
            context = RunContext(
                request_id=request_id,
                trace_id=trace_id,
                tenant_id=x_tenant_id,
                actor_id=x_actor_id,
                roles=roles,
                purpose="policy-question",
                configuration_id=settings.fingerprint(),
                configuration_versions=dict(settings.configuration_versions),
                deadline_at=fake_now() + timedelta(seconds=5),
                budget=Budget(max_input_tokens=2048, max_output_tokens=512),
                authorization_context=AuthorizationContext(
                    scopes=scopes,
                    decision_id=x_authz_decision_id or "authz-fixture-1",
                ),
            )
            if "policy:read" not in scopes:
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "insufficient authorization scope",
                    retry_class=RetryClass.NONE,
                    http_status=403,
                    trace_id=trace_id,
                    request_id=request_id,
                )

            return await c.answer_service.answer(body, context)

    return application


app = create_app()
