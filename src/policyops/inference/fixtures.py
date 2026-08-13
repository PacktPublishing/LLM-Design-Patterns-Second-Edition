"""Chapter 4 fixture loader — honors the Chapter 2 dependency declared in
`labs/ch04/manifest.toml` (`requires = ["ch01", "ch02", "ch03"]`).

Loads the Chapter 2 eval cases from `evals/cases/{capability,regression,adversarial}/cases.jsonl`
and adapts them into `InferenceRequest` objects so the gateway's routing, budgeting, and gating
logic is exercised against a realistic, checked-in case mix instead of four hand-written
requests.

`evals/**` is owned by the Chapter 2 lab. This module only READS it, never writes.
"""

from __future__ import annotations

from pathlib import Path

from policyops.eval.runner import load_cases
from policyops.eval.schemas import RiskArea, SuiteClass, TaskCase
from policyops.inference.schemas import InferenceRequest, RiskTier, TaskClass

# evals/cases/{capability,regression,adversarial}/cases.jsonl — see labs/ch04/manifest.toml.
EVALS_CASES_ROOT = Path(__file__).resolve().parents[3] / "evals" / "cases"

# Expected counts, asserted on every load. Fail closed (raise) if a suite is missing/empty
# or the counts drift, rather than silently running against a smaller/partial fixture set.
EXPECTED_SUITE_COUNTS: dict[str, int] = {
    SuiteClass.CAPABILITY.value: 10,
    SuiteClass.REGRESSION.value: 15,
    SuiteClass.ADVERSARIAL.value: 6,
}
EXPECTED_RISK_COUNTS: dict[str, int] = {
    "authorization": 10,
    "answer_schema": 9,
    "tool_arguments": 7,
    "abstention": 2,
    "citation": 2,
    "adversarial": 1,
}

# Pure mapping from a case's stable `risk` field onto gateway request shape. `authorization`
# and `citation` line up directly with the Change 2 hard gates: an authorization-risk case is
# adapted as an unauthorized caller (the hard gate must deny it before any model call), and a
# citation-risk case is adapted with citations required (the hard gate's citation-integrity
# check and the quality gate's evidence-alignment check both apply).
_RISK_POLICY: dict[RiskArea, tuple[RiskTier, bool, TaskClass]] = {
    RiskArea.AUTHORIZATION: (RiskTier.HIGH, False, TaskClass.CONTROLLED_ACTION),
    RiskArea.CITATION: (RiskTier.MEDIUM, True, TaskClass.POLICY_QA),
    RiskArea.ANSWER_SCHEMA: (RiskTier.MEDIUM, True, TaskClass.POLICY_QA),
    RiskArea.TOOL_ARGUMENTS: (RiskTier.MEDIUM, False, TaskClass.CONTROLLED_ACTION),
    RiskArea.ABSTENTION: (RiskTier.LOW, False, TaskClass.POLICY_QA),
    RiskArea.ADVERSARIAL: (RiskTier.HIGH, True, TaskClass.POLICY_QA),
}

_BASE_IDENTITY = {
    "tenant_id": "tenant_alpha",
    "actor_id": "actor_reader",
    "authorization_fingerprint": "authz:reader",
    "configuration_hash": "sha256:gateway-fixture",
    "policy_version": "policy-v1",
}


class FixtureLoadError(RuntimeError):
    """Raised when the Chapter 2 case fixtures are missing, empty, or don't match the
    expected shape. The loader fails closed instead of silently running a partial workload."""


def _derive_question(case: TaskCase) -> str:
    """Derive `question` as a pure function of stable case fields.

    These cases carry no top-level `question` field. When the case's `input` already carries
    one (most regression/adversarial cases), it is used as-is. Otherwise `question` is
    synthesized deterministically from the case's `risk` and `input.mode` and `task_id` —
    never randomly, and never via a per-task_id lookup table.
    """
    existing = case.input.get("question")
    if isinstance(existing, str) and existing.strip():
        return existing
    mode = case.input.get("mode", "default")
    return f"[{case.risk.value}/{mode}] fixture probe for {case.task_id}"


def _adapt_case(case: TaskCase) -> InferenceRequest:
    risk_tier, require_citations, task_class = _RISK_POLICY[case.risk]
    return InferenceRequest(
        request_id=f"evalcase-{case.task_id}",
        question=_derive_question(case),
        task_class=task_class,
        risk_tier=risk_tier,
        require_citations=require_citations,
        authorized=case.risk != RiskArea.AUTHORIZATION,
        **_BASE_IDENTITY,
    )


def _suite_counts(cases: list[TaskCase]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.suite.value] = counts.get(case.suite.value, 0) + 1
    return counts


def _risk_counts(cases: list[TaskCase]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.risk.value] = counts.get(case.risk.value, 0) + 1
    return counts


def load_and_validate_cases(cases_root: Path | None = None) -> list[TaskCase]:
    """Load capability/regression/adversarial cases and fail closed on any drift from the
    expected suite/risk distribution."""
    root = cases_root or EVALS_CASES_ROOT

    for suite_name in EXPECTED_SUITE_COUNTS:
        suite_dir = root / suite_name
        if not suite_dir.exists() or not any(suite_dir.glob("*.jsonl")):
            raise FixtureLoadError(
                f"required suite '{suite_name}' is missing under {root}; failing closed"
            )

    cases = [case for case in load_cases(root) if case.suite != SuiteClass.HOLDOUT]

    suite_counts = _suite_counts(cases)
    for suite_name, expected_count in EXPECTED_SUITE_COUNTS.items():
        actual_count = suite_counts.get(suite_name, 0)
        if actual_count == 0:
            raise FixtureLoadError(
                f"suite '{suite_name}' loaded zero cases from {root}; failing closed"
            )
        if actual_count != expected_count:
            raise FixtureLoadError(
                f"suite '{suite_name}' expected {expected_count} cases, found {actual_count} "
                f"in {root}; failing closed"
            )

    risk_counts = _risk_counts(cases)
    for risk_name, expected_count in EXPECTED_RISK_COUNTS.items():
        actual_count = risk_counts.get(risk_name, 0)
        if actual_count != expected_count:
            raise FixtureLoadError(
                f"risk '{risk_name}' expected {expected_count} cases, found {actual_count} "
                f"in {root}; failing closed"
            )

    return cases


def load_gateway_workload(cases_root: Path | None = None) -> list[InferenceRequest]:
    """Load and adapt the Chapter 2 cases into the Chapter 4 gateway's request fixtures."""
    cases = load_and_validate_cases(cases_root)
    return [_adapt_case(case) for case in sorted(cases, key=lambda c: c.task_id)]
