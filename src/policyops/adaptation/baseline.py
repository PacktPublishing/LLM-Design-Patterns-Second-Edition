"""Chapter 2 baseline measurement — honors the `upstream = "ch02"` declaration in
`labs/ch03/manifest.toml` (step 1 of the chapter's Hands-On sequence: "Measure the unchanged
baseline from Chapter 2").

Fixture-only precedent: `src/policyops/inference/fixtures.py` (Chapter 4) consumes Chapter 2's
locked cases through `policyops.eval` and fails closed on drift instead of trusting a literal
placeholder hash. This module follows the same shape for Chapter 3's baseline: the suite hash
and the measured metrics are both derived from Chapter 2's actual cases, never a literal.

`evals/**` is owned by the Chapter 2 lab. This module only READS it, never writes into it —
`run_suite` is given a Chapter 3 evidence directory to write its own evidence into.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from policyops.adaptation.intake import hash_payload
from policyops.eval import SuiteSummary, TaskCase, load_cases, run_suite

EVALS_ROOT = Path(__file__).resolve().parents[3] / "evals"
EVALS_CASES_ROOT = EVALS_ROOT / "cases"
EVALS_HOLDOUTS_ROOT = EVALS_ROOT / "holdouts"

BASELINE_SUITE = "all"


class BaselineMeasurementError(RuntimeError):
    """Raised when Chapter 2's locked cases are missing or empty. The lab fails closed here
    instead of silently falling back to a fabricated baseline hash or measurement."""


def _suite_hash(cases: list[TaskCase]) -> str:
    ordered = sorted(cases, key=lambda case: case.task_id)
    return hash_payload([{"task_id": case.task_id, "content_hash": case.content_hash} for case in ordered])


def measure_ch02_baseline(
    evidence_dir: Path,
    *,
    cases_root: Path | None = None,
    holdouts_root: Path | None = None,
    suite: str = BASELINE_SUITE,
) -> dict[str, Any]:
    """Measure the unchanged Chapter 2 baseline offline, from Chapter 2's actual locked cases.

    The suite hash is derived from the content hashes of the loaded cases (never a literal).
    The measurement itself is a real `policyops.eval.run_suite` pass over those cases, using
    Chapter 1's replay adapter — offline and deterministic, no network or model training.

    Raises `BaselineMeasurementError` if Chapter 2's case fixtures are missing or empty.
    `policyops.eval.run_suite` separately fails closed (`HoldoutIntegrityError`) if the
    protected holdout split has drifted.
    """
    root = cases_root or EVALS_CASES_ROOT
    holdouts = holdouts_root or EVALS_HOLDOUTS_ROOT
    if not root.exists():
        raise BaselineMeasurementError(f"Chapter 2 cases missing under {root}; failing closed")
    cases = load_cases(root)
    if not cases:
        raise BaselineMeasurementError(f"Chapter 2 cases loaded zero cases from {root}; failing closed")

    suite_hash = _suite_hash(cases)
    summary: SuiteSummary = asyncio.run(
        run_suite(
            cases_root=root,
            suite=suite,
            evidence_dir=evidence_dir,
            profile="fixture",
            holdouts_root=holdouts,
        )
    )
    return {
        "suite": suite,
        "suite_hash": suite_hash,
        "case_count": len(cases),
        "case_ids": sorted(case.task_id for case in cases),
        "holdout_verified": True,
        "summary": summary.model_dump(mode="json"),
    }


def baseline_report(measurement: dict[str, Any]) -> dict[str, Any]:
    """Build the `baseline_report.json` payload (deliverable 1): what was measured, on which
    Chapter 2 cases, the resulting metrics, and the provenance hash of the measured suite."""
    summary = measurement["summary"]
    return {
        "schema_version": "1",
        "baseline_id": "ch02-baseline",
        "suite": measurement["suite"],
        "suite_hash": measurement["suite_hash"],
        "case_count": measurement["case_count"],
        "case_ids": measurement["case_ids"],
        "holdout_verified": measurement["holdout_verified"],
        "metrics": {
            "pass_rate": summary["pass_rate"],
            "first_try_pass_rate": summary["first_try_pass_rate"],
            "total_cases": summary["total_cases"],
            "total_trials": summary["total_trials"],
            "passed_trials": summary["passed_trials"],
            "cost_per_successful_outcome": summary["cost_per_successful_outcome"],
            "cost_status": summary["cost_status"],
            "gates_passed": summary["gates_passed"],
        },
        "measured_at": summary.get("generated_at"),
    }
