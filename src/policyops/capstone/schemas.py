"""Chapter 16 capstone schemas."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CapstoneDecision(str, Enum):
    GO = "GO"
    NO_GO = "NO-GO"


class GameDayStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class TraceabilityClosure(StrictModel):
    chapters_expected: int
    chapters_found: int
    missing_chapters: list[str]
    statuses: dict[str, str]
    commands: dict[str, str]
    rollback_paths_present: bool
    decisions_go: bool
    closed: bool


class GameDayStepResult(StrictModel):
    step: int
    scenario: str
    prerequisite: str
    injection_or_action: str
    expected_result: str
    actual_result: str
    evidence_ref: str
    cleanup_status: Literal["complete", "not_required"]
    mandatory: bool = True
    status: GameDayStatus


class ReleaseBundle(StrictModel):
    bundle_id: str
    traceability_hash: str
    game_day_hash: str
    governance_decision_hash: str
    evidence_hash: str
    signed_by: str
    signature: str


class CapstoneReleaseDecision(StrictModel):
    decision_id: str
    decision: CapstoneDecision
    reasons: list[str] = Field(default_factory=list)
    bundle_hash: str
    seeded_failure_proven: bool


class CapstoneScorecard(StrictModel):
    schema_version: Literal["1"] = "1"
    traceability_closed: bool
    game_day_steps_passed: int
    game_day_steps_expected: int
    mandatory_failures: int
    seeded_failure_returns_no_go: bool
    release_go: bool
    duplicate_tickets: int
    unauthorized_effects: int
    cross_tenant_leaks: int
    secret_leaks: int
    rights_receipt_complete: bool
    evidence_signed: bool
    gates_passed: bool

    @model_validator(mode="after")
    def _hard_gates(self) -> CapstoneScorecard:
        if self.gates_passed and (
            not self.traceability_closed
            or self.game_day_steps_passed != self.game_day_steps_expected
            or self.mandatory_failures
            or not self.seeded_failure_returns_no_go
            or not self.release_go
            or self.duplicate_tickets
            or self.unauthorized_effects
            or self.cross_tenant_leaks
            or self.secret_leaks
            or not self.rights_receipt_complete
            or not self.evidence_signed
        ):
            raise ValueError("capstone cannot pass when any mandatory invariant fails")
        return self
