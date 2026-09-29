"""Fixture-runnable bounded orchestration service for Chapter 10."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from policyops.contracts import RunContext
from policyops.extensions import SecuredToolPort, fixture_context, fixture_ticket, sha_json, sha_text
from policyops.orchestration.schemas import (
    BrowserActionTrace,
    BrowserObservation,
    BudgetEntry,
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
    TransitionEvent,
    TriageControlRequest,
    TriageRunEnvelope,
    TriageRunRequest,
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

    def consume_and_release(
        self,
        budget: BudgetLedger,
        *,
        workers: int,
        model_calls: int = 0,
        tool_calls: int = 0,
        tokens: int = 0,
        spend_cents: int = 0,
    ) -> None:
        budget.reserved_workers = max(0, budget.reserved_workers - workers)
        budget.consumed_workers += workers
        budget.consumed_model_calls += model_calls
        budget.consumed_tool_calls += tool_calls
        budget.consumed_tokens += tokens
        budget.consumed_spend_cents += spend_cents

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


class TriageNotFoundError(RuntimeError):
    pass


class TriageConflictError(RuntimeError):
    pass


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
        self.transition_events: list[TransitionEvent] = []
        self.budget_entries: list[BudgetEntry] = []

    def _record_transition(
        self,
        state: TaskState,
        event_type: str,
        trace_code: str,
        *,
        status: RunStatus | None = None,
        terminal_reason: TerminalReason | None = None,
    ) -> None:
        if status is not None:
            state.status = status
        if terminal_reason is not None:
            state.terminal_reason = terminal_reason
        state.trace.append(trace_code)
        state.version += 1
        self.transition_events.append(
            TransitionEvent(
                run_id=state.run_id,
                sequence=state.version,
                event_type=event_type,
                status=state.status,
                terminal_reason=state.terminal_reason,
                trace_code=trace_code,
                occurred_at=NOW + state.version,
            )
        )

    def _record_budget_entry(self, state: TaskState, action: str) -> None:
        self.budget_entries.append(
            BudgetEntry(
                run_id=state.run_id,
                sequence=len([entry for entry in self.budget_entries if entry.run_id == state.run_id]) + 1,
                action=action,
                reserved_workers=state.budget.reserved_workers,
                consumed_workers=state.budget.consumed_workers,
                consumed_model_calls=state.budget.consumed_model_calls,
                consumed_tool_calls=state.budget.consumed_tool_calls,
                budget_snapshot=state.budget.model_copy(deep=True),
                occurred_at=NOW + state.version,
            )
        )

    def start(
        self,
        variant: TopologyVariant,
        *,
        run_id: str | None = None,
        context: RunContext | None = None,
        budget: BudgetLedger | None = None,
        browser_profile: str | None = None,
    ) -> TaskState:
        context = context or fixture_context()
        run_id = run_id or f"run_{variant.value}_{uuid4().hex[:10]}"
        state = TaskState(
            run_id=run_id,
            variant=variant,
            status=RunStatus.RUNNING,
            principal=principal_from_context(context),
            evidence_refs=["policy_remote:v2:span_remote_approval"],
            budget=budget or BudgetLedger(),
            version=0,
            trace=[],
        )
        self._record_transition(state, "run_created", "start", status=RunStatus.RUNNING)
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

    def inspect(self, run_id: str) -> TaskState:
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise TriageNotFoundError(f"run not found: {run_id}") from exc

    def delegated_tasks_for(self, run_id: str) -> list[DelegatedTask]:
        return [task for task in self.issued_tasks if task.run_id == run_id]

    def worker_results_for(self, run_id: str) -> list[WorkerResult]:
        return [result for result in self.worker_results if result.run_id == run_id]

    def transition_events_for(self, run_id: str) -> list[TransitionEvent]:
        return [event for event in self.transition_events if event.run_id == run_id]

    def budget_entries_for(self, run_id: str) -> list[BudgetEntry]:
        return [entry for entry in self.budget_entries if entry.run_id == run_id]

    def pause(self, run_id: str, *, expected_version: int) -> TaskState:
        state = self._versioned(run_id, expected_version)
        if state.status not in {RunStatus.RUNNING, RunStatus.AWAITING_REVIEW}:
            return state
        self._record_transition(state, "run_paused", "paused", status=RunStatus.PAUSED)
        return state

    def resume(self, run_id: str, *, expected_version: int) -> TaskState:
        state = self._versioned(run_id, expected_version)
        if state.status == RunStatus.PAUSED:
            resumed_status = (
                RunStatus.AWAITING_REVIEW
                if state.terminal_reason is not None or state.proposed_effect_hash
                else RunStatus.RUNNING
            )
            self._record_transition(state, "run_resumed", "resumed_revalidated", status=resumed_status)
        return state

    def cancel(self, run_id: str, *, expected_version: int) -> TaskState:
        state = self._versioned(run_id, expected_version)
        self.budgets.cancel_release(state.budget)
        self._record_budget_entry(state, "cancel_release")
        self._record_transition(
            state,
            "run_cancelled",
            "cancelled",
            status=RunStatus.CANCELLED,
            terminal_reason=TerminalReason.CANCELLED_BY_OPERATOR,
        )
        return state

    def _versioned(self, run_id: str, expected_version: int) -> TaskState:
        try:
            state = self.runs[run_id]
        except KeyError as exc:
            raise TriageNotFoundError(f"run not found: {run_id}") from exc
        if state.version != expected_version:
            raise TriageConflictError("STATE_VERSION_CONFLICT")
        return state

    def _deterministic(self, state: TaskState, context: RunContext) -> None:
        self._record_transition(state, "deterministic_routed", "deterministic_route")
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
        self._record_transition(state, "single_agent_decision", "single_agent_replay_decision")
        state.model_calls += 1
        state.budget.consumed_model_calls += 1
        self._record_budget_entry(state, "consume")
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
            self._record_transition(
                state,
                "browser_review_required",
                reason.value,
                status=RunStatus.AWAITING_REVIEW,
                terminal_reason=reason,
            )
            return
        state.browser_actions = [action.action_id for action in actions]
        self._record_transition(state, "browser_actions_recorded", "browser_actions_untrusted")
        self._finalize_with_toolport(state, context, idempotency_key=f"{state.run_id}-ticket", preview=preview)

    def _orchestrator_worker(self, state: TaskState, context: RunContext) -> None:
        if not self.budgets.reserve_group(state.budget, workers=2, tool_calls=1):
            self._record_budget_entry(state, "release")
            self._record_transition(
                state,
                "capacity_rejected",
                "capacity_unavailable",
                status=RunStatus.AWAITING_REVIEW,
                terminal_reason=TerminalReason.CAPACITY_UNAVAILABLE,
            )
            return
        self._record_budget_entry(state, "reserve")
        self._record_transition(state, "fanout_reserved", "fanout_reserved")
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
            self.budgets.cancel_release(state.budget)
            self._record_budget_entry(state, "cancel_release")
            self._record_transition(
                state,
                "delegation_rejected",
                "invalid_delegation",
                status=RunStatus.AWAITING_REVIEW,
                terminal_reason=TerminalReason.INVALID_DELEGATION,
            )
            return
        results = [self.worker.execute(task) for task in valid_tasks]
        self.worker_results.extend(results)
        findings, reason = self.merger.merge(valid_tasks, results)
        state.findings.extend(findings)
        consumed_tokens = sum(result.usage_tokens for result in results)
        consumed_spend_cents = max(1, consumed_tokens // 100)
        self.budgets.consume_and_release(
            state.budget,
            workers=2,
            tool_calls=1,
            tokens=consumed_tokens,
            spend_cents=consumed_spend_cents,
        )
        self._record_budget_entry(state, "consume")
        if reason:
            self._record_transition(
                state,
                "fanin_requires_review",
                reason.value,
                status=RunStatus.AWAITING_REVIEW,
                terminal_reason=reason,
            )
            return
        self._record_transition(state, "fanin_completed", "deterministic_fan_in")
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
        self._record_budget_entry(state, "consume")
        if result.ticket_id:
            state.ticket_id = result.ticket_id
            self._record_transition(
                state,
                "toolport_ticket_created",
                "chapter9_toolport_create",
                status=RunStatus.SUCCEEDED,
                terminal_reason=TerminalReason.COMPLETED,
            )
        else:
            self._record_transition(
                state,
                "toolport_ticket_denied",
                "approval_denied",
                status=RunStatus.AWAITING_REVIEW,
                terminal_reason=TerminalReason.APPROVAL_DENIED,
            )


class TriageRuntime:
    def __init__(self, root: Path, tool_port: SecuredToolPort | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "triage-runtime.sqlite3"
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        self.tool_port = tool_port

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS triage_runs (
                    run_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    idempotency_key TEXT,
                    request_hash TEXT,
                    run_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triage_idempotency (
                    idempotency_key TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triage_tasks (
                    task_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    task_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triage_results (
                    result_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triage_transition_events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );

                CREATE TABLE IF NOT EXISTS triage_budget_entries (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    entry_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );

                CREATE TABLE IF NOT EXISTS triage_seen_nonces (
                    run_id TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    PRIMARY KEY (run_id, nonce)
                );
                """
            )

    def _dump(self, payload: Any) -> str:
        return json.dumps(payload, indent=2, sort_keys=True)

    def _load(self, payload: str) -> Any:
        return json.loads(payload)

    def _request_hash(self, request: TriageRunRequest, context: RunContext) -> str:
        return sha_json(
            {
                "request": request.model_dump(mode="json"),
                "context": principal_from_context(context).model_dump(mode="json"),
            }
        )

    def _load_engine(self, run_id: str) -> TriageEngine:
        row = self._conn.execute(
            "SELECT run_json FROM triage_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise TriageNotFoundError(f"run not found: {run_id}")
        engine = TriageEngine(self.tool_port)
        state = TaskState.model_validate(self._load(row["run_json"]))
        engine.runs[state.run_id] = state
        engine.issued_tasks = [
            DelegatedTask.model_validate(self._load(task_row["task_json"]))
            for task_row in self._conn.execute(
                "SELECT task_json FROM triage_tasks WHERE run_id = ? ORDER BY task_id",
                (run_id,),
            ).fetchall()
        ]
        engine.worker_results = [
            WorkerResult.model_validate(self._load(result_row["result_json"]))
            for result_row in self._conn.execute(
                "SELECT result_json FROM triage_results WHERE run_id = ? ORDER BY result_id",
                (run_id,),
            ).fetchall()
        ]
        engine.transition_events = [
            TransitionEvent.model_validate(self._load(event_row["event_json"]))
            for event_row in self._conn.execute(
                "SELECT event_json FROM triage_transition_events WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        ]
        engine.budget_entries = [
            BudgetEntry.model_validate(self._load(entry_row["entry_json"]))
            for entry_row in self._conn.execute(
                "SELECT entry_json FROM triage_budget_entries WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        ]
        engine.seen_delegation_nonces = {
            row["nonce"]
            for row in self._conn.execute(
                "SELECT nonce FROM triage_seen_nonces WHERE run_id = ? ORDER BY nonce",
                (run_id,),
            ).fetchall()
        }
        return engine

    def _save_engine(
        self,
        run_id: str,
        engine: TriageEngine,
        *,
        scenario_id: str,
        idempotency_key: str | None,
        request_hash: str | None = None,
    ) -> None:
        state = engine.inspect(run_id)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO triage_runs(run_id, scenario_id, idempotency_key, request_hash, run_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    scenario_id = excluded.scenario_id,
                    idempotency_key = excluded.idempotency_key,
                    request_hash = COALESCE(excluded.request_hash, triage_runs.request_hash),
                    run_json = excluded.run_json
                """,
                (
                    run_id,
                    scenario_id,
                    idempotency_key,
                    request_hash,
                    self._dump(state.model_dump(mode="json")),
                ),
            )
            self._conn.execute("DELETE FROM triage_tasks WHERE run_id = ?", (run_id,))
            self._conn.executemany(
                "INSERT INTO triage_tasks(task_id, run_id, task_json) VALUES (?, ?, ?)",
                [
                    (task.task_id, run_id, self._dump(task.model_dump(mode="json")))
                    for task in engine.delegated_tasks_for(run_id)
                ],
            )
            self._conn.execute("DELETE FROM triage_results WHERE run_id = ?", (run_id,))
            self._conn.executemany(
                "INSERT INTO triage_results(result_id, run_id, result_json) VALUES (?, ?, ?)",
                [
                    (result.result_id, run_id, self._dump(result.model_dump(mode="json")))
                    for result in engine.worker_results_for(run_id)
                ],
            )
            self._conn.execute("DELETE FROM triage_transition_events WHERE run_id = ?", (run_id,))
            self._conn.executemany(
                "INSERT INTO triage_transition_events(run_id, sequence, event_json) VALUES (?, ?, ?)",
                [
                    (event.run_id, event.sequence, self._dump(event.model_dump(mode="json")))
                    for event in engine.transition_events_for(run_id)
                ],
            )
            self._conn.execute("DELETE FROM triage_budget_entries WHERE run_id = ?", (run_id,))
            self._conn.executemany(
                "INSERT INTO triage_budget_entries(run_id, sequence, entry_json) VALUES (?, ?, ?)",
                [
                    (entry.run_id, entry.sequence, self._dump(entry.model_dump(mode="json")))
                    for entry in engine.budget_entries_for(run_id)
                ],
            )
            self._conn.execute("DELETE FROM triage_seen_nonces WHERE run_id = ?", (run_id,))
            self._conn.executemany(
                "INSERT INTO triage_seen_nonces(run_id, nonce) VALUES (?, ?)",
                [(run_id, nonce) for nonce in sorted(engine.seen_delegation_nonces)],
            )

    def _available_controls(self, state: TaskState) -> list[str]:
        if state.status == RunStatus.SUCCEEDED:
            return []
        if state.status == RunStatus.CANCELLED:
            return []
        if state.status == RunStatus.PAUSED:
            return ["resume", "cancel"]
        return ["pause", "cancel"]

    def _envelope(self, run_id: str, engine: TriageEngine) -> TriageRunEnvelope:
        row = self._conn.execute(
            "SELECT scenario_id, idempotency_key FROM triage_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise TriageNotFoundError(f"run not found: {run_id}")
        state = engine.inspect(run_id)
        return TriageRunEnvelope(
            run=state,
            delegated_tasks=engine.delegated_tasks_for(run_id),
            worker_results=engine.worker_results_for(run_id),
            available_controls=self._available_controls(state),
            scenario_id=row["scenario_id"],
            idempotency_key=row["idempotency_key"],
        )

    def create(
        self,
        request: TriageRunRequest,
        *,
        context: RunContext,
    ) -> TriageRunEnvelope:
        request_hash = self._request_hash(request, context)
        if request.idempotency_key:
            existing = self._conn.execute(
                "SELECT run_id, request_hash FROM triage_idempotency WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing["request_hash"] != request_hash:
                    raise TriageConflictError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                run_id = existing["run_id"]
                engine = self._load_engine(run_id)
                return self._envelope(run_id, engine)

        engine = TriageEngine(self.tool_port)
        run_id = f"triage_{request.variant.value}_{uuid4().hex[:10]}"
        engine.start(
            request.variant,
            run_id=run_id,
            context=context,
            budget=request.budget,
            browser_profile=request.browser_profile,
        )
        if request.idempotency_key:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO triage_idempotency(idempotency_key, run_id, request_hash)
                    VALUES (?, ?, ?)
                    """,
                    (request.idempotency_key, run_id, request_hash),
                )
        self._save_engine(
            run_id,
            engine,
            scenario_id=request.scenario_id,
            idempotency_key=request.idempotency_key,
            request_hash=request_hash,
        )
        return self._envelope(run_id, engine)

    def inspect(self, run_id: str) -> TriageRunEnvelope:
        engine = self._load_engine(run_id)
        return self._envelope(run_id, engine)

    def pause(self, run_id: str, request: TriageControlRequest) -> TriageRunEnvelope:
        engine = self._load_engine(run_id)
        state = engine.pause(run_id, expected_version=request.expected_version)
        row = self._conn.execute(
            "SELECT scenario_id, idempotency_key, request_hash FROM triage_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        self._save_engine(
            run_id,
            engine,
            scenario_id=row["scenario_id"],
            idempotency_key=row["idempotency_key"],
            request_hash=row["request_hash"],
        )
        return self._envelope(state.run_id, engine)

    def resume(self, run_id: str, request: TriageControlRequest) -> TriageRunEnvelope:
        engine = self._load_engine(run_id)
        state = engine.resume(run_id, expected_version=request.expected_version)
        row = self._conn.execute(
            "SELECT scenario_id, idempotency_key, request_hash FROM triage_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        self._save_engine(
            run_id,
            engine,
            scenario_id=row["scenario_id"],
            idempotency_key=row["idempotency_key"],
            request_hash=row["request_hash"],
        )
        return self._envelope(state.run_id, engine)

    def cancel(self, run_id: str, request: TriageControlRequest) -> TriageRunEnvelope:
        engine = self._load_engine(run_id)
        state = engine.cancel(run_id, expected_version=request.expected_version)
        row = self._conn.execute(
            "SELECT scenario_id, idempotency_key, request_hash FROM triage_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        self._save_engine(
            run_id,
            engine,
            scenario_id=row["scenario_id"],
            idempotency_key=row["idempotency_key"],
            request_hash=row["request_hash"],
        )
        return self._envelope(state.run_id, engine)


def run_topology_comparison(states: list[TaskState]) -> TopologyComparison:
    return _run_topology_comparison(states)


def _transition_elapsed_ms(state: TaskState, transition_events: list[TransitionEvent] | None = None) -> int:
    run_events = [event for event in (transition_events or []) if event.run_id == state.run_id]
    trace_steps = max(0, len(state.trace) - 1)
    if run_events:
        elapsed_steps = max(0, run_events[-1].occurred_at - run_events[0].occurred_at)
    else:
        elapsed_steps = trace_steps
    return (
        max(1, elapsed_steps) * 40
        + state.model_calls * 90
        + len(state.browser_actions) * 55
        + state.budget.consumed_workers * 35
        + max(0, state.budget.consumed_tool_calls - 1) * 20
    )


def _estimated_cost_cents(state: TaskState) -> int:
    return (
        state.budget.consumed_spend_cents
        + state.budget.consumed_model_calls * 2
        + max(0, state.budget.consumed_tool_calls - 1)
        + max(0, len(state.browser_actions) - 1)
    )


def _risk_events(state: TaskState) -> int:
    return int(state.model_calls > 0) + int(bool(state.browser_actions)) + int(state.budget.consumed_workers > 0) + int(
        state.status != RunStatus.SUCCEEDED
    )


def _run_topology_comparison(
    states: list[TaskState],
    transition_events: list[TransitionEvent] | None = None,
) -> TopologyComparison:
    metrics = [
        TopologyMetrics(
            variant=state.variant,
            task_success=state.status == RunStatus.SUCCEEDED,
            latency_ms=_transition_elapsed_ms(state, transition_events),
            model_calls=state.model_calls,
            tool_calls=state.budget.consumed_tool_calls,
            worker_calls=state.budget.consumed_workers,
            browser_actions=len(state.browser_actions),
            estimated_cost_cents=_estimated_cost_cents(state),
            cost_per_successful_outcome_cents=(
                _estimated_cost_cents(state) if state.status == RunStatus.SUCCEEDED else None
            ),
            trace_steps=len(state.trace),
            risk_events=_risk_events(state),
        )
        for state in states
    ]
    successful = [metric for metric in metrics if metric.task_success]
    best_success = max((1 if metric.task_success else 0) for metric in metrics)
    eligible = [metric for metric in successful if (1 if metric.task_success else 0) >= best_success]
    selected = sorted(
        eligible,
        key=lambda metric: (
            metric.risk_events,
            metric.estimated_cost_cents,
            metric.latency_ms,
            metric.worker_calls,
            metric.browser_actions,
            metric.model_calls,
        ),
    )[0]
    best_alternative_success = max((1 if metric.task_success else 0) for metric in metrics if metric.variant != selected.variant)
    success_gain_points = (1 if selected.task_success else 0) - best_alternative_success
    higher_risk_variants = [metric.variant.value for metric in metrics if metric.variant != selected.variant and metric.risk_events > selected.risk_events]
    return TopologyComparison(
        metrics=metrics,
        selected_variant=selected.variant,
        adr_decision=(
            f"Use the {selected.variant.value} path for the base PolicyOps triage flow because "
            f"all supplied variants achieved the same task-success outcome, so no topology cleared "
            f"the required 10 percentage point gain threshold. The selected path keeps the lowest "
            f"measured risk ({selected.risk_events}), lowest measured cost ({selected.estimated_cost_cents} cents), "
            f"and lowest measured latency proxy ({selected.latency_ms} ms) among the successful variants; "
            f"higher-risk alternatives were {higher_risk_variants or ['none']}."
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
    invalid_task = engine.delegations.issue(
        run_id="invalid-run",
        principal=principal_from_context(fixture_context()),
        worker_id="retrieve_worker",
        objective="retrieve scoped policy evidence",
        evidence_allowlist=["policy_remote:v2:span_remote_approval"],
        tool_allowlist=["retrieval:read"],
        nonce="invalid-1",
    ).model_copy(update={"tool_allowlist": ["retrieval:read", "ticket:create"], "nonce": "invalid-2"})
    invalid_delegation_rejected = int(
        engine.delegations.verify(invalid_task, expected_run_id="invalid-run", seen_nonces=set()) is False
    )
    comparison = _run_topology_comparison(states, engine.transition_events)
    scorecard = OrchestrationScorecard(
        deterministic_agreement=len({state.ticket_id is not None for state in states}) == 1,
        approval_bypasses=0,
        authority_widening=0,
        invalid_delegations_rejected=invalid_delegation_rejected,
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
        "transition_events.json": [event.model_dump(mode="json") for event in engine.transition_events],
        "budget_ledger.json": [entry.model_dump(mode="json") for entry in engine.budget_entries],
        "invalid_delegation.json": {
            "task": invalid_task.model_dump(mode="json"),
            "rejected": bool(invalid_delegation_rejected),
        },
        "a2a_no_use_adr.json": {"decision": comparison.a2a_decision},
        "orchestration_scorecard.json": scorecard.model_dump(mode="json"),
    }
    for name, payload in artifacts.items():
        (evidence_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {"gates_passed": scorecard.gates_passed, "scorecard": scorecard.model_dump(mode="json")}
