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

from policyops.capstone import (
    CapstoneRunRecord,
    CapstoneRuntime,
    MemoryCorrectionRequest,
    MemoryDeleteRequest,
    MemoryEnvelope,
    TicketExecuteRequest,
    TicketExecutionEnvelope,
    TicketPreviewRequest,
)
from policyops.capstone.service import CapstoneConflictError, CapstoneNotFoundError
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
from policyops.deployment import DependencyDiagnostic, DeploymentRuntime, HealthReport, HealthState
from policyops.extensions import ExtensionRuntime, ExtensionVersion
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
from policyops.telemetry import (
    AdjudicationEnvelope,
    AdjudicationRequest,
    CanaryReport,
    CanaryStopRequest,
    ExperimentEnvelope,
    ExperimentRunRequest,
    OperationEnvelope,
    TelemetryNotFoundError,
    TelemetryRuntime,
    hash_tenant,
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
    application.state.telemetry_runtime = TelemetryRuntime(
        Path(__file__).resolve().parents[3] / "build" / "ch12" / "runtime"
    )
    application.state.extension_runtime = ExtensionRuntime(
        Path(__file__).resolve().parents[3] / "build" / "ch09" / "runtime"
    )
    application.state.deployment_runtime = DeploymentRuntime(
        Path(__file__).resolve().parents[3] / "build" / "ch14" / "runtime"
    )
    application.state.capstone_runtime = CapstoneRuntime(
        Path(__file__).resolve().parents[3] / "build" / "ch16" / "runtime"
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

    def _require_operation_access(tenant_id: str, envelope: OperationEnvelope) -> None:
        if not envelope.spans:
            raise _problem(ErrorCode.NOT_FOUND, "operation has no spans", http_status=404)
        if envelope.spans[0].context.tenant_hash != hash_tenant(tenant_id):
            raise _problem(ErrorCode.FORBIDDEN, "operation tenant mismatch", http_status=403)

    def _require_operator_role(roles_header: str | None) -> str:
        roles = [r.strip() for r in (roles_header or "").split(",") if r.strip()]
        allowed = {
            "operator",
            "platform-engineer",
            "site-reliability-engineer",
            "database-engineer",
            "release-engineer",
        }
        for role in roles:
            if role in allowed:
                return role
        raise _problem(ErrorCode.FORBIDDEN, "operator role required", http_status=403)

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

    @application.get("/health/startup", response_model=HealthReport)
    async def startup(request: Request) -> Response:
        runtime: DeploymentRuntime = request.app.state.deployment_runtime
        report = runtime.startup_report()
        return JSONResponse(
            status_code=200 if report.startup == HealthState.READY else 503,
            content=report.model_dump(mode="json"),
        )

    @application.get("/diagnostics/dependencies", response_model=list[DependencyDiagnostic])
    async def dependency_diagnostics(
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
    ) -> list[DependencyDiagnostic]:
        _require_identity(x_tenant_id, x_actor_id)
        role = _require_operator_role(x_roles)
        runtime: DeploymentRuntime = request.app.state.deployment_runtime
        return runtime.dependency_diagnostics(role=role)

    @application.get("/v1/extensions", response_model=list[ExtensionVersion])
    async def list_extensions(
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
    ) -> list[ExtensionVersion]:
        _require_identity(x_tenant_id, x_actor_id)
        _require_operator_role(x_roles)
        runtime: ExtensionRuntime = request.app.state.extension_runtime
        return runtime.list_extensions()

    @application.post("/v1/extensions/{extension_id}:disable", response_model=ExtensionVersion)
    async def disable_extension(
        extension_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
    ) -> ExtensionVersion:
        _require_identity(x_tenant_id, x_actor_id)
        _require_operator_role(x_roles)
        runtime: ExtensionRuntime = request.app.state.extension_runtime
        return runtime.disable_extension(extension_id)

    @application.post("/v1/extensions/{extension_id}:activate", response_model=ExtensionVersion)
    async def activate_extension(
        extension_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
    ) -> ExtensionVersion:
        _require_identity(x_tenant_id, x_actor_id)
        _require_operator_role(x_roles)
        runtime: ExtensionRuntime = request.app.state.extension_runtime
        return runtime.activate_extension(extension_id)

    @application.post("/v1/extensions/{extension_id}:rollback", response_model=ExtensionVersion)
    async def rollback_extension(
        extension_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
    ) -> ExtensionVersion:
        _require_identity(x_tenant_id, x_actor_id)
        _require_operator_role(x_roles)
        runtime: ExtensionRuntime = request.app.state.extension_runtime
        return runtime.rollback_extension(extension_id)

    @application.post("/v1/extensions/{extension_id}:revoke", response_model=ExtensionVersion)
    async def revoke_extension(
        extension_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
    ) -> ExtensionVersion:
        _require_identity(x_tenant_id, x_actor_id)
        _require_operator_role(x_roles)
        runtime: ExtensionRuntime = request.app.state.extension_runtime
        return runtime.revoke_extension(extension_id)

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

    @application.post("/v1/tickets/preview", response_model=TicketExecutionEnvelope)
    async def ticket_preview(
        body: TicketPreviewRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
        x_trace_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
        x_authz_scopes: str | None = Header(default=None),
        x_authz_decision_id: str | None = Header(default=None),
    ) -> TicketExecutionEnvelope:
        tenant_id, actor_id = _require_identity(x_tenant_id, x_actor_id)
        settings = request.app.state.container.settings
        context = _run_context(
            tenant_id=tenant_id,
            actor_id=actor_id,
            settings=settings,
            request_id=x_request_id,
            trace_id=x_trace_id,
            roles_header=x_roles,
            scopes_header=x_authz_scopes or "ticket:preview,ticket:create",
            decision_id=x_authz_decision_id,
            purpose="policy-support-ticket-preview",
        )
        runtime: CapstoneRuntime = request.app.state.capstone_runtime
        try:
            return runtime.preview_ticket(body, context=context)
        except PermissionError as exc:
            raise _problem(ErrorCode.FORBIDDEN, str(exc), http_status=403) from exc
        except ValueError as exc:
            raise _problem(ErrorCode.VALIDATION_ERROR, str(exc), http_status=400) from exc

    @application.post("/v1/tickets/execute", response_model=TicketExecutionEnvelope)
    async def ticket_execute(
        body: TicketExecuteRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
        x_trace_id: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
        x_authz_scopes: str | None = Header(default=None),
        x_authz_decision_id: str | None = Header(default=None),
    ) -> TicketExecutionEnvelope:
        tenant_id, actor_id = _require_identity(x_tenant_id, x_actor_id)
        settings = request.app.state.container.settings
        context = _run_context(
            tenant_id=tenant_id,
            actor_id=actor_id,
            settings=settings,
            request_id=x_request_id,
            trace_id=x_trace_id,
            roles_header=x_roles,
            scopes_header=x_authz_scopes or "ticket:preview,ticket:create",
            decision_id=x_authz_decision_id,
            purpose="policy-support-ticket-execute",
        )
        runtime: CapstoneRuntime = request.app.state.capstone_runtime
        try:
            return runtime.execute_ticket(body, context=context)
        except PermissionError as exc:
            raise _problem(ErrorCode.FORBIDDEN, str(exc), http_status=403) from exc
        except ValueError as exc:
            raise _problem(ErrorCode.VALIDATION_ERROR, str(exc), http_status=400) from exc
        except CapstoneConflictError as exc:
            raise _problem(ErrorCode.CONFLICT, str(exc), http_status=409) from exc

    @application.get("/v1/runs/{run_id}", response_model=CapstoneRunRecord)
    async def capstone_run_inspect(
        run_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> CapstoneRunRecord:
        tenant_id, actor_id = _require_identity(x_tenant_id, x_actor_id)
        runtime: CapstoneRuntime = request.app.state.capstone_runtime
        try:
            run = runtime.inspect_run(run_id)
        except CapstoneNotFoundError as exc:
            raise _problem(ErrorCode.NOT_FOUND, str(exc), http_status=404) from exc
        if run.tenant_id != tenant_id or run.actor_id != actor_id:
            raise _problem(ErrorCode.FORBIDDEN, "run identity mismatch", http_status=403)
        return run

    @application.get("/v1/memory", response_model=MemoryEnvelope)
    async def memory_export(
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> MemoryEnvelope:
        _require_identity(x_tenant_id, x_actor_id)
        runtime: CapstoneRuntime = request.app.state.capstone_runtime
        return runtime.memory_export()

    @application.get("/v1/memory/export", response_model=MemoryEnvelope)
    async def memory_export_alias(
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> MemoryEnvelope:
        return await memory_export(request, x_tenant_id, x_actor_id)

    @application.post("/v1/memory/correct", response_model=MemoryEnvelope)
    async def memory_correct(
        body: MemoryCorrectionRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> MemoryEnvelope:
        _require_identity(x_tenant_id, x_actor_id)
        runtime: CapstoneRuntime = request.app.state.capstone_runtime
        try:
            return runtime.memory_correct(body)
        except CapstoneNotFoundError as exc:
            raise _problem(ErrorCode.NOT_FOUND, str(exc), http_status=404) from exc
        except CapstoneConflictError as exc:
            raise _problem(ErrorCode.CONFLICT, str(exc), http_status=409) from exc

    @application.post("/v1/memory/delete", response_model=MemoryEnvelope)
    async def memory_delete(
        body: MemoryDeleteRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> MemoryEnvelope:
        _require_identity(x_tenant_id, x_actor_id)
        runtime: CapstoneRuntime = request.app.state.capstone_runtime
        try:
            return runtime.memory_delete(body)
        except CapstoneNotFoundError as exc:
            raise _problem(ErrorCode.NOT_FOUND, str(exc), http_status=404) from exc
        except CapstoneConflictError as exc:
            raise _problem(ErrorCode.CONFLICT, str(exc), http_status=409) from exc

    @application.get("/operations/{correlation_id}", response_model=OperationEnvelope)
    async def operation_inspect(
        correlation_id: str,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> OperationEnvelope:
        tenant_id, _actor_id = _require_identity(x_tenant_id, x_actor_id)
        runtime: TelemetryRuntime = request.app.state.telemetry_runtime
        try:
            envelope = runtime.inspect_operation(correlation_id)
        except TelemetryNotFoundError as exc:
            raise _problem(ErrorCode.NOT_FOUND, str(exc), http_status=404) from exc
        _require_operation_access(tenant_id, envelope)
        return envelope

    @application.post("/adjudications", response_model=AdjudicationEnvelope)
    async def adjudicate_operation(
        body: AdjudicationRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> AdjudicationEnvelope:
        tenant_id, _actor_id = _require_identity(x_tenant_id, x_actor_id)
        runtime: TelemetryRuntime = request.app.state.telemetry_runtime
        operation = runtime.inspect_operation(body.correlation_id)
        _require_operation_access(tenant_id, operation)
        return runtime.adjudicate(body)

    @application.post("/experiments", response_model=ExperimentEnvelope)
    async def run_experiment(
        body: ExperimentRunRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> ExperimentEnvelope:
        _require_identity(x_tenant_id, x_actor_id)
        runtime: TelemetryRuntime = request.app.state.telemetry_runtime
        return runtime.run_experiment(body)

    @application.post("/canaries/{canary_id}/stop", response_model=CanaryReport)
    async def stop_canary(
        canary_id: str,
        body: CanaryStopRequest,
        request: Request,
        x_tenant_id: str | None = Header(default=None),
        x_actor_id: str | None = Header(default=None),
    ) -> CanaryReport:
        _require_identity(x_tenant_id, x_actor_id)
        runtime: TelemetryRuntime = request.app.state.telemetry_runtime
        try:
            return runtime.stop_canary(canary_id, body)
        except TelemetryNotFoundError as exc:
            raise _problem(ErrorCode.NOT_FOUND, str(exc), http_status=404) from exc

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
