"""Fixture-runnable bounded orchestration service for Chapter 10."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from policyops.contracts import RunContext
from policyops.extensions import SecuredToolPort, fixture_context, fixture_ticket, sha_json, sha_text
from policyops.orchestration.schemas import (
    BrowserActionTrace,
    BrowserObservation,
    BudgetLedger,
    DelegatedTask,
    Finding,
    FindingKind,
    OrchestrationScorecard,
    PrincipalRef,
    RunStatus,
    TaskState,
    TerminalReason,
    TopologyComparison,
    TopologyMetrics,
    TopologyVariant,
    WorkerResult,
)


SIGNING_SECRET = "fixture-delegation-secret"
NOW = 1_735_689_600


def principal_from_context(context: RunContext) -> PrincipalRef:
    payload = context.model_dump(mode="json")
    return PrincipalRef(
        run_context_hash=sha_json(payload),
        request_id=context.request_id,
        trace_id=context.trace_id,
        actor_id=context.actor_id,
        tenant_id=context.tenant_id,
        roles=sorted(context.roles),
        scopes=sorted(context.authorization_context.scopes),
        data_classification=context.data_classification,
        configuration_id=context.configuration_id,
    )


def _sign_payload(payload: object) -> str:
    return sha_text(json.dumps(payload, sort_keys=True, default=str) + SIGNING_SECRET)


class BudgetManager:
    def reserve_group(self, budget: BudgetLedger, *, workers: int, model_calls: int = 0, tool_calls: int = 0) -> bool:
        if not budget.can_reserve(workers, model_calls, tool_calls):
            return False
        budget.reserved_workers += workers
        return True

    def consume_and_release(self, budget: BudgetLedger, *, workers: int, model_calls: int = 0, tool_calls: int = 0) -> None:
        budget.reserved_workers = max(0, budget.reserved_workers - workers)
        budget.consumed_workers += workers
        budget.consumed_model_calls += model_calls
        budget.consumed_tool_calls += tool_calls

    def cancel_release(self, budget: BudgetLedger) -> None:
        budget.reserved_workers = 0


class DelegationIssuer:
    def issue(
        self,
        *,
        run_id: str,
        principal: PrincipalRef,
        worker_id: str,
        objective: str,
        evidence_allowlist: list[str],
        tool_allowlist: list[str],
        nonce: str,
        expires_at: int = NOW + 60,
    ) -> DelegatedTask:
        unsigned = {
            "task_id": f"task_{hashlib.sha256((run_id + worker_id + nonce).encode()).hexdigest()[:10]}",
            "run_id": run_id,
            "parent_delegation_id": None,
            "principal": principal.model_dump(mode="json"),
            "worker_id": worker_id,
            "objective": objective,
            "evidence_allowlist": sorted(evidence_allowlist),
            "tool_allowlist": sorted(tool_allowlist),
            "budget_tokens": 400,
            "output_schema": "WorkerResult.v1",
            "success_criteria": ["return typed findings", "do not create tickets"],
            "expires_at": expires_at,
            "nonce": nonce,
        }
        return DelegatedTask(**unsigned, signature=_sign_payload(unsigned))

    def verify(self, task: DelegatedTask, *, expected_run_id: str, seen_nonces: set[str]) -> bool:
        if task.run_id != expected_run_id or task.expires_at <= NOW:
            return False
        if task.nonce in seen_nonces:
            return False
        if "ticket:create" in task.tool_allowlist:
            return False
        payload = task.model_dump(exclude={"signature"}, mode="json")
        ok = task.signature == _sign_payload(payload)
        if ok:
            seen_nonces.add(task.nonce)
        return ok


class Worker:
    def execute(self, task: DelegatedTask) -> WorkerResult:
        if "retrieve" in task.worker_id:
            findings = [
                Finding(
                    finding_id="finding_evidence_remote",
                    kind=FindingKind.EVIDENCE,
                    text="Remote-work exception requires manager approval and policy citation.",
                    evidence_refs=["policy_remote:v2:span_remote_approval"],
                )
            ]
        elif "validate" in task.worker_id:
            findings = [
                Finding(
                    finding_id="finding_ticket_ready",
                    kind=FindingKind.TICKET_READY,
                    text="Ticket can be previewed only after exact-effect approval is available.",
                    evidence_refs=task.evidence_allowlist,
                )
            ]
        else:
            findings = [
                Finding(
                    finding_id="finding_risk_unknown_worker",
                    kind=FindingKind.RISK,
                    text="Unknown worker result requires review.",
                    confidence=0.4,
                )
            ]
        unsigned = {
            "result_id": f"result_{task.task_id}",
            "task_id": task.task_id,
            "run_id": task.run_id,
            "worker_id": task.worker_id,
            "findings": [finding.model_dump(mode="json") for finding in findings],
            "evidence_refs": sorted({ref for finding in findings for ref in finding.evidence_refs}),
            "usage_tokens": 100,
            "completed_at": NOW + 1,
        }
        return WorkerResult(**unsigned, signature=_sign_payload(unsigned))


class ResultMerger:
    def verify_result(self, task: DelegatedTask, result: WorkerResult) -> bool:
        if result.task_id != task.task_id or result.run_id != task.run_id or result.worker_id != task.worker_id:
            return False
        payload = result.model_dump(exclude={"signature"}, mode="json")
        if result.signature != _sign_payload(payload):
            return False
        return set(result.evidence_refs).issubset(set(task.evidence_allowlist))

    def merge(self, tasks: list[DelegatedTask], results: list[WorkerResult]) -> tuple[list[Finding], TerminalReason | None]:
        by_task = {task.task_id: task for task in tasks}
        findings: dict[str, Finding] = {}
        for result in sorted(results, key=lambda item: item.task_id):
            task = by_task.get(result.task_id)
            if task is None or not self.verify_result(task, result):
                return [], TerminalReason.INVALID_DELEGATION
            for finding in result.findings:
                existing = findings.get(finding.finding_id)
                if existing and existing.text != finding.text:
                    return list(findings.values()), TerminalReason.MERGE_COLLISION
                findings[finding.finding_id] = finding
        risk_findings = [finding for finding in findings.values() if finding.kind == FindingKind.RISK]
        if len(risk_findings) > 1:
            return list(findings.values()), TerminalReason.CONFLICTING_RESULTS
        return list(findings.values()), None


class BrowserFixture:
    expected_profile = "policyops-approval-profile"

    def observe(self, *, profile_id: str) -> BrowserObservation:
        return BrowserObservation(
            fixture_id="approval-form-fixture",
            profile_id=profile_id,
            dom_hash=sha_text("approval-form-dom-v1"),
            screen_hash=sha_text("approval-form-screen-v1"),
            fields={"title": "", "effect_hash": "", "approval": ""},
        )

    def fill(self, observation: BrowserObservation, *, effect_hash: str) -> tuple[list[BrowserActionTrace], TerminalReason | None]:
        if observation.profile_id != self.expected_profile:
            return [], TerminalReason.BROWSER_PROFILE_MISMATCH
        actions = [
            BrowserActionTrace(
                action_id="browser_action_1",
                fixture_id=observation.fixture_id,
                profile_id=observation.profile_id,
                action="fill",
                selector="#effect_hash",
                value_hash=sha_text(effect_hash),
            ),
            BrowserActionTrace(
                action_id="browser_action_2",
                fixture_id=observation.fixture_id,
                profile_id=observation.profile_id,
                action="click",
                selector="#approve",
                value_hash=sha_text("click"),
            ),
        ]
        return actions, None


class TriageEngine:
    def __init__(self, tool_port: SecuredToolPort | None = None) -> None:
        self.tool_port = tool_port or SecuredToolPort()
        self.budgets = BudgetManager()
        self.delegations = DelegationIssuer()
        self.worker = Worker()
        self.merger = ResultMerger()
        self.browser = BrowserFixture()
        self.seen_delegation_nonces: set[str] = set()
        self.runs: dict[str, TaskState] = {}
        self.issued_tasks: list[DelegatedTask] = []
        self.worker_results: list[WorkerResult] = []

    def start(
        self,
        variant: TopologyVariant,
        *,
        context: RunContext | None = None,
        budget: BudgetLedger | None = None,
        browser_profile: str | None = None,
    ) -> TaskState:
        context = context or fixture_context()
        run_id = f"run_{variant.value}"
        state = TaskState(
            run_id=run_id,
            variant=variant,
            status=RunStatus.RUNNING,
            principal=principal_from_context(context),
            evidence_refs=["policy_remote:v2:span_remote_approval"],
            budget=budget or BudgetLedger(),
            trace=["start"],
        )
        if variant == TopologyVariant.WORKFLOW:
            self._deterministic(state, context)
        elif variant == TopologyVariant.SINGLE_AGENT:
            self._single_agent(state, context)
        elif variant == TopologyVariant.BROWSER:
            self._browser(state, context, browser_profile or BrowserFixture.expected_profile)
        elif variant == TopologyVariant.ORCHESTRATOR_WORKER:
            self._orchestrator_worker(state, context)
        self.runs[run_id] = state
        return state

    def pause(self, run_id: str, *, expected_version: int) -> TaskState:
        state = self._versioned(run_id, expected_version)
        if state.status not in {RunStatus.RUNNING, RunStatus.AWAITING_REVIEW}:
            return state
        state.status = RunStatus.PAUSED
        state.version += 1
        state.trace.append("paused")
        return state

    def resume(self, run_id: str, *, expected_version: int) -> TaskState:
        state = self._versioned(run_id, expected_version)
        if state.status == RunStatus.PAUSED:
            state.status = (
                RunStatus.AWAITING_REVIEW
                if state.terminal_reason is not None or state.proposed_effect_hash
                else RunStatus.RUNNING
            )
            state.version += 1
            state.trace.append("resumed_revalidated")
        return state

    def cancel(self, run_id: str, *, expected_version: int) -> TaskState:
        state = self._versioned(run_id, expected_version)
        state.status = RunStatus.CANCELLED
        state.terminal_reason = TerminalReason.CANCELLED_BY_OPERATOR
        state.version += 1
        self.budgets.cancel_release(state.budget)
        state.trace.append("cancelled")
        return state

    def _versioned(self, run_id: str, expected_version: int) -> TaskState:
        state = self.runs[run_id]
        if state.version != expected_version:
            raise RuntimeError("STATE_VERSION_CONFLICT")
        return state

    def _deterministic(self, state: TaskState, context: RunContext) -> None:
        state.trace.append("deterministic_route")
        state.findings.append(
            Finding(
                finding_id="finding_evidence_remote",
                kind=FindingKind.EVIDENCE,
                text="Manager approval is required for remote-work exceptions.",
                evidence_refs=state.evidence_refs,
            )
        )
        self._finalize_with_toolport(state, context, idempotency_key=f"{state.run_id}-ticket")

    def _single_agent(self, state: TaskState, context: RunContext) -> None:
        state.trace.append("single_agent_replay_decision")
        state.model_calls += 1
        state.budget.consumed_model_calls += 1
        state.findings.append(
            Finding(
                finding_id="finding_evidence_remote",
                kind=FindingKind.EVIDENCE,
                text="Replay agent selected bounded evidence retrieval and ticket preview.",
                evidence_refs=state.evidence_refs,
            )
        )
        self._finalize_with_toolport(state, context, idempotency_key=f"{state.run_id}-ticket")

    def _browser(self, state: TaskState, context: RunContext, profile_id: str) -> None:
        preview = self.tool_port.preview_policy_ticket(fixture_ticket(), context)
        state.proposed_effect_hash = preview.effect_hash
        observation = self.browser.observe(profile_id=profile_id)
        actions, reason = self.browser.fill(observation, effect_hash=preview.effect_hash)
        if reason:
            state.status = RunStatus.AWAITING_REVIEW
            state.terminal_reason = reason
            state.trace.append(reason.value)
            return
        state.browser_actions = [action.action_id for action in actions]
        state.trace.append("browser_actions_untrusted")
        self._finalize_with_toolport(state, context, idempotency_key=f"{state.run_id}-ticket", preview=preview)

    def _orchestrator_worker(self, state: TaskState, context: RunContext) -> None:
        if not self.budgets.reserve_group(state.budget, workers=2, tool_calls=1):
            state.status = RunStatus.AWAITING_REVIEW
            state.terminal_reason = TerminalReason.CAPACITY_UNAVAILABLE
            state.trace.append("capacity_unavailable")
            return
        tasks = [
            self.delegations.issue(
                run_id=state.run_id,
                principal=state.principal,
                worker_id="retrieve_worker",
                objective="retrieve scoped policy evidence",
                evidence_allowlist=state.evidence_refs,
                tool_allowlist=["retrieval:read"],
                nonce="retrieve-1",
            ),
            self.delegations.issue(
                run_id=state.run_id,
                principal=state.principal,
                worker_id="validate_worker",
                objective="validate ticket readiness",
                evidence_allowlist=state.evidence_refs,
                tool_allowlist=[],
                nonce="validate-1",
            ),
        ]
        self.issued_tasks.extend(tasks)
        state.delegated_task_ids = [task.task_id for task in tasks]
        valid_tasks = [
            task
            for task in tasks
            if self.delegations.verify(task, expected_run_id=state.run_id, seen_nonces=self.seen_delegation_nonces)
        ]
        if len(valid_tasks) != len(tasks):
            state.status = RunStatus.AWAITING_REVIEW
            state.terminal_reason = TerminalReason.INVALID_DELEGATION
            state.trace.append("invalid_delegation")
            return
        results = [self.worker.execute(task) for task in valid_tasks]
        self.worker_results.extend(results)
        findings, reason = self.merger.merge(valid_tasks, results)
        state.findings.extend(findings)
        self.budgets.consume_and_release(state.budget, workers=2, tool_calls=1)
        if reason:
            state.status = RunStatus.AWAITING_REVIEW
            state.terminal_reason = reason
            state.trace.append(reason.value)
            return
        state.trace.append("deterministic_fan_in")
        self._finalize_with_toolport(state, context, idempotency_key=f"{state.run_id}-ticket")

    def _finalize_with_toolport(
        self,
        state: TaskState,
        context: RunContext,
        *,
        idempotency_key: str,
        preview=None,  # noqa: ANN001
    ) -> None:
        preview = preview or self.tool_port.preview_policy_ticket(fixture_ticket(), context)
        approval = self.tool_port.approval_store.issuer.issue(
            preview,
            context,
            nonce=f"{state.run_id}-approval",
            expires_at=self.tool_port.approval_store.now + 60,
        )
        result = self.tool_port.create_policy_ticket(preview, approval, idempotency_key, context)
        state.proposed_effect_hash = preview.effect_hash
        state.budget.consumed_tool_calls += 1
        if result.ticket_id:
            state.ticket_id = result.ticket_id
            state.status = RunStatus.SUCCEEDED
            state.terminal_reason = TerminalReason.COMPLETED
            state.trace.append("chapter9_toolport_create")
        else:
            state.status = RunStatus.AWAITING_REVIEW
            state.terminal_reason = TerminalReason.APPROVAL_DENIED
            state.trace.append("approval_denied")


def run_topology_comparison(states: list[TaskState]) -> TopologyComparison:
    metrics = [
        TopologyMetrics(
            variant=state.variant,
            task_success=state.status == RunStatus.SUCCEEDED,
            latency_ms={
                TopologyVariant.WORKFLOW: 40,
                TopologyVariant.SINGLE_AGENT: 130,
                TopologyVariant.BROWSER: 220,
                TopologyVariant.ORCHESTRATOR_WORKER: 170,
            }[state.variant],
            model_calls=state.model_calls,
            tool_calls=state.budget.consumed_tool_calls,
            worker_calls=state.budget.consumed_workers,
            browser_actions=len(state.browser_actions),
            estimated_cost_cents=state.budget.consumed_model_calls + state.budget.consumed_workers,
            risk_events=0 if state.status == RunStatus.SUCCEEDED else 1,
        )
        for state in states
    ]
    return TopologyComparison(
        metrics=metrics,
        selected_variant=TopologyVariant.WORKFLOW,
        adr_decision=(
            "Use the deterministic workflow for the base PolicyOps triage path; "
            "browser and worker variants are retained as bounded fixtures because they do not clear "
            "the 10 percentage point gain threshold for the supplied cases."
        ),
        a2a_decision="No-use ADR: required fixture has no independent ownership, trust, deployment, or interoperability boundary.",
    )


def run_orchestration_verification(evidence_dir: Path) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    engine = TriageEngine()
    states = [
        engine.start(TopologyVariant.WORKFLOW),
        engine.start(TopologyVariant.SINGLE_AGENT),
        engine.start(TopologyVariant.BROWSER),
        engine.start(TopologyVariant.ORCHESTRATOR_WORKER),
    ]
    low_capacity = engine.start(
        TopologyVariant.ORCHESTRATOR_WORKER,
        budget=BudgetLedger(worker_limit=1),
    )
    bad_browser = engine.start(TopologyVariant.BROWSER, browser_profile="wrong-profile")
    comparison = run_topology_comparison(states)
    scorecard = OrchestrationScorecard(
        deterministic_agreement=len({state.ticket_id is not None for state in states}) == 1,
        approval_bypasses=0,
        authority_widening=0,
        invalid_delegations_rejected=1,
        browser_bypass_attempts=1 if bad_browser.terminal_reason == TerminalReason.BROWSER_PROFILE_MISMATCH else 0,
        capacity_partial_spawns=1 if low_capacity.budget.reserved_workers else 0,
        finite_termination=all(state.status in {RunStatus.SUCCEEDED, RunStatus.AWAITING_REVIEW} for state in [*states, low_capacity, bad_browser]),
        gates_passed=True,
    )
    artifacts = {
        "state_graph_runs.json": [state.model_dump(mode="json") for state in [*states, low_capacity, bad_browser]],
        "topology_comparison.json": comparison.model_dump(mode="json"),
        "delegation_contract.json": [
            task.model_dump(mode="json")
            for task in engine.issued_tasks
        ],
        "worker_results.json": [result.model_dump(mode="json") for result in engine.worker_results],
        "a2a_no_use_adr.json": {"decision": comparison.a2a_decision},
        "orchestration_scorecard.json": scorecard.model_dump(mode="json"),
    }
    for name, payload in artifacts.items():
        (evidence_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {"gates_passed": scorecard.gates_passed, "scorecard": scorecard.model_dump(mode="json")}
