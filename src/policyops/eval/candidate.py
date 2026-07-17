"""Candidate adapters for evaluation — wraps Chapter 1 answer path."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from policyops.adapters.replay import ReplayModelClient
from policyops.composition import AppContainer
from policyops.config import Settings
from policyops.contracts import (
    AuthorizationContext,
    Budget,
    DomainError,
    ModelRequest,
    RunContext,
)
from policyops.eval.schemas import TaskCase, TrialContext, TrialRecord
from policyops.services import AnswerService
from policyops.util import fake_now


class PolicyOpsCandidate:
    candidate_id = "policyops-replay"

    def __init__(self, fixture_pack: Path | None = None) -> None:
        pack = Path(fixture_pack or "labs/ch01/fixtures")
        settings = Settings(profile="fixture", adapter="replay", fixture_pack=pack, lab_id="ch01")
        client = ReplayModelClient(pack)
        self.container = AppContainer(
            settings=settings, client=client, answer_service=AnswerService(client)
        )
        self._client = client

    async def run(self, case: TaskCase, trial: TrialContext) -> TrialRecord:
        started = time.perf_counter()
        mode = case.input.get("mode", "answer")

        if mode == "tool_args_only":
            return TrialRecord(
                trial_id=trial.trial_id,
                task_id=case.task_id,
                candidate_id=self.candidate_id,
                status="ok",
                output={"tool_args": case.input.get("proposed_tool_args")},
                http_status=200,
                model_invoked=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                usage=None,
                cost_usd=None,
            )

        if mode == "gaming":
            return TrialRecord(
                trial_id=trial.trial_id,
                task_id=case.task_id,
                candidate_id="gaming-candidate",
                status="ok",
                output={
                    "answer": {
                        "schema_version": "1.0",
                        "answer_type": "direct",
                        "text": "This is definitely the complete policy answer.",
                        "citations": [],
                    }
                },
                http_status=200,
                model_invoked=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                usage={"input_tokens": 10, "output_tokens": 10, "adapter": "gaming"},
                cost_usd=0.0,
            )

        if mode == "forced_abstain":
            return TrialRecord(
                trial_id=trial.trial_id,
                task_id=case.task_id,
                candidate_id=self.candidate_id,
                status="ok",
                output={
                    "answer": {
                        "schema_version": "1.0",
                        "answer_type": "abstain",
                        "text": "Insufficient evidence in the policy corpus.",
                        "abstention_reason": "insufficient_evidence",
                        "citations": [],
                    }
                },
                http_status=200,
                model_invoked=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                usage={"input_tokens": 8, "output_tokens": 12, "adapter": "replay"},
                cost_usd=0.0,
            )

        headers = case.input.get("headers") or {}
        tenant = headers.get("X-Tenant-Id")
        actor = headers.get("X-Actor-Id")
        before = self._client.call_count
        question = case.input.get("question", "")
        body_extra = case.input.get("body") or {}
        # Simulate API identity gate used in Chapter 1.
        if not tenant or not actor:
            return TrialRecord(
                trial_id=trial.trial_id,
                task_id=case.task_id,
                candidate_id=self.candidate_id,
                status="error",
                output=None,
                http_status=401,
                model_invoked=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code="UNAUTHORIZED",
            )
        if body_extra.get("tenant_id") and body_extra["tenant_id"] != tenant:
            return TrialRecord(
                trial_id=trial.trial_id,
                task_id=case.task_id,
                candidate_id=self.candidate_id,
                status="error",
                output=None,
                http_status=403,
                model_invoked=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code="FORBIDDEN",
            )

        from datetime import timedelta

        context = RunContext(
            request_id=trial.trial_id,
            trace_id=f"trace_{uuid4().hex[:8]}",
            tenant_id=tenant,
            actor_id=actor,
            roles=["policy-reader"],
            purpose="policy-question",
            configuration_id=self.container.settings.fingerprint(),
            configuration_versions=dict(self.container.settings.configuration_versions),
            deadline_at=fake_now() + timedelta(seconds=5),
            budget=Budget(max_input_tokens=2048, max_output_tokens=512),
            authorization_context=AuthorizationContext(
                scopes=["policy:read"], decision_id="authz-eval-1"
            ),
        )
        try:
            response = await self.container.answer_service.answer(
                ModelRequest(question=question), context
            )
            invoked = self._client.call_count > before
            payload: dict[str, Any] = response.model_dump(mode="json")
            return TrialRecord(
                trial_id=trial.trial_id,
                task_id=case.task_id,
                candidate_id=self.candidate_id,
                status="ok",
                output=payload,
                http_status=200,
                model_invoked=invoked,
                latency_ms=(time.perf_counter() - started) * 1000,
                usage=payload.get("usage"),
                cost_usd=0.0,
                trace={"configuration_id": payload.get("configuration_id")},
            )
        except DomainError as exc:
            invoked = self._client.call_count > before
            return TrialRecord(
                trial_id=trial.trial_id,
                task_id=case.task_id,
                candidate_id=self.candidate_id,
                status="error",
                output=None,
                http_status=exc.http_status,
                model_invoked=invoked,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code=exc.code.value,
            )
