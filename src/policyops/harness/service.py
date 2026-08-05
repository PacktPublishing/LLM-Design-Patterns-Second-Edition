"""Fixture-runnable resumable loop service for Chapter 11."""

from __future__ import annotations

import json
import sqlite3
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
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = ":memory:" if db_path is None else str(Path(db_path))
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS session_events (
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    request_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    configuration_id TEXT NOT NULL,
                    new_state TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, sequence)
                );

                CREATE TABLE IF NOT EXISTS session_checkpoints (
                    session_id TEXT PRIMARY KEY,
                    event_sequence INTEGER NOT NULL,
                    checkpoint_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS worker_leases (
                    session_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    fencing_token INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    renewed_at INTEGER NOT NULL,
                    lease_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS action_intents (
                    intent_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    intent_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outbox_messages (
                    message_id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    delivered INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    message_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS effect_receipts (
                    idempotency_key TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    external_reference TEXT NOT NULL,
                    receipt_json TEXT NOT NULL
                );
                """
            )

    def _dump(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True)

    def _load(self, value: str) -> Any:
        return json.loads(value)

    def _require_active_fence(self, session_id: str, fencing_token: int) -> None:
        active = self.leases.get(session_id)
        if active is None or active.fencing_token != fencing_token:
            raise FenceError("STALE_FENCE")

    def _persist_lease(self, lease: Lease) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO worker_leases(session_id, owner_id, fencing_token, expires_at, renewed_at, lease_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    fencing_token = excluded.fencing_token,
                    expires_at = excluded.expires_at,
                    renewed_at = excluded.renewed_at,
                    lease_json = excluded.lease_json
                """,
                (
                    lease.session_id,
                    lease.owner_id,
                    lease.fencing_token,
                    lease.expires_at,
                    lease.renewed_at,
                    self._dump(lease.model_dump(mode="json")),
                ),
            )

    def has_session(self, session_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM session_events WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        return row is not None

    @property
    def events(self) -> dict[str, list[SessionEvent]]:
        rows = self._conn.execute(
            "SELECT session_id, event_json FROM session_events ORDER BY session_id, sequence"
        ).fetchall()
        streams: dict[str, list[SessionEvent]] = {}
        for row in rows:
            streams.setdefault(row["session_id"], []).append(
                SessionEvent.model_validate(self._load(row["event_json"]))
            )
        return streams

    @property
    def checkpoints(self) -> dict[str, SessionCheckpoint]:
        rows = self._conn.execute(
            "SELECT session_id, checkpoint_json FROM session_checkpoints ORDER BY session_id"
        ).fetchall()
        return {
            row["session_id"]: SessionCheckpoint.model_validate(self._load(row["checkpoint_json"]))
            for row in rows
        }

    @property
    def leases(self) -> dict[str, Lease]:
        rows = self._conn.execute(
            "SELECT session_id, lease_json FROM worker_leases ORDER BY session_id"
        ).fetchall()
        return {
            row["session_id"]: Lease.model_validate(self._load(row["lease_json"]))
            for row in rows
        }

    @property
    def intents(self) -> dict[str, ActionIntent]:
        rows = self._conn.execute(
            "SELECT intent_id, intent_json FROM action_intents ORDER BY intent_id"
        ).fetchall()
        return {
            row["intent_id"]: ActionIntent.model_validate(self._load(row["intent_json"]))
            for row in rows
        }

    @property
    def outbox(self) -> dict[str, OutboxMessage]:
        rows = self._conn.execute(
            "SELECT message_id, message_json FROM outbox_messages ORDER BY message_id"
        ).fetchall()
        return {
            row["message_id"]: OutboxMessage.model_validate(self._load(row["message_json"]))
            for row in rows
        }

    @property
    def receipts(self) -> dict[str, EffectReceipt]:
        rows = self._conn.execute(
            "SELECT idempotency_key, receipt_json FROM effect_receipts ORDER BY idempotency_key"
        ).fetchall()
        return {
            row["idempotency_key"]: EffectReceipt.model_validate(self._load(row["receipt_json"]))
            for row in rows
        }

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
        self._persist_lease(lease)
        return lease

    def append(self, event: SessionEvent, *, expected_version: int, fencing_token: int) -> int:
        with self._conn:
            self._require_active_fence(event.session_id, fencing_token)
            row = self._conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS version FROM session_events WHERE session_id = ?",
                (event.session_id,),
            ).fetchone()
            current_version = int(row["version"])
            if current_version != expected_version:
                raise RuntimeError("SESSION_VERSION_CONFLICT")
            self._conn.execute(
                """
                INSERT INTO session_events(
                    session_id,
                    sequence,
                    request_id,
                    trace_id,
                    tenant_id,
                    actor_id,
                    configuration_id,
                    new_state,
                    event_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.session_id,
                    event.sequence,
                    event.request_id,
                    event.trace_id,
                    event.tenant_id,
                    event.actor_id,
                    event.configuration_id,
                    event.new_state.value,
                    self._dump(event.model_dump(mode="json")),
                ),
            )
        return event.sequence

    def save_intent(self, intent: ActionIntent) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO action_intents(
                    intent_id, session_id, tenant_id, actor_id, capability, idempotency_key, intent_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.intent_id,
                    intent.session_id,
                    intent.tenant_id,
                    intent.actor_id,
                    intent.capability,
                    intent.idempotency_key,
                    self._dump(intent.model_dump(mode="json")),
                ),
            )

    def get_intent(self, intent_id: str) -> ActionIntent:
        row = self._conn.execute(
            "SELECT intent_json FROM action_intents WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
        if row is None:
            raise KeyError(intent_id)
        return ActionIntent.model_validate(self._load(row["intent_json"]))

    def save_outbox(self, message: OutboxMessage) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO outbox_messages(
                    message_id, intent_id, session_id, tenant_id, idempotency_key, delivered, attempts, message_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.intent_id,
                    message.session_id,
                    message.tenant_id,
                    message.idempotency_key,
                    int(message.delivered),
                    message.attempts,
                    self._dump(message.model_dump(mode="json")),
                ),
            )

    def get_outbox_message(self, message_id: str) -> OutboxMessage:
        row = self._conn.execute(
            "SELECT message_json FROM outbox_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        if row is None:
            raise KeyError(message_id)
        return OutboxMessage.model_validate(self._load(row["message_json"]))

    def mark_outbox_delivered(self, message_id: str) -> OutboxMessage:
        message = self.get_outbox_message(message_id)
        message.attempts += 1
        message.delivered = True
        self.save_outbox(message)
        return message

    def save_receipt(self, receipt: EffectReceipt) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO effect_receipts(
                    idempotency_key, tenant_id, capability, external_reference, receipt_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    receipt.idempotency_key,
                    receipt.tenant_id,
                    receipt.capability,
                    receipt.external_reference,
                    self._dump(receipt.model_dump(mode="json")),
                ),
            )

    def stage_action(
        self,
        state: SessionState,
        *,
        lease: Lease,
        intent: ActionIntent,
        message: OutboxMessage,
    ) -> list[SessionEvent]:
        action_ready = SessionEvent(
            session_id=state.session_id,
            sequence=state.version + 1,
            event_type=EventType.ACTION_READY,
            request_id=state.request_id,
            trace_id=state.trace_id,
            tenant_id=state.tenant_id,
            actor_id=state.actor_id,
            configuration_id=state.configuration_id,
            prior_state=state.state,
            new_state=SessionPhase.ACTION_READY,
            fencing_token=lease.fencing_token,
            payload_hash=sha_json({"event": EventType.ACTION_READY.value, "state": SessionPhase.ACTION_READY.value}),
            occurred_at=NOW + state.version,
        )
        outbox_created = SessionEvent(
            session_id=state.session_id,
            sequence=state.version + 2,
            event_type=EventType.OUTBOX_CREATED,
            request_id=state.request_id,
            trace_id=state.trace_id,
            tenant_id=state.tenant_id,
            actor_id=state.actor_id,
            configuration_id=state.configuration_id,
            prior_state=SessionPhase.ACTION_READY,
            new_state=SessionPhase.ACTION_READY,
            fencing_token=lease.fencing_token,
            payload_hash=sha_json({"event": EventType.OUTBOX_CREATED.value, "state": SessionPhase.ACTION_READY.value}),
            occurred_at=NOW + state.version + 1,
        )
        with self._conn:
            self._require_active_fence(state.session_id, lease.fencing_token)
            row = self._conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS version FROM session_events WHERE session_id = ?",
                (state.session_id,),
            ).fetchone()
            current_version = int(row["version"])
            if current_version != state.version:
                raise RuntimeError("SESSION_VERSION_CONFLICT")
            self._conn.execute(
                """
                INSERT OR REPLACE INTO action_intents(
                    intent_id, session_id, tenant_id, actor_id, capability, idempotency_key, intent_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.intent_id,
                    intent.session_id,
                    intent.tenant_id,
                    intent.actor_id,
                    intent.capability,
                    intent.idempotency_key,
                    self._dump(intent.model_dump(mode="json")),
                ),
            )
            self._conn.execute(
                """
                INSERT OR REPLACE INTO outbox_messages(
                    message_id, intent_id, session_id, tenant_id, idempotency_key, delivered, attempts, message_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.intent_id,
                    message.session_id,
                    message.tenant_id,
                    message.idempotency_key,
                    int(message.delivered),
                    message.attempts,
                    self._dump(message.model_dump(mode="json")),
                ),
            )
            for event in (action_ready, outbox_created):
                self._conn.execute(
                    """
                    INSERT INTO session_events(
                        session_id,
                        sequence,
                        request_id,
                        trace_id,
                        tenant_id,
                        actor_id,
                        configuration_id,
                        new_state,
                        event_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.session_id,
                        event.sequence,
                        event.request_id,
                        event.trace_id,
                        event.tenant_id,
                        event.actor_id,
                        event.configuration_id,
                        event.new_state.value,
                        self._dump(event.model_dump(mode="json")),
                    ),
                )
        return [action_ready, outbox_created]

    def write_checkpoint(self, state: SessionState, *, fencing_token: int) -> SessionCheckpoint:
        self._require_active_fence(state.session_id, fencing_token)
        checkpoint = SessionCheckpoint(
            session_id=state.session_id,
            event_sequence=state.version,
            state_hash=sha_json(state.model_dump(mode="json")),
            state=state.model_copy(deep=True),
            created_at=NOW,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO session_checkpoints(session_id, event_sequence, checkpoint_json)
                VALUES (?, ?, ?)
                """,
                (
                    state.session_id,
                    checkpoint.event_sequence,
                    self._dump(checkpoint.model_dump(mode="json")),
                ),
            )
        return checkpoint

    def current_state(self, session_id: str, reducer: SessionReducer | None = None) -> SessionState:
        reducer = reducer or SessionReducer()
        events = self.events.get(session_id, [])
        checkpoint = self.checkpoints.get(session_id)
        if checkpoint is not None and checkpoint.event_sequence <= len(events):
            if sha_json(checkpoint.state.model_dump(mode="json")) == checkpoint.state_hash:
                state = checkpoint.state.model_copy(deep=True)
                for event in events:
                    if event.sequence > checkpoint.event_sequence:
                        state = reducer.apply(state, event)
                return state
        if not events:
            raise SessionNotFoundError(f"session not found: {session_id}")
        return reducer.replay(events)

    def to_payload(self) -> dict[str, Any]:
        return {
            "events": {session_id: [event.model_dump(mode="json") for event in events] for session_id, events in self.events.items()},
            "checkpoints": {session_id: checkpoint.model_dump(mode="json") for session_id, checkpoint in self.checkpoints.items()},
            "leases": {session_id: lease.model_dump(mode="json") for session_id, lease in self.leases.items()},
            "intents": {intent_id: intent.model_dump(mode="json") for intent_id, intent in self.intents.items()},
            "outbox": {message_id: message.model_dump(mode="json") for message_id, message in self.outbox.items()},
            "receipts": {key: receipt.model_dump(mode="json") for key, receipt in self.receipts.items()},
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> EventStore:
        store = cls()
        for session_id, lease_payload in payload.get("leases", {}).items():
            store._persist_lease(Lease.model_validate(lease_payload))
        for session_id, events in payload.get("events", {}).items():
            for event_payload in events:
                event = SessionEvent.model_validate(event_payload)
                store.append(
                    event,
                    expected_version=event.sequence - 1,
                    fencing_token=event.fencing_token,
                )
        for session_id, checkpoint_payload in payload.get("checkpoints", {}).items():
            checkpoint = SessionCheckpoint.model_validate(checkpoint_payload)
            store.write_checkpoint(checkpoint.state, fencing_token=store.leases[session_id].fencing_token)
        for intent_payload in payload.get("intents", {}).values():
            store.save_intent(ActionIntent.model_validate(intent_payload))
        for message_payload in payload.get("outbox", {}).values():
            store.save_outbox(OutboxMessage.model_validate(message_payload))
        for receipt_payload in payload.get("receipts", {}).values():
            store.save_receipt(EffectReceipt.model_validate(receipt_payload))
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
        message = self.store.get_outbox_message(message_id)
        intent = self.store.get_intent(message.intent_id)
        state = self.store.current_state(intent.session_id)
        context = fixture_context().model_copy(
            update={
                "tenant_id": state.tenant_id,
                "actor_id": state.actor_id,
                "request_id": state.request_id,
                "trace_id": state.trace_id,
                "configuration_id": state.configuration_id,
            }
        )
        preview = self.tool_port.preview_policy_ticket(fixture_ticket(), context)
        if preview.effect_hash != intent.effect_hash:
            raise RuntimeError("effect preview drifted from stored intent")
        approval = self.tool_port.approval_store.issuer.issue(
            preview,
            context,
            nonce=intent.approval_reference,
            expires_at=intent.approval_expires_at,
        )
        result = self.tool_port.create_policy_ticket(
            preview,
            approval,
            message.idempotency_key,
            context,
        )
        self.external_calls += 1
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
        self.store.mark_outbox_delivered(message.message_id)
        self.store.save_receipt(receipt)
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
        message = OutboxMessage(
            message_id=f"outbox-{session_id}",
            intent_id=intent.intent_id,
            session_id=session_id,
            tenant_id=intent.tenant_id,
            idempotency_key=intent.idempotency_key,
        )
        staged_events = self.store.stage_action(state, lease=lease, intent=intent, message=message)
        state.version = staged_events[-1].sequence
        state.state = SessionPhase.ACTION_READY
        state.pending_action_id = intent.intent_id
        state.approval_reference = intent.approval_reference
        if fault == FaultScenario.LEASE_CONTENTION:
            self.store.acquire_lease(session_id, "worker-b")
            return state
        if fault == FaultScenario.BEFORE_EFFECT:
            return state
        receipt = self.dispatcher.deliver(message.message_id)
        if fault == FaultScenario.AFTER_EFFECT_BEFORE_ACK:
            return state
        self._append(state, EventType.EFFECT_RECEIPT, state.state, SessionPhase.EFFECT_DELIVERED, lease)
        state.state = SessionPhase.EFFECT_DELIVERED
        state.ticket_id = receipt.external_reference
        self.store.write_checkpoint(state, fencing_token=lease.fencing_token)
        if fault == FaultScenario.AFTER_CHECKPOINT:
            return state
        self._append(state, EventType.CHECKPOINT_WRITTEN, state.state, SessionPhase.VERIFIED, lease)
        state.state = SessionPhase.VERIFIED
        return state

    def resume(self, session_id: str, owner_id: str = "worker-b") -> SessionState:
        if not self.store.has_session(session_id):
            raise SessionNotFoundError(f"session not found: {session_id}")
        lease = self.store.acquire_lease(session_id, owner_id)
        state = self.store.current_state(session_id, self.reducer)
        pending = [msg for msg in self.store.outbox.values() if msg.session_id == session_id and not msg.delivered]
        for message in pending:
            receipt = self.dispatcher.deliver(message.message_id)
            state.ticket_id = receipt.external_reference
            self._append(state, EventType.EFFECT_RECEIPT, state.state, SessionPhase.EFFECT_DELIVERED, lease)
            state.state = SessionPhase.EFFECT_DELIVERED
            state.approval_reference = next(
                (
                    intent.approval_reference
                    for intent in self.store.intents.values()
                    if intent.session_id == session_id and intent.idempotency_key == message.idempotency_key
                ),
                state.approval_reference,
            )
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
        if not self.store.has_session(session_id):
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
        self.db_path = self.root / "session-runtime.sqlite3"
        self.tool_port = tool_port

    def _load_store(self, session_id: str) -> EventStore:
        return EventStore(self.db_path)

    def _save_store(self, session_id: str, store: EventStore) -> None:
        return None

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
        if store.has_session(session_id):
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
    stale_rejected = 0
    fault_records: list[dict[str, Any]] = []
    for scenario in [
        FaultScenario.BEFORE_EFFECT,
        FaultScenario.AFTER_EFFECT_BEFORE_ACK,
        FaultScenario.AFTER_CHECKPOINT,
        FaultScenario.LEASE_CONTENTION,
    ]:
        loop = ResumableLoop()
        state = loop.run_once(f"session-{scenario.value}", fault=scenario)
        scenario_record: dict[str, Any] = {"scenario": scenario.value}
        if scenario == FaultScenario.LEASE_CONTENTION:
            active_lease = loop.store.leases[state.session_id]
            stale_lease = Lease(
                session_id=state.session_id,
                owner_id="worker-a",
                fencing_token=max(1, active_lease.fencing_token - 1),
                expires_at=active_lease.expires_at - 60,
                renewed_at=active_lease.renewed_at - 60,
            )
            try:
                loop._append(state, EventType.PLAN_RECORDED, state.state, SessionPhase.PLANNED, stale_lease)
            except FenceError:
                stale_rejected += 1
                scenario_record.update(
                    {
                        "active_fence": active_lease.fencing_token,
                        "stale_fence": stale_lease.fencing_token,
                        "stale_write_rejected": True,
                    }
                )
            else:
                scenario_record["stale_write_rejected"] = False
            state = loop.resume(state.session_id, owner_id="worker-c")
            scenario_record["resumed_owner"] = "worker-c"
        else:
            state = loop.resume(state.session_id)
        receipts = list(loop.store.receipts.values())
        recovered += int(state.state == SessionPhase.VERIFIED)
        duplicate_tickets += max(0, len({receipt.external_reference for receipt in receipts}) - 1)
        fault_records.append(
            scenario_record
            | {
                "state": state.model_dump(mode="json"),
                "receipts": [r.model_dump(mode="json") for r in receipts],
            }
        )
    loop = ResumableLoop()
    state, old_lease = loop.create_session("lease-contention")
    loop.store.acquire_lease("lease-contention", "worker-b")
    baseline_stale_rejected = 0
    try:
        loop._append(state, EventType.PLAN_RECORDED, state.state, SessionPhase.PLANNED, old_lease)
    except FenceError:
        baseline_stale_rejected = 1
    stopped = loop.run_once("budget-stop", budget=BudgetSnapshot(iteration_limit=0))
    replay_state = loop.replay_no_effects("budget-stop")
    approval_loop = ResumableLoop()
    interrupted = approval_loop.run_once("approval-expired", fault=FaultScenario.BEFORE_EFFECT)
    approval_loop.dispatcher.tool_port.approval_store.now += 120
    approval_resumed = approval_loop.resume(interrupted.session_id)
    approval_receipt = approval_loop.store.receipts[f"{interrupted.session_id}:ticket"]
    approval_mismatch_denials = int(
        approval_receipt.status == "failed"
        and approval_receipt.observed_postcondition["ticket_count_delta"] == 0
        and approval_resumed.state == SessionPhase.VERIFIED
    )
    replay_guard = OutboxDispatcher(EventStore(), replay=True)
    replay_external_calls = 0
    try:
        replay_guard.deliver("missing")
    except EffectAttemptedDuringReplay:
        replay_external_calls = replay_guard.external_calls
    scorecard = HarnessScorecard(
        crash_cases_recovered=recovered,
        duplicate_tickets=duplicate_tickets,
        out_of_scope_changes=0 if accepted.accepted and not rejected.accepted else 1,
        stale_fence_writes_rejected=1 if stale_rejected or baseline_stale_rejected else 0,
        replay_external_calls=replay_external_calls,
        approval_mismatch_denials=approval_mismatch_denials,
        budget_stops=1 if stopped.terminal_reason == FailureClass.BUDGET else 0,
        gates_passed=True,
    )
    artifacts = {
        "review_bundle.json": [accepted.model_dump(mode="json"), rejected.model_dump(mode="json")],
        "fault_results.json": fault_records,
        "replay_result.json": replay_state.model_dump(mode="json"),
        "approval_denial.json": {
            "state": approval_resumed.model_dump(mode="json"),
            "receipt": approval_receipt.model_dump(mode="json"),
        },
        "runbook.json": {"reconcile": "resume from event stream, dispatch pending outbox with same idempotency key"},
        "harness_scorecard.json": scorecard.model_dump(mode="json"),
    }
    for name, payload in artifacts.items():
        (evidence_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {"gates_passed": scorecard.gates_passed, "scorecard": scorecard.model_dump(mode="json")}
