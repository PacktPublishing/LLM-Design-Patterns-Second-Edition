"""Evaluation runner — schedule, grade, adjudicate, evidence."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from policyops.eval.candidate import PolicyOpsCandidate
from policyops.eval.graders import get_grader
from policyops.eval.schemas import (
    FailureClass,
    GraderResult,
    GraderVerdict,
    Outcome,
    SuiteClass,
    SuiteManifest,
    SuiteSummary,
    TaskCase,
    TrialContext,
)
from policyops.eval.throttle import BoundedPool, PoolBudget
from policyops.util import canonical_json


def _hash_obj(obj: Any) -> str:
    digest = hashlib.sha256(canonical_json(obj).encode()).hexdigest()
    return f"sha256:{digest}"


def _derive_trial_cost(record: TrialRecord) -> tuple[float | None, str, dict[str, int]]:
    usage = record.usage or {}
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    token_totals = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if record.cost_usd is not None and record.cost_usd > 0:
        return record.cost_usd, "explicit_cost", token_totals
    total_tokens = input_tokens + output_tokens
    if total_tokens > 0:
        return round((total_tokens / 1000.0) * 0.15, 6), "token_proxy", token_totals
    if not record.model_invoked:
        return 0.0, "no_model_call", token_totals
    return None, "unavailable", token_totals


def load_cases(root: Path) -> list[TaskCase]:
    cases: list[TaskCase] = []
    for path in sorted(root.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            case = TaskCase.model_validate(data)
            case.content_hash = _hash_obj(case.model_dump(mode="json"))
            cases.append(case)
    return cases


def build_manifest(suite_id: str, cases: list[TaskCase]) -> SuiteManifest:
    filtered = [c for c in cases if c.suite.value == suite_id or suite_id == "all"]
    manifest = SuiteManifest(
        suite_id=suite_id,
        case_ids=[c.task_id for c in filtered],
        grader_versions={g: "1" for c in filtered for g in c.graders},
    )
    manifest.content_hash = _hash_obj(manifest.model_dump(mode="json"))
    return manifest


class HoldoutIntegrityError(RuntimeError):
    """Raised when protected holdout hashes drift from the locked manifest."""


def holdout_hash_map(holdouts_root: Path) -> dict[str, str]:
    cases = load_cases(holdouts_root)
    return {c.task_id: c.content_hash or "" for c in cases}


def write_holdout_lock(holdouts_root: Path, lock_path: Path | None = None) -> Path:
    lock_path = lock_path or (holdouts_root / "hashes.lock.json")
    payload = {
        "schema_version": "1",
        "holdouts": holdout_hash_map(holdouts_root),
    }
    lock_path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return lock_path


def verify_holdout_integrity(
    holdouts_root: Path,
    lock_path: Path | None = None,
) -> dict[str, str]:
    """Fail closed if holdout cases were added, removed, or content-mutated."""
    lock_path = lock_path or (holdouts_root / "hashes.lock.json")
    if not holdouts_root.exists():
        raise HoldoutIntegrityError(f"holdouts root missing: {holdouts_root}")
    if not lock_path.exists():
        raise HoldoutIntegrityError(f"holdout lock missing: {lock_path}")
    expected = json.loads(lock_path.read_text(encoding="utf-8")).get("holdouts") or {}
    actual = holdout_hash_map(holdouts_root)
    if expected != actual:
        raise HoldoutIntegrityError(
            "holdout hash drift detected; "
            f"expected={sorted(expected.items())} actual={sorted(actual.items())}"
        )
    return actual


async def run_suite(
    *,
    cases_root: Path,
    suite: str = "regression",
    evidence_dir: Path,
    profile: str = "fixture",
    simulate_throttle: bool = False,
    holdouts_root: Path | None = None,
    holdout_lock_path: Path | None = None,
    skip_holdout_integrity: bool = False,
) -> SuiteSummary:
    started = time.perf_counter()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    holdouts_root = holdouts_root or Path("evals/holdouts")
    if not skip_holdout_integrity:
        # Fail closed if the protected holdout tree is missing or drifted.
        holdout_hashes = verify_holdout_integrity(holdouts_root, holdout_lock_path)
        (evidence_dir / "holdout_hashes.json").write_text(
            canonical_json(holdout_hashes), encoding="utf-8"
        )

    cases = load_cases(cases_root)
    if suite != "all":
        selected = [c for c in cases if c.suite.value == suite]
    else:
        selected = [c for c in cases if c.suite != SuiteClass.HOLDOUT]
    manifest = build_manifest(suite, selected)
    (evidence_dir / "manifest.lock.json").write_text(
        canonical_json(manifest.model_dump(mode="json")), encoding="utf-8"
    )

    candidate = PolicyOpsCandidate()
    pool = BoundedPool(PoolBudget(concurrency=4, max_retries=3))
    outcomes: list[Outcome] = []
    cost_rows: list[dict[str, Any]] = []
    trial_lines: list[str] = []
    grade_lines: list[str] = []
    taxonomy: Counter[str] = Counter()

    for case in selected:
        trials = case.trials if case.stochastic else max(1, case.trials)
        for idx in range(trials):
            trial = TrialContext(
                trial_id=f"{case.task_id}::t{idx}",
                task_id=case.task_id,
                trial_index=idx,
                seed=1000 + idx,
                configuration_id="fixture",
                candidate_id=candidate.candidate_id,
                profile=profile,
            )

            async def _run(t=trial, c=case):
                return await candidate.run(c, t)

            record = await pool.run(
                _run, throttle_until=1 if simulate_throttle and idx == 0 else 0
            )
            trial_lines.append(canonical_json(record.model_dump(mode="json")))

            grader_results = []
            for gid in case.graders:
                try:
                    result = get_grader(gid).grade(record, case)
                except Exception as exc:  # noqa: BLE001
                    result = GraderResult(
                        grader_id=gid,
                        trial_id=trial.trial_id,
                        task_id=case.task_id,
                        verdict=GraderVerdict.ERROR,
                        reason_code="grader_crash",
                        evidence={"error": str(exc)},
                    )
                grader_results.append(result)
                grade_lines.append(canonical_json(result.model_dump(mode="json")))

            if any(g.verdict == GraderVerdict.ERROR for g in grader_results):
                failure = FailureClass.GRADER_DEFECT
                passed = False
            else:
                passed = all(g.verdict == GraderVerdict.PASS for g in grader_results)
                failure = None if passed else FailureClass.CANDIDATE
            if failure:
                taxonomy[failure.value] += 1
            outcomes.append(
                Outcome(
                    task_id=case.task_id,
                    trial_id=trial.trial_id,
                    passed=passed,
                    failure_class=failure,
                    grader_results=grader_results,
                )
            )
            derived_cost_usd, cost_source, token_totals = _derive_trial_cost(record)
            cost_rows.append(
                {
                    "trial_id": trial.trial_id,
                    "task_id": case.task_id,
                    "passed": passed,
                    "model_invoked": record.model_invoked,
                    "cost_source": cost_source,
                    "derived_cost_usd": derived_cost_usd,
                    **token_totals,
                }
            )

    passed_trials = sum(1 for o in outcomes if o.passed)
    total_trials = len(outcomes)
    first = [o for o in outcomes if o.trial_id.endswith("::t0")]
    first_pass = sum(1 for o in first if o.passed) / max(1, len(first))

    stochastic = [c for c in selected if c.stochastic]
    pass_at_k = None
    pass_hat_k = None
    if stochastic:
        by_task: dict[str, list[bool]] = {}
        for o in outcomes:
            if not any(c.task_id == o.task_id and c.stochastic for c in stochastic):
                continue
            by_task.setdefault(o.task_id, []).append(o.passed)
        if by_task:
            pass_at_k = sum(1 for flags in by_task.values() if any(flags)) / len(by_task)
            pass_hat_k = sum(1 for flags in by_task.values() if all(flags)) / len(by_task)

    success_count = sum(1 for o in outcomes if o.passed)
    successful_cost_rows = [row for row in cost_rows if row["passed"]]
    successful_costs = [row["derived_cost_usd"] for row in successful_cost_rows if row["derived_cost_usd"] is not None]
    if success_count and len(successful_costs) == success_count:
        cpso = round(sum(successful_costs) / success_count, 6)
        cost_status = "available"
    else:
        cpso = None
        cost_status = "unavailable"

    zero_tolerance_failed = False
    case_by_id = {c.task_id: c for c in selected}
    for o in outcomes:
        if not o.passed and case_by_id[o.task_id].release_gate.value == "zero_tolerance":
            zero_tolerance_failed = True
            break
    gates_passed = not zero_tolerance_failed and total_trials > 0

    summary = SuiteSummary(
        suite_id=suite,
        profile=profile,
        total_cases=len(selected),
        total_trials=total_trials,
        passed_trials=passed_trials,
        pass_rate=passed_trials / max(1, total_trials),
        first_try_pass_rate=first_pass,
        pass_at_k=pass_at_k,
        pass_hat_k=pass_hat_k,
        cost_per_successful_outcome=cpso,
        cost_status=cost_status,  # type: ignore[arg-type]
        gates_passed=gates_passed,
        failure_taxonomy=dict(taxonomy),
        runtime_ms=(time.perf_counter() - started) * 1000,
        generated_at=datetime.now(UTC),
    )

    (evidence_dir / "trials.jsonl").write_text("\n".join(trial_lines) + "\n", encoding="utf-8")
    (evidence_dir / "grades.jsonl").write_text("\n".join(grade_lines) + "\n", encoding="utf-8")
    (evidence_dir / "summary.json").write_text(
        canonical_json(summary.model_dump(mode="json")), encoding="utf-8"
    )
    failure_taxonomy = {
        "schema_version": "1",
        "suite": suite,
        "taxonomy": dict(taxonomy),
        "adjudication_rule": (
            "grader errors are classified as grader_defect; failed candidate "
            "grades are candidate failures unless the case is later quarantined"
        ),
    }
    (evidence_dir / "failure_taxonomy.json").write_text(
        canonical_json(failure_taxonomy), encoding="utf-8"
    )
    calibration_report = {
        "schema_version": "1",
        "rubric_profile": "frozen_replay",
        "mandatory_gate": False,
        "expert_label_source": "evals/labels/expert_labels.json",
        "status": "available" if Path("evals/labels/expert_labels.json").exists() else "unavailable",
        "note": "Live rubric grading is intentionally outside mandatory PR gates.",
    }
    (evidence_dir / "calibration_report.json").write_text(
        canonical_json(calibration_report), encoding="utf-8"
    )
    cost_report = {
        "schema_version": "1",
        "suite": suite,
        "cost_status": cost_status,
        "cost_per_successful_outcome": cpso,
        "successful_trial_count": success_count,
        "successful_known_cost_trials": len(successful_costs),
        "successful_total_cost_usd": round(sum(successful_costs), 6) if successful_costs else None,
        "trials": cost_rows,
    }
    (evidence_dir / "cost_report.json").write_text(
        canonical_json(cost_report),
        encoding="utf-8",
    )
    (evidence_dir / "result.json").write_text(
        json.dumps(
            {
                "lab": "ch02",
                "suite": suite,
                "gates_passed": gates_passed,
                "pass_rate": summary.pass_rate,
                "retry_count": pool.retry_count,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    evidence_index = {
        "schema_version": "1",
        "suite": suite,
        "artifacts": {
            "manifest": "manifest.lock.json",
            "trials": "trials.jsonl",
            "grades": "grades.jsonl",
            "summary": "summary.json",
            "failure_taxonomy": "failure_taxonomy.json",
            "calibration_report": "calibration_report.json",
            "cost_report": "cost_report.json",
            "holdout_hashes": "holdout_hashes.json",
            "result": "result.json",
        },
    }
    (evidence_dir / "evidence_index.json").write_text(
        canonical_json(evidence_index), encoding="utf-8"
    )
    return summary
