"""FastAPI boundary — identity headers, answer + health routes."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
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
from policyops.harness import (
    SessionCancelRequest,
    SessionConflictError,
    SessionEnvelope,
    SessionEvent,
    SessionCheckpoint,
    SessionNotFoundError,
    SessionResumeRequest,
    SessionRunRequest,
    SessionRuntime,
)
from policyops.orchestration import (
    TriageConflictError,
    TriageControlRequest,
    TriageNotFoundError,
    TriageRunEnvelope,
    TriageRunRequest,
    TriageRuntime,
)
from policyops.telemetry import setup_telemetry, span
from policyops.util import fake_now


def create_app(container: AppContainer | None = None) -> FastAPI:
    setup_telemetry()
    application = FastAPI(title="PolicyOps", version="0.1.0")
    application.state.container = container or build_container()
    application.state.session_runtime = SessionRuntime(
        Path(__file__).resolve().parents[3] / "build" / "ch11" / "runtime"
    )
    application.state.triage_runtime = TriageRuntime(
        Path(__file__).resolve().parents[3] / "build" / "ch10" / "runtime"
    )

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

    def _problem(
        code: ErrorCode,
        message: str,
        *,
        http_status: int,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> DomainError:
        return DomainError(
            code,
            message,
            retry_class=RetryClass.NONE,
            http_status=http_status,
            trace_id=trace_id,
            request_id=request_id,
        )

    def _require_identity(x_tenant_id: str | None, x_actor_id: str | None) -> tuple[str, str]:
        if not x_tenant_id or not x_actor_id:
            raise _problem(
                ErrorCode.UNAUTHORIZED,
                "missing tenant or actor identity",
                http_status=401,
            )
        return x_tenant_id, x_actor_id

    def _run_context(
        *,
        tenant_id: str,
        actor_id: str,
        settings,
        request_id: str | None,
        trace_id: str | None,
        roles_header: str | None,
        scopes_header: str | None,
        decision_id: str | None,
        purpose: str,
    ) -> RunContext:
        roles = [r.strip() for r in (roles_header or "policy-reader").split(",") if r.strip()]
        scopes = [s.strip() for s in (scopes_header or "policy:read").split(",") if s.strip()]
        return RunContext(
            request_id=request_id or f"req_{uuid4().hex[:12]}",
            trace_id=trace_id or f"trace_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            actor_id=actor_id,
            roles=roles,
            purpose=purpose,
            configuration_id=settings.fingerprint(),
            configuration_versions=dict(settings.configuration_versions),
            deadline_at=fake_now() + timedelta(seconds=5),
            budget=Budget(max_input_tokens=2048, max_output_tokens=512),
            authorization_context=AuthorizationContext(
                scopes=scopes,
                decision_id=decision_id or "authz-fixture-1",
            ),
        )

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

            c: AppContainer = request.app.state.container
            settings = c.settings
            context = _run_context(
                tenant_id=x_tenant_id,
                actor_id=x_actor_id,
                settings=settings,
                request_id=x_request_id,
                trace_id=x_trace_id,
                roles_header=x_roles,
                scopes_header=x_authz_scopes,
                decision_id=x_authz_decision_id,
                purpose="policy-question",
            )
            if "policy:read" not in context.authorization_context.scopes:
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "insufficient authorization scope",
                    retry_class=RetryClass.NONE,
                    http_status=403,
                    trace_id=context.trace_id,
                    request_id=context.request_id,
                )

            return await c.answer_service.answer(body, context)

    @application.post("/v1/triage/runs", response_model=TriageRunEnvelope)
    async def triage_run_create(
        body: TriageRunRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
        x_trace_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
        x_authz_scopes: str | None = Header(default=None),
        x_authz_decision_id: str | None = Header(default=None),
    ) -> TriageRunEnvelope:
        tenant_id, actor_id = _require_identity(x_tenant_id, x_actor_id)
        settings = request.app.state.container.settings
        context = _run_context(
            tenant_id=tenant_id,
            actor_id=actor_id,
            settings=settings,
            request_id=x_request_id,
            trace_id=x_trace_id,
            roles_header=x_roles,
            scopes_header=x_authz_scopes or "policy:read,ticket:create,ticket:preview",
            decision_id=x_authz_decision_id,
            purpose="policy-triage",
        )
        runtime: TriageRuntime = request.app.state.triage_runtime
        return runtime.create(body, context=context)

    @application.get("/v1/triage/runs/{run_id}", response_model=TriageRunEnvelope)
    async def triage_run_inspect(
        run_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> TriageRunEnvelope:
        tenant_id, actor_id = _require_identity(x_tenant_id, x_actor_id)
        runtime: TriageRuntime = request.app.state.triage_runtime
        try:
            envelope = runtime.inspect(run_id)
        except TriageNotFoundError as exc:
            raise _problem(ErrorCode.NOT_FOUND, str(exc), http_status=404) from exc
        if envelope.run.principal.tenant_id != tenant_id or envelope.run.principal.actor_id != actor_id:
            raise _problem(ErrorCode.FORBIDDEN, "run identity mismatch", http_status=403)
        return envelope

    @application.post("/v1/triage/runs/{run_id}:pause", response_model=TriageRunEnvelope)
    async def triage_run_pause(
        run_id: str,
        body: TriageControlRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> TriageRunEnvelope:
        await triage_run_inspect(run_id, request, x_tenant_id, x_actor_id)
        runtime: TriageRuntime = request.app.state.triage_runtime
        try:
            return runtime.pause(run_id, body)
        except TriageConflictError as exc:
            raise _problem(ErrorCode.CONFLICT, str(exc), http_status=409) from exc

    @application.post("/v1/triage/runs/{run_id}:resume", response_model=TriageRunEnvelope)
    async def triage_run_resume(
        run_id: str,
        body: TriageControlRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> TriageRunEnvelope:
        await triage_run_inspect(run_id, request, x_tenant_id, x_actor_id)
        runtime: TriageRuntime = request.app.state.triage_runtime
        try:
            return runtime.resume(run_id, body)
        except TriageConflictError as exc:
            raise _problem(ErrorCode.CONFLICT, str(exc), http_status=409) from exc

    @application.post("/v1/triage/runs/{run_id}:cancel", response_model=TriageRunEnvelope)
    async def triage_run_cancel(
        run_id: str,
        body: TriageControlRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> TriageRunEnvelope:
        await triage_run_inspect(run_id, request, x_tenant_id, x_actor_id)
        runtime: TriageRuntime = request.app.state.triage_runtime
        try:
            return runtime.cancel(run_id, body)
        except TriageConflictError as exc:
            raise _problem(ErrorCode.CONFLICT, str(exc), http_status=409) from exc

    @application.get("/v1/sessions/{session_id}", response_model=SessionEnvelope)
    async def session_inspect(
        session_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> SessionEnvelope:
        tenant_id, actor_id = _require_identity(x_tenant_id, x_actor_id)
        runtime: SessionRuntime = request.app.state.session_runtime
        try:
            envelope = runtime.inspect(session_id)
        except SessionNotFoundError as exc:
            raise _problem(ErrorCode.NOT_FOUND, str(exc), http_status=404) from exc
        if envelope.session.tenant_id != tenant_id or envelope.session.actor_id != actor_id:
            raise _problem(ErrorCode.FORBIDDEN, "session identity mismatch", http_status=403)
        return envelope

    @application.get("/v1/sessions/{session_id}/events", response_model=list[SessionEvent])
    async def session_events(
        session_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> list[SessionEvent]:
        envelope = await session_inspect(session_id, request, x_tenant_id, x_actor_id)
        return envelope.events

    @application.get("/v1/sessions/{session_id}/checkpoint", response_model=SessionCheckpoint | None)
    async def session_checkpoint(
        session_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> SessionCheckpoint | None:
        envelope = await session_inspect(session_id, request, x_tenant_id, x_actor_id)
        return envelope.checkpoint

    @application.post("/v1/sessions/{session_id}/run", response_model=SessionEnvelope)
    async def session_run(
        session_id: str,
        body: SessionRunRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
        x_trace_id: str | None = Header(default=None),
    ) -> SessionEnvelope:
        tenant_id, actor_id = _require_identity(x_tenant_id, x_actor_id)
        runtime: SessionRuntime = request.app.state.session_runtime
        configuration_id = request.app.state.container.settings.fingerprint()
        try:
            return runtime.run(
                session_id,
                body,
                tenant_id=tenant_id,
                actor_id=actor_id,
                configuration_id=configuration_id,
                request_id=x_request_id,
                trace_id=x_trace_id,
            )
        except SessionConflictError as exc:
            raise _problem(ErrorCode.CONFLICT, str(exc), http_status=409) from exc

    @application.post("/v1/sessions/{session_id}/resume", response_model=SessionEnvelope)
    async def session_resume(
        session_id: str,
        body: SessionResumeRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> SessionEnvelope:
        tenant_id, actor_id = _require_identity(x_tenant_id, x_actor_id)
        runtime: SessionRuntime = request.app.state.session_runtime
        try:
            return runtime.resume(session_id, body, tenant_id=tenant_id, actor_id=actor_id)
        except SessionNotFoundError as exc:
            raise _problem(ErrorCode.NOT_FOUND, str(exc), http_status=404) from exc
        except SessionConflictError as exc:
            raise _problem(ErrorCode.CONFLICT, str(exc), http_status=409) from exc

    @application.post("/v1/sessions/{session_id}/cancel", response_model=SessionEnvelope)
    async def session_cancel(
        session_id: str,
        body: SessionCancelRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> SessionEnvelope:
        tenant_id, actor_id = _require_identity(x_tenant_id, x_actor_id)
        runtime: SessionRuntime = request.app.state.session_runtime
        try:
            return runtime.cancel(session_id, body, tenant_id=tenant_id, actor_id=actor_id)
        except SessionNotFoundError as exc:
            raise _problem(ErrorCode.NOT_FOUND, str(exc), http_status=404) from exc
        except SessionConflictError as exc:
            raise _problem(ErrorCode.CONFLICT, str(exc), http_status=409) from exc

    return application


app = create_app()
