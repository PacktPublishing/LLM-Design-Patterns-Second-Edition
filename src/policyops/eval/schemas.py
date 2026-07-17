"""Evaluation schemas owned by Chapter 2."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SuiteClass(str, Enum):
    CAPABILITY = "capability"
    REGRESSION = "regression"
    ADVERSARIAL = "adversarial"
    HOLDOUT = "holdout"


class RiskArea(str, Enum):
    ANSWER_SCHEMA = "answer_schema"
    CITATION = "citation"
    AUTHORIZATION = "authorization"
    TOOL_ARGUMENTS = "tool_arguments"
    ABSTENTION = "abstention"
    ADVERSARIAL = "adversarial"


class ReleaseGate(str, Enum):
    ZERO_TOLERANCE = "zero_tolerance"
    THRESHOLD = "threshold"
    INFORMATIONAL = "informational"


class FailureClass(str, Enum):
    CANDIDATE = "candidate"
    TASK_AMBIGUITY = "task_ambiguity"
    GRADER_DEFECT = "grader_defect"
    FIXTURE_NOISE = "fixture_noise"
    INFRASTRUCTURE = "infrastructure"
    UNRESOLVED = "unresolved"


class TaskCase(StrictModel):
    schema_version: Literal["1"] = "1"
    task_id: str
    suite: SuiteClass
    risk: RiskArea
    owner: str = "policyops"
    rationale: str
    input: dict[str, Any]
    expected: dict[str, Any] = Field(default_factory=dict)
    required_evidence: list[str] = Field(default_factory=list)
    forbidden_behavior: list[str] = Field(default_factory=list)
    graders: list[str]
    trials: int = Field(default=1, ge=1, le=10)
    release_gate: ReleaseGate = ReleaseGate.ZERO_TOLERANCE
    stochastic: bool = False
    content_hash: str | None = None


class TrialContext(StrictModel):
    schema_version: Literal["1"] = "1"
    trial_id: str
    task_id: str
    trial_index: int
    seed: int
    configuration_id: str
    candidate_id: str
    profile: str = "fixture"


class TrialRecord(StrictModel):
    schema_version: Literal["1"] = "1"
    trial_id: str
    task_id: str
    candidate_id: str
    status: Literal["ok", "error", "throttled", "timeout"]
    output: dict[str, Any] | None = None
    http_status: int | None = None
    model_invoked: bool = False
    latency_ms: float = 0.0
    usage: dict[str, Any] | None = None
    cost_usd: float | None = None
    error_code: str | None = None
    trace: dict[str, Any] = Field(default_factory=dict)
    infrastructure_status: str = "ok"


class GraderVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class GraderResult(StrictModel):
    schema_version: Literal["1"] = "1"
    grader_id: str
    trial_id: str
    task_id: str
    verdict: GraderVerdict
    score: float | None = None
    reason_code: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class Outcome(StrictModel):
    schema_version: Literal["1"] = "1"
    task_id: str
    trial_id: str
    passed: bool
    failure_class: FailureClass | None = None
    grader_results: list[GraderResult]


class SuiteManifest(StrictModel):
    schema_version: Literal["1"] = "1"
    suite_id: str
    case_ids: list[str]
    grader_versions: dict[str, str]
    thresholds: dict[str, float] = Field(default_factory=dict)
    fixture_version: str = "ch02-v1"
    content_hash: str | None = None


class SuiteSummary(StrictModel):
    schema_version: Literal["1"] = "1"
    suite_id: str
    profile: str
    total_cases: int
    total_trials: int
    passed_trials: int
    pass_rate: float
    first_try_pass_rate: float
    pass_at_k: float | None = None
    pass_hat_k: float | None = None
    cost_per_successful_outcome: float | None = None
    cost_status: Literal["available", "unavailable"] = "unavailable"
    gates_passed: bool
    failure_taxonomy: dict[str, int] = Field(default_factory=dict)
    runtime_ms: float = 0.0
    generated_at: datetime | None = None
