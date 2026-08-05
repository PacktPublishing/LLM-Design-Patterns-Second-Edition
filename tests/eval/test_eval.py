"""Chapter 2 evaluation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from policyops.eval.graders import (
    AbstentionGrader,
    AuthorizationGrader,
    CitationGrader,
    GamingGrader,
    SchemaGrader,
    get_grader,
)
from policyops.eval.runner import load_cases, run_suite
from policyops.eval.schemas import RiskArea, TaskCase, TrialRecord
from policyops.eval.throttle import BoundedPool, PoolBudget

CASES = Path("evals/cases")
HOLDOUTS = Path("evals/holdouts")


def _write_cases(root: Path, cases: list[dict]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
    return root


def _trial(**overrides) -> TrialRecord:
    base = dict(
        trial_id="t0",
        task_id="task",
        candidate_id="c",
        status="ok",
        http_status=200,
        model_invoked=False,
    )
    base.update(overrides)
    return TrialRecord(**base)


def test_at_least_30_cases_cover_six_risks() -> None:
    cases = load_cases(CASES)
    assert len(cases) >= 30
    risks = {c.risk for c in cases}
    assert risks >= set(RiskArea)


def test_case_schema_round_trip() -> None:
    cases = load_cases(CASES)
    raw = cases[0].model_dump(mode="json")
    again = TaskCase.model_validate(raw)
    assert again.task_id == cases[0].task_id


@pytest.mark.asyncio
async def test_regression_suite_gates(tmp_path: Path) -> None:
    summary = await run_suite(
        cases_root=CASES,
        suite="regression",
        evidence_dir=tmp_path / "regression",
        profile="fixture",
    )
    assert summary.gates_passed
    assert summary.cost_status == "available"
    assert summary.cost_per_successful_outcome and summary.cost_per_successful_outcome > 0
    assert (tmp_path / "regression" / "summary.json").exists()
    assert (tmp_path / "regression" / "failure_taxonomy.json").exists()
    assert (tmp_path / "regression" / "calibration_report.json").exists()
    assert (tmp_path / "regression" / "cost_report.json").exists()
    assert (tmp_path / "regression" / "evidence_index.json").exists()


@pytest.mark.asyncio
async def test_deterministic_repeat(tmp_path: Path) -> None:
    a = await run_suite(
        cases_root=CASES, suite="regression", evidence_dir=tmp_path / "a", profile="fixture"
    )
    b = await run_suite(
        cases_root=CASES, suite="regression", evidence_dir=tmp_path / "b", profile="fixture"
    )
    assert a.pass_rate == b.pass_rate
    assert a.passed_trials == b.passed_trials


@pytest.mark.asyncio
async def test_throttle_retries_bounded(tmp_path: Path) -> None:
    summary = await run_suite(
        cases_root=CASES,
        suite="regression",
        evidence_dir=tmp_path / "throttle",
        profile="fixture",
        simulate_throttle=True,
    )
    result = json.loads((tmp_path / "throttle" / "result.json").read_text(encoding="utf-8"))
    assert result["retry_count"] >= 1
    assert summary.total_trials > 0


@pytest.mark.asyncio
async def test_pool_max_retries() -> None:
    pool = BoundedPool(PoolBudget(concurrency=1, max_retries=2, base_delay_ms=1, jitter_ms=0))

    async def boom():
        raise TimeoutError("429")

    with pytest.raises(TimeoutError):
        await pool.run(boom, throttle_until=10)
    assert pool.retry_count >= 2


def test_gaming_candidate_fails_deterministic_graders() -> None:
    case = TaskCase(
        task_id="adv.gaming.unit",
        suite="adversarial",
        risk="adversarial",
        rationale="unit",
        input={"mode": "gaming"},
        expected={"require_citations": True},
        graders=["gaming@1", "citation@1"],
    )
    trial = TrialRecord(
        trial_id="g1",
        task_id=case.task_id,
        candidate_id="gaming",
        status="ok",
        output={
            "answer": {
                "schema_version": "1.0",
                "answer_type": "direct",
                "text": "This is definitely the complete policy answer.",
                "citations": [],
            }
        },
        http_status=200,
        model_invoked=True,
    )
    g = GamingGrader().grade(trial, case)
    c = CitationGrader().grade(trial, case)
    assert g.verdict.value == "fail"
    assert c.verdict.value == "fail"


@pytest.mark.asyncio
async def test_holdouts_not_in_all_suite(tmp_path: Path) -> None:
    summary = await run_suite(
        cases_root=CASES, suite="all", evidence_dir=tmp_path / "all", profile="fixture"
    )
    assert summary.total_cases >= 30
    # holdouts live under evals/holdouts and are excluded from suite=all
    holdouts = load_cases(Path("evals/holdouts"))
    assert holdouts
    assert all(h.task_id not in json.loads(
        (tmp_path / "all" / "manifest.lock.json").read_text(encoding="utf-8")
    )["case_ids"] for h in holdouts)


def test_grader_registry() -> None:
    assert get_grader("schema@1").grader_id == "schema@1"


@pytest.mark.asyncio
async def test_cpso_labeled_unavailable_when_no_successes(tmp_path: Path) -> None:
    """DR-03: CPSO must be explicitly 'unavailable' rather than a silent zero."""
    cases_root = _write_cases(
        tmp_path / "cases",
        [
            {
                "schema_version": "1",
                "task_id": "reg.forced_fail.001",
                "suite": "regression",
                "risk": "answer_schema",
                "rationale": "force a failing trial to exercise unavailable CPSO labeling",
                "input": {
                    "mode": "answer",
                    "question": "How many remote days are allowed?",
                    "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
                },
                "expected": {"http_status": 500},
                "graders": ["schema@1"],
                "release_gate": "informational",
            }
        ],
    )
    summary = await run_suite(
        cases_root=cases_root,
        suite="regression",
        evidence_dir=tmp_path / "ev",
        profile="fixture",
    )
    assert summary.passed_trials == 0
    assert summary.cost_status == "unavailable"
    assert summary.cost_per_successful_outcome is None


@pytest.mark.asyncio
async def test_cpso_is_measured_from_trial_cost_inputs(tmp_path: Path) -> None:
    summary = await run_suite(
        cases_root=CASES,
        suite="regression",
        evidence_dir=tmp_path / "ev",
        profile="fixture",
    )
    report = json.loads((tmp_path / "ev" / "cost_report.json").read_text(encoding="utf-8"))
    assert summary.cost_status == "available"
    assert summary.cost_per_successful_outcome == report["cost_per_successful_outcome"]
    assert report["successful_trial_count"] == summary.passed_trials
    assert report["successful_known_cost_trials"] == summary.passed_trials
    assert any(row["cost_source"] == "token_proxy" for row in report["trials"] if row["passed"])


@pytest.mark.asyncio
async def test_grader_defect_is_adjudicated_separately(tmp_path: Path) -> None:
    """DR-01: a broken grader must not silently blame the candidate."""
    cases_root = _write_cases(
        tmp_path / "cases",
        [
            {
                "schema_version": "1",
                "task_id": "reg.grader_defect.001",
                "suite": "regression",
                "risk": "answer_schema",
                "rationale": "unknown grader id triggers grader-defect adjudication",
                "input": {
                    "mode": "answer",
                    "question": "How many remote days are allowed?",
                    "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
                },
                "expected": {},
                "graders": ["nonexistent@1"],
                "release_gate": "informational",
            }
        ],
    )
    summary = await run_suite(
        cases_root=cases_root,
        suite="regression",
        evidence_dir=tmp_path / "ev",
        profile="fixture",
    )
    assert summary.failure_taxonomy.get("grader_defect", 0) >= 1


def test_schema_grader_blocks_http_status_regression() -> None:
    case = TaskCase(
        task_id="reg.schema.status",
        suite="regression",
        risk="answer_schema",
        rationale="unit",
        input={},
        expected={"http_status": 200},
        graders=["schema@1"],
    )
    result = SchemaGrader().grade(_trial(http_status=502), case)
    assert result.verdict.value == "fail"
    assert result.reason_code == "http_status_mismatch"


def test_authorization_grader_flags_forbidden_model_invocation() -> None:
    case = TaskCase(
        task_id="adv.authz.model_invoked",
        suite="adversarial",
        risk="authorization",
        rationale="unit",
        input={},
        expected={"http_status": 401},
        forbidden_behavior=["model_invoked"],
        graders=["authorization@1"],
    )
    result = AuthorizationGrader().grade(
        _trial(http_status=401, model_invoked=True), case
    )
    assert result.verdict.value == "fail"
    assert result.reason_code == "model_invoked_forbidden"


def test_abstention_grader_requires_reason() -> None:
    case = TaskCase(
        task_id="cap.abstain.reason",
        suite="capability",
        risk="abstention",
        rationale="unit",
        input={},
        expected={"answer_type": "abstain"},
        graders=["abstention@1"],
    )
    missing_reason = _trial(
        output={"answer": {"answer_type": "abstain", "text": "no data"}}
    )
    result = AbstentionGrader().grade(missing_reason, case)
    assert result.verdict.value == "fail"
    assert result.reason_code == "missing_reason"


def test_citation_grader_flags_fabricated_source() -> None:
    case = TaskCase(
        task_id="adv.citation.fabricated",
        suite="adversarial",
        risk="citation",
        rationale="unit",
        input={},
        expected={
            "require_citations": True,
            "forbid_fabricated_citation": True,
            "allowed_source_ids": ["pol-remote-work-v1"],
        },
        graders=["citation@1"],
    )
    trial = _trial(
        output={
            "answer": {
                "text": "made up",
                "citations": [
                    {"source_id": "not-a-real-source", "excerpt": "x", "locator": "l"}
                ],
            }
        }
    )
    result = CitationGrader().grade(trial, case)
    assert result.verdict.value == "fail"
    assert result.reason_code == "fabricated_citation"


def test_holdout_content_hash_is_immutable() -> None:
    """DR-02: holdout hashes are content-derived and stable across independent loads."""
    holdouts_a = load_cases(HOLDOUTS)
    holdouts_b = load_cases(HOLDOUTS)
    assert holdouts_a, "expected holdout cases to exist"
    for a, b in zip(holdouts_a, holdouts_b):
        assert a.content_hash == b.content_hash
        assert a.content_hash and a.content_hash.startswith("sha256:")


def test_holdout_lock_matches_current_cases() -> None:
    from policyops.eval.runner import verify_holdout_integrity

    hashes = verify_holdout_integrity(HOLDOUTS)
    assert "hold.auth.cross_tenant.001" in hashes


def test_holdout_hash_drift_fails_closed(tmp_path: Path) -> None:
    """DR-02 / CH02-SEC-006: mutating holdout content must fail the run."""
    from policyops.eval.runner import (
        HoldoutIntegrityError,
        verify_holdout_integrity,
        write_holdout_lock,
    )

    holdouts = tmp_path / "holdouts"
    holdouts.mkdir()
    src = (HOLDOUTS / "cases.jsonl").read_text(encoding="utf-8")
    (holdouts / "cases.jsonl").write_text(src, encoding="utf-8")
    lock = write_holdout_lock(holdouts)
    # Mutate holdout content after lock is written.
    (holdouts / "cases.jsonl").write_text(
        src.replace("secret", "secret-mutated"), encoding="utf-8"
    )
    with pytest.raises(HoldoutIntegrityError, match="holdout hash drift"):
        verify_holdout_integrity(holdouts, lock)


@pytest.mark.asyncio
async def test_run_suite_fails_on_holdout_drift(tmp_path: Path) -> None:
    from policyops.eval.runner import HoldoutIntegrityError, write_holdout_lock

    holdouts = tmp_path / "holdouts"
    holdouts.mkdir()
    src = (HOLDOUTS / "cases.jsonl").read_text(encoding="utf-8")
    (holdouts / "cases.jsonl").write_text(src, encoding="utf-8")
    write_holdout_lock(holdouts)
    (holdouts / "cases.jsonl").write_text(
        src.replace('"question": "secret"', '"question": "tampered"'),
        encoding="utf-8",
    )
    with pytest.raises(HoldoutIntegrityError):
        await run_suite(
            cases_root=CASES,
            suite="regression",
            evidence_dir=tmp_path / "ev",
            profile="fixture",
            holdouts_root=holdouts,
        )


@pytest.mark.asyncio
async def test_run_suite_fails_when_holdouts_missing(tmp_path: Path) -> None:
    """Protected holdout directory deletion must not silently skip integrity."""
    from policyops.eval.runner import HoldoutIntegrityError

    with pytest.raises(HoldoutIntegrityError, match="holdouts root missing"):
        await run_suite(
            cases_root=CASES,
            suite="regression",
            evidence_dir=tmp_path / "ev",
            profile="fixture",
            holdouts_root=tmp_path / "does-not-exist",
        )


@pytest.mark.asyncio
async def test_holdouts_excluded_from_all_suite_even_when_loaded(tmp_path: Path) -> None:
    """DR-02: even if a holdout case sits alongside cases, suite=all must exclude it."""
    holdout = load_cases(HOLDOUTS)[0]
    cases_root = _write_cases(
        tmp_path / "cases",
        [
            {
                "schema_version": "1",
                "task_id": "reg.included.001",
                "suite": "regression",
                "risk": "answer_schema",
                "rationale": "included regular case",
                "input": {
                    "mode": "answer",
                    "question": "How many remote days are allowed?",
                    "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
                },
                "expected": {"http_status": 200, "require_citations": True},
                "graders": ["schema@1", "citation@1"],
                "release_gate": "informational",
            },
            holdout.model_dump(mode="json"),
        ],
    )
    summary = await run_suite(
        cases_root=cases_root,
        suite="all",
        evidence_dir=tmp_path / "ev",
        profile="fixture",
    )
    manifest = json.loads(
        (tmp_path / "ev" / "manifest.lock.json").read_text(encoding="utf-8")
    )
    assert holdout.task_id not in manifest["case_ids"]
    assert "reg.included.001" in manifest["case_ids"]
    assert summary.total_cases == 1
