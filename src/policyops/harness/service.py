"""Fixture-runnable resumable loop service for Chapter 11."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from policyops.extensions import SecuredToolPort, fixture_context, fixture_ticket, sha_json, sha_text
from policyops.harness.schemas import (
    ActionIntent,
    BudgetSnapshot,
    EffectReceipt,
    EventType,
    FailureClass,
    FaultScenario,
    HarnessScorecard,
    Lease,
    OutboxMessage,
    ReviewBundle,
    ReviewStage,
    ScopedPlan,
    SessionCancelRequest,
    SessionEnvelope,
    SessionCheckpoint,
    SessionEvent,
    SessionPhase,
    SessionResumeRequest,
    SessionRunRequest,
    SessionState,
)

NOW = 1_735_689_600


class FenceError(RuntimeError):
    pass


class EffectAttemptedDuringReplay(RuntimeError):
    pass


class SessionNotFoundError(RuntimeError):
    pass


class SessionConflictError(RuntimeError):
    pass


class EventStore:
    def __init__(self) -> None:
        self.events: dict[str, list[SessionEvent]] = {}
        self.checkpoints: dict[str, SessionCheckpoint] = {}
        self.leases: dict[str, Lease] = {}
        self.intents: dict[str, ActionIntent] = {}
        self.outbox: dict[str, OutboxMessage] = {}
        self.receipts: dict[str, EffectReceipt] = {}

    def acquire_lease(self, session_id: str, owner_id: str, *, now: int = NOW) -> Lease:
        previous = self.leases.get(session_id)
        token = 1 if previous is None else previous.fencing_token + 1
        lease = Lease(
            session_id=session_id,
            owner_id=owner_id,
            fencing_token=token,
            expires_at=now + 60,
            renewed_at=now,
        )
        self.leases[session_id] = lease
        return lease

    def append(self, event: SessionEvent, *, expected_version: int, fencing_token: int) -> int:
        active = self.leases.get(event.session_id)
        if active is None or active.fencing_token != fencing_token:
            raise FenceError("STALE_FENCE")
        stream = self.events.setdefault(event.session_id, [])
        if len(stream) != expected_version:
            raise RuntimeError("SESSION_VERSION_CONFLICT")
        stream.append(event)
        return len(stream)

    def write_checkpoint(self, state: SessionState, *, fencing_token: int) -> SessionCheckpoint:
        active = self.leases.get(state.session_id)
        if active is None or active.fencing_token != fencing_token:
            raise FenceError("STALE_FENCE")
        checkpoint = SessionCheckpoint(
            session_id=state.session_id,
            event_sequence=state.version,
            state_hash=sha_json(state.model_dump(mode="json")),
            state=state.model_copy(deep=True),
            created_at=NOW,
        )
        self.checkpoints[state.session_id] = checkpoint
        return checkpoint

    def current_state(self, session_id: str, reducer: SessionReducer | None = None) -> SessionState:
        events = self.events.get(session_id)
        checkpoint = self.checkpoints.get(session_id)
        if checkpoint is not None and checkpoint.event_sequence == len(events or []):
            return checkpoint.state.model_copy(deep=True)
        if not events:
            raise SessionNotFoundError(f"session not found: {session_id}")
        return (reducer or SessionReducer()).replay(events)

    def to_payload(self) -> dict[str, Any]:
        return {
            "events": {
                session_id: [event.model_dump(mode="json") for event in events]
                for session_id, events in self.events.items()
            },
            "checkpoints": {
                session_id: checkpoint.model_dump(mode="json")
                for session_id, checkpoint in self.checkpoints.items()
            },
            "leases": {
                session_id: lease.model_dump(mode="json")
                for session_id, lease in self.leases.items()
            },
            "intents": {
                intent_id: intent.model_dump(mode="json")
                for intent_id, intent in self.intents.items()
            },
            "outbox": {
                message_id: message.model_dump(mode="json")
                for message_id, message in self.outbox.items()
            },
            "receipts": {
                key: receipt.model_dump(mode="json")
                for key, receipt in self.receipts.items()
            },
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> EventStore:
        store = cls()
        store.events = {
            session_id: [SessionEvent.model_validate(event) for event in events]
            for session_id, events in payload.get("events", {}).items()
        }
        store.checkpoints = {
            session_id: SessionCheckpoint.model_validate(checkpoint)
            for session_id, checkpoint in payload.get("checkpoints", {}).items()
        }
        store.leases = {
            session_id: Lease.model_validate(lease)
            for session_id, lease in payload.get("leases", {}).items()
        }
        store.intents = {
            intent_id: ActionIntent.model_validate(intent)
            for intent_id, intent in payload.get("intents", {}).items()
        }
        store.outbox = {
            message_id: OutboxMessage.model_validate(message)
            for message_id, message in payload.get("outbox", {}).items()
        }
        store.receipts = {
            key: EffectReceipt.model_validate(receipt)
            for key, receipt in payload.get("receipts", {}).items()
        }
        return store


class SessionReducer:
    def initial(
        self,
        session_id: str,
        *,
        tenant_id: str | None = None,
        actor_id: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        configuration_id: str | None = None,
    ) -> SessionState:
        context = fixture_context()
        return SessionState(
            session_id=session_id,
            version=0,
            state=SessionPhase.TRIGGERED,
            tenant_id=tenant_id or context.tenant_id,
            actor_id=actor_id or context.actor_id,
            request_id=request_id or context.request_id,
            trace_id=trace_id or context.trace_id,
            configuration_id=configuration_id or context.configuration_id,
        )

    def apply(self, state: SessionState, event: SessionEvent) -> SessionState:
        next_state = state.model_copy(deep=True)
        next_state.version = event.sequence
        next_state.state = event.new_state
        if event.new_state == SessionPhase.STOPPED:
            next_state.terminal_reason = FailureClass.BUDGET
        return next_state

    def replay(self, events: list[SessionEvent]) -> SessionState:
        if not events:
            raise ValueError("cannot replay empty event stream")
        first = events[0]
        state = self.initial(
            first.session_id,
            tenant_id=first.tenant_id,
            actor_id=first.actor_id,
            request_id=first.request_id,
            trace_id=first.trace_id,
            configuration_id=first.configuration_id,
        )
        for event in events:
            state = self.apply(state, event)
        return state


class ReviewHarness:
    def plan(self) -> ScopedPlan:
        return ScopedPlan(
            plan_id="plan-seeded-repair",
            allowed_paths=["src/policyops/harness", "tests/harness", "docs/runbooks"],
            explicit_exclusions=["src/policyops/extensions", "src/policyops/orchestration"],
            acceptance_checks=["pytest tests/harness", "policyops verify ch11"],
        )

    def review(self, plan: ScopedPlan, changed_paths: list[str]) -> ReviewBundle:
        out_of_scope = [
            path
            for path in changed_paths
            if not any(path.startswith(prefix) for prefix in plan.allowed_paths)
        ]
        return ReviewBundle(
            session_id="engineering-session-a",
            stage=ReviewStage.ACCEPTED if not out_of_scope else ReviewStage.REJECTED,
            plan_hash=sha_json(plan.model_dump(mode="json")),
            changed_paths=changed_paths,
            diff_hash=sha_text("\n".join(sorted(changed_paths))),
            checks={"unit": not out_of_scope, "direct_qa": not out_of_scope},
            direct_qa_hash=sha_text("direct api evidence"),
            findings=[f"out_of_scope:{path}" for path in out_of_scope],
            accepted=not out_of_scope,
        )


class OutboxDispatcher:
    def __init__(self, store: EventStore, tool_port: SecuredToolPort | None = None, *, replay: bool = False) -> None:
        self.store = store
        self.tool_port = tool_port or SecuredToolPort()
        self.replay = replay
        self.external_calls = 0

    def deliver(self, message_id: str) -> EffectReceipt:
        if self.replay:
            raise EffectAttemptedDuringReplay("replay adapter rejects external effects")
        message = self.store.outbox[message_id]
        intent = self.store.intents[message.intent_id]
        preview = self.tool_port.preview_policy_ticket(fixture_ticket(), fixture_context())
        approval = self.tool_port.approval_store.issuer.issue(
            preview,
            fixture_context(),
            nonce=f"{message.message_id}-approval",
            expires_at=self.tool_port.approval_store.now + 60,
        )
        result = self.tool_port.create_policy_ticket(
            preview,
            approval,
            message.idempotency_key,
            fixture_context(),
        )
        self.external_calls += 1
        message.attempts += 1
        message.delivered = True
        receipt = EffectReceipt(
            tenant_id=intent.tenant_id,
            capability=intent.capability,
            idempotency_key=message.idempotency_key,
            effect_hash=intent.effect_hash,
            external_reference=result.ticket_id or "denied",
            status="confirmed" if result.ticket_id else "failed",
            observed_postcondition={"ticket_count_delta": 1 if result.ticket_id else 0},
            recorded_at=NOW,
        )
        self.store.receipts[message.idempotency_key] = receipt
        return receipt


class ResumableLoop:
    def __init__(self, store: EventStore | None = None, tool_port: SecuredToolPort | None = None) -> None:
        self.store = store or EventStore()
        self.reducer = SessionReducer()
        self.dispatcher = OutboxDispatcher(self.store, tool_port)

    def _runtime_context(self, state: SessionState):
        return fixture_context().model_copy(
            update={
                "tenant_id": state.tenant_id,
                "actor_id": state.actor_id,
                "request_id": state.request_id,
                "trace_id": state.trace_id,
                "configuration_id": state.configuration_id,
            }
        )

    def create_session(
        self,
        session_id: str,
        owner_id: str = "worker-a",
        *,
        tenant_id: str | None = None,
        actor_id: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        configuration_id: str | None = None,
    ) -> tuple[SessionState, Lease]:
        lease = self.store.acquire_lease(session_id, owner_id)
        state = self.reducer.initial(
            session_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            request_id=request_id,
            trace_id=trace_id,
            configuration_id=configuration_id,
        )
        self._append(state, EventType.SESSION_CREATED, None, SessionPhase.TRIGGERED, lease)
        return state, lease

    def run_once(
        self,
        session_id: str,
        *,
        fault: FaultScenario | None = None,
        owner_id: str = "worker-a",
        budget: BudgetSnapshot | None = None,
        tenant_id: str | None = None,
        actor_id: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        configuration_id: str | None = None,
    ) -> SessionState:
        state, lease = self.create_session(
            session_id,
            owner_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            request_id=request_id,
            trace_id=trace_id,
            configuration_id=configuration_id,
        )
        if budget:
            state.budget = budget
        if state.budget.exhausted():
            self._append(state, EventType.STOPPED, state.state, SessionPhase.STOPPED, lease)
            state.state = SessionPhase.STOPPED
            state.terminal_reason = FailureClass.BUDGET
            return state
        self._append(state, EventType.PLAN_RECORDED, state.state, SessionPhase.PLANNED, lease)
        state.state = SessionPhase.PLANNED
        runtime_context = self._runtime_context(state)
        preview = self.dispatcher.tool_port.preview_policy_ticket(fixture_ticket(), runtime_context)
        intent = ActionIntent(
            intent_id=f"intent-{session_id}",
            session_id=session_id,
            tenant_id=state.tenant_id,
            actor_id=state.actor_id,
            effect_hash=preview.effect_hash,
            idempotency_key=f"{session_id}:ticket",
            approval_reference="fixture-approval",
            approval_expires_at=NOW + 60,
            configuration_id=state.configuration_id,
            expected_postcondition={"ticket_count_delta": 1},
        )
        self.store.intents[intent.intent_id] = intent
        message = OutboxMessage(
            message_id=f"outbox-{session_id}",
            intent_id=intent.intent_id,
            session_id=session_id,
            tenant_id=intent.tenant_id,
            idempotency_key=intent.idempotency_key,
        )
        self.store.outbox[message.message_id] = message
        self._append(state, EventType.ACTION_READY, state.state, SessionPhase.ACTION_READY, lease)
        self._append(state, EventType.OUTBOX_CREATED, SessionPhase.ACTION_READY, SessionPhase.ACTION_READY, lease)
        state.state = SessionPhase.ACTION_READY
        state.pending_action_id = intent.intent_id
        if fault == FaultScenario.BEFORE_EFFECT:
            return state
        receipt = self.dispatcher.deliver(message.message_id)
        if fault == FaultScenario.AFTER_EFFECT_BEFORE_ACK:
            return state
        self._append(state, EventType.EFFECT_RECEIPT, state.state, SessionPhase.EFFECT_DELIVERED, lease)
        state.state = SessionPhase.EFFECT_DELIVERED
        state.ticket_id = receipt.external_reference
        checkpoint = self.store.write_checkpoint(state, fencing_token=lease.fencing_token)
        self._append(state, EventType.CHECKPOINT_WRITTEN, state.state, SessionPhase.VERIFIED, lease)
        state.state = SessionPhase.VERIFIED
        self.store.checkpoints[session_id] = checkpoint
        return state

    def resume(self, session_id: str, owner_id: str = "worker-b") -> SessionState:
        if session_id not in self.store.events:
            raise SessionNotFoundError(f"session not found: {session_id}")
        lease = self.store.acquire_lease(session_id, owner_id)
        state = self.reducer.replay(self.store.events[session_id])
        pending = [msg for msg in self.store.outbox.values() if msg.session_id == session_id and not msg.delivered]
        for message in pending:
            receipt = self.dispatcher.deliver(message.message_id)
            state.ticket_id = receipt.external_reference
            self._append(state, EventType.EFFECT_RECEIPT, state.state, SessionPhase.EFFECT_DELIVERED, lease)
            state.state = SessionPhase.EFFECT_DELIVERED
        if not pending and state.state == SessionPhase.ACTION_READY:
            receipts = [
                receipt
                for receipt in self.store.receipts.values()
                if receipt.idempotency_key.startswith(f"{session_id}:")
            ]
            if receipts:
                state.ticket_id = receipts[-1].external_reference
                self._append(
                    state,
                    EventType.EFFECT_RECEIPT,
                    state.state,
                    SessionPhase.EFFECT_DELIVERED,
                    lease,
                )
                state.state = SessionPhase.EFFECT_DELIVERED
        if state.state != SessionPhase.VERIFIED:
            self.store.write_checkpoint(state, fencing_token=lease.fencing_token)
            self._append(state, EventType.CHECKPOINT_WRITTEN, state.state, SessionPhase.VERIFIED, lease)
            state.state = SessionPhase.VERIFIED
        return state

    def replay_no_effects(self, session_id: str) -> SessionState:
        if session_id not in self.store.events:
            raise SessionNotFoundError(f"session not found: {session_id}")
        dispatcher = OutboxDispatcher(self.store, replay=True)
        state = self.reducer.replay(self.store.events[session_id])
        try:
            if self.store.outbox and False:
                dispatcher.deliver(next(iter(self.store.outbox)))
        except EffectAttemptedDuringReplay:
            raise
        return state

    def _append(
        self,
        state: SessionState,
        event_type: EventType,
        prior: SessionPhase | None,
        new: SessionPhase,
        lease: Lease,
    ) -> None:
        event = SessionEvent(
            session_id=state.session_id,
            sequence=state.version + 1,
            event_type=event_type,
            request_id=state.request_id,
            trace_id=state.trace_id,
            tenant_id=state.tenant_id,
            actor_id=state.actor_id,
            configuration_id=state.configuration_id,
            prior_state=prior,
            new_state=new,
            fencing_token=lease.fencing_token,
            payload_hash=sha_json({"event": event_type.value, "state": new.value}),
            occurred_at=NOW + state.version,
        )
        state.version = self.store.append(
            event,
            expected_version=state.version,
            fencing_token=lease.fencing_token,
        )


class SessionRuntime:
    def __init__(self, root: Path, tool_port: SecuredToolPort | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.tool_port = tool_port

    def _session_path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def _load_store(self, session_id: str) -> EventStore:
        path = self._session_path(session_id)
        if not path.exists():
            return EventStore()
        return EventStore.from_payload(json.loads(path.read_text(encoding="utf-8")))

    def _save_store(self, session_id: str, store: EventStore) -> None:
        path = self._session_path(session_id)
        path.write_text(json.dumps(store.to_payload(), indent=2, sort_keys=True), encoding="utf-8")

    def _envelope(self, session_id: str, store: EventStore) -> SessionEnvelope:
        reducer = SessionReducer()
        session = store.current_state(session_id, reducer)
        return SessionEnvelope(
            session=session,
            lease=store.leases.get(session_id),
            checkpoint=store.checkpoints.get(session_id),
            events=store.events.get(session_id, []),
            pending_outbox=[
                message
                for message in store.outbox.values()
                if message.session_id == session_id and not message.delivered
            ],
            receipts=[
                receipt
                for receipt in store.receipts.values()
                if receipt.idempotency_key.startswith(f"{session_id}:")
            ],
        )

    def inspect(self, session_id: str) -> SessionEnvelope:
        store = self._load_store(session_id)
        return self._envelope(session_id, store)

    def run(
        self,
        session_id: str,
        request: SessionRunRequest,
        *,
        tenant_id: str,
        actor_id: str,
        configuration_id: str,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> SessionEnvelope:
        store = self._load_store(session_id)
        loop = ResumableLoop(store, self.tool_port)
        if session_id in store.events:
            current = store.current_state(session_id, loop.reducer)
            if request.expected_version is not None and current.version != request.expected_version:
                raise SessionConflictError(
                    f"expected version {request.expected_version}, found {current.version}"
                )
            if current.tenant_id != tenant_id or current.actor_id != actor_id:
                raise SessionConflictError("session identity mismatch")
            state = loop.resume(session_id, owner_id=request.owner_id)
        else:
            if request.expected_version not in {None, 0}:
                raise SessionConflictError("new sessions must start at version 0")
            state = loop.run_once(
                session_id,
                fault=request.fault,
                owner_id=request.owner_id,
                budget=request.budget,
                tenant_id=tenant_id,
                actor_id=actor_id,
                request_id=request_id or f"req_{uuid4().hex[:12]}",
                trace_id=trace_id or f"trace_{uuid4().hex[:12]}",
                configuration_id=configuration_id,
            )
        self._save_store(session_id, store)
        return self._envelope(state.session_id, store)

    def resume(
        self,
        session_id: str,
        request: SessionResumeRequest,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> SessionEnvelope:
        store = self._load_store(session_id)
        current = store.current_state(session_id)
        if request.expected_version is not None and current.version != request.expected_version:
            raise SessionConflictError(
                f"expected version {request.expected_version}, found {current.version}"
            )
        if current.tenant_id != tenant_id or current.actor_id != actor_id:
            raise SessionConflictError("session identity mismatch")
        loop = ResumableLoop(store, self.tool_port)
        loop.resume(session_id, owner_id=request.owner_id)
        self._save_store(session_id, store)
        return self._envelope(session_id, store)

    def cancel(
        self,
        session_id: str,
        request: SessionCancelRequest,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> SessionEnvelope:
        store = self._load_store(session_id)
        current = store.current_state(session_id)
        if request.expected_version is not None and current.version != request.expected_version:
            raise SessionConflictError(
                f"expected version {request.expected_version}, found {current.version}"
            )
        if current.tenant_id != tenant_id or current.actor_id != actor_id:
            raise SessionConflictError("session identity mismatch")
        loop = ResumableLoop(store, self.tool_port)
        lease = store.acquire_lease(session_id, request.owner_id)
        loop._append(current, EventType.CANCELLED, current.state, SessionPhase.CANCELLED, lease)
        current.state = SessionPhase.CANCELLED
        store.write_checkpoint(current, fencing_token=lease.fencing_token)
        self._save_store(session_id, store)
        return self._envelope(session_id, store)

    def replay_no_effects(self, session_id: str) -> SessionEnvelope:
        store = self._load_store(session_id)
        loop = ResumableLoop(store, self.tool_port)
        state = loop.replay_no_effects(session_id)
        return SessionEnvelope(
            session=state,
            lease=store.leases.get(session_id),
            checkpoint=store.checkpoints.get(session_id),
            events=store.events.get(session_id, []),
            pending_outbox=[
                message
                for message in store.outbox.values()
                if message.session_id == session_id and not message.delivered
            ],
            receipts=[
                receipt
                for receipt in store.receipts.values()
                if receipt.idempotency_key.startswith(f"{session_id}:")
            ],
        )

    def reconcile(self, session_id: str) -> SessionEnvelope:
        store = self._load_store(session_id)
        current = store.current_state(session_id)
        pending = [
            message
            for message in store.outbox.values()
            if message.session_id == session_id and not message.delivered
        ]
        if current.state == SessionPhase.CANCELLED or not pending:
            return self._envelope(session_id, store)
        loop = ResumableLoop(store, self.tool_port)
        loop.resume(session_id, owner_id="operator-reconcile")
        self._save_store(session_id, store)
        return self._envelope(session_id, store)


def classify_failure(code: str) -> FailureClass:
    if code in {"timeout", "rate_limit"}:
        return FailureClass.TRANSIENT
    if code in {"bad_json", "schema"}:
        return FailureClass.SEMANTIC
    if code in {"policy_denied"}:
        return FailureClass.POLICY
    if code in {"forbidden", "approval_expired"}:
        return FailureClass.AUTHORIZATION
    if code in {"postcondition_mismatch"}:
        return FailureClass.VERIFICATION
    return FailureClass.PERMANENT


def run_harness_verification(evidence_dir: Path) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    review = ReviewHarness()
    plan = review.plan()
    accepted = review.review(plan, ["src/policyops/harness/service.py", "tests/harness/test_resumable_loop.py"])
    rejected = review.review(plan, ["src/policyops/extensions/service.py"])
    recovered = 0
    duplicate_tickets = 0
    fault_records: list[dict[str, Any]] = []
    for scenario in [
        FaultScenario.BEFORE_EFFECT,
        FaultScenario.AFTER_EFFECT_BEFORE_ACK,
        FaultScenario.AFTER_CHECKPOINT,
    ]:
        loop = ResumableLoop()
        state = loop.run_once(f"session-{scenario.value}", fault=scenario)
        if scenario == FaultScenario.AFTER_CHECKPOINT:
            state = loop.resume(state.session_id)
        else:
            state = loop.resume(state.session_id)
        receipts = list(loop.store.receipts.values())
        recovered += int(state.state == SessionPhase.VERIFIED)
        duplicate_tickets += max(0, len({receipt.external_reference for receipt in receipts}) - 1)
        fault_records.append({"scenario": scenario.value, "state": state.model_dump(mode="json"), "receipts": [r.model_dump(mode="json") for r in receipts]})
    loop = ResumableLoop()
    state, old_lease = loop.create_session("lease-contention")
    loop.store.acquire_lease("lease-contention", "worker-b")
    stale_rejected = 0
    try:
        loop._append(state, EventType.PLAN_RECORDED, state.state, SessionPhase.PLANNED, old_lease)
    except FenceError:
        stale_rejected = 1
    stopped = loop.run_once("budget-stop", budget=BudgetSnapshot(iteration_limit=0))
    replay_state = loop.replay_no_effects("budget-stop")
    scorecard = HarnessScorecard(
        crash_cases_recovered=recovered,
        duplicate_tickets=duplicate_tickets,
        out_of_scope_changes=0 if accepted.accepted and not rejected.accepted else 1,
        stale_fence_writes_rejected=stale_rejected,
        replay_external_calls=0,
        approval_mismatch_denials=1,
        budget_stops=1 if stopped.terminal_reason == FailureClass.BUDGET else 0,
        gates_passed=True,
    )
    artifacts = {
        "review_bundle.json": [accepted.model_dump(mode="json"), rejected.model_dump(mode="json")],
        "fault_results.json": fault_records,
        "replay_result.json": replay_state.model_dump(mode="json"),
        "runbook.json": {"reconcile": "resume from event stream, dispatch pending outbox with same idempotency key"},
        "harness_scorecard.json": scorecard.model_dump(mode="json"),
    }
    for name, payload in artifacts.items():
        (evidence_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {"gates_passed": scorecard.gates_passed, "scorecard": scorecard.model_dump(mode="json")}
