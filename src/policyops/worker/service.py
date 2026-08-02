"""Worker facade over the Chapter 11 resumable session runtime."""

from __future__ import annotations

from pathlib import Path

from policyops.harness import (
    FaultScenario,
    SessionCancelRequest,
    SessionEnvelope,
    SessionResumeRequest,
    SessionRunRequest,
    SessionRuntime,
)


class SessionWorker:
    def __init__(
        self,
        runtime_root: Path,
        *,
        tenant_id: str,
        actor_id: str,
        configuration_id: str,
        owner_id: str = "worker-a",
    ) -> None:
        self.runtime = SessionRuntime(runtime_root)
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.configuration_id = configuration_id
        self.owner_id = owner_id

    def run(
        self,
        session_id: str,
        *,
        expected_version: int | None = 0,
        fault: FaultScenario | None = None,
    ) -> SessionEnvelope:
        return self.runtime.run(
            session_id,
            SessionRunRequest(
                expected_version=expected_version,
                owner_id=self.owner_id,
                fault=fault,
            ),
            tenant_id=self.tenant_id,
            actor_id=self.actor_id,
            configuration_id=self.configuration_id,
        )

    def resume(self, session_id: str, *, expected_version: int | None = None) -> SessionEnvelope:
        return self.runtime.resume(
            session_id,
            SessionResumeRequest(expected_version=expected_version, owner_id=self.owner_id),
            tenant_id=self.tenant_id,
            actor_id=self.actor_id,
        )

    def cancel(
        self,
        session_id: str,
        *,
        expected_version: int | None = None,
        owner_id: str = "operator-a",
    ) -> SessionEnvelope:
        return self.runtime.cancel(
            session_id,
            SessionCancelRequest(expected_version=expected_version, owner_id=owner_id),
            tenant_id=self.tenant_id,
            actor_id=self.actor_id,
        )

    def inspect(self, session_id: str) -> SessionEnvelope:
        return self.runtime.inspect(session_id)

    def replay_no_effects(self, session_id: str) -> SessionEnvelope:
        return self.runtime.replay_no_effects(session_id)

    def reconcile(self, session_id: str) -> SessionEnvelope:
        return self.runtime.reconcile(session_id)
