"""Chapter 3 adaptation pipeline tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from policyops.adaptation import (
    artifact_admission_report,
    build_dataset_manifest,
    admit_adapter,
    contamination_report,
    deterministic_split,
    load_records,
    plan_training_run,
    run_adaptation_pipeline,
    run_adaptation_verification,
)
import policyops.adaptation.pipeline as pipeline_module
from policyops.adaptation.baseline import BaselineMeasurementError, measure_ch02_baseline
from policyops.adaptation.schemas import ModelArtifact

RECORDS = Path("evals/adaptation/records.jsonl")
ADAPTER = Path("evals/adaptation/adapter_fixture.json")


def _artifact(**overrides) -> ModelArtifact:
    base = dict(
        artifact_id="adapter-fixture-v1",
        path=str(ADAPTER),
        content_hash="sha256:" + hashlib.sha256(ADAPTER.read_bytes()).hexdigest(),
        license="Apache-2.0",
        base_model="policyops-replay-v1",
    )
    base.update(overrides)
    return ModelArtifact(**base)


def test_records_have_provenance() -> None:
    records = load_records(RECORDS)
    assert len(records) >= 6
    assert all(r.rights_basis and r.source_ref for r in records)
    assert all(r.provenance_chain for r in records)


def test_pipeline_ships_or_explicit_no_adapt(tmp_path: Path) -> None:
    payload = run_adaptation_pipeline(RECORDS, ADAPTER, tmp_path / "ok")
    assert payload["contamination"]["clean"] is True
    assert payload["decision"]["decision"] == "ship"
    assert payload["decision"]["selected_candidate_id"] == "retrieval-replay-v1"
    assert (tmp_path / "ok" / "result.json").exists()
    assert (tmp_path / "ok" / "dataset_card.json").exists()
    assert (tmp_path / "ok" / "model_card.json").exists()
    assert (tmp_path / "ok" / "artifact_admission.json").exists()
    assert (tmp_path / "ok" / "candidate_reports.json").exists()
    assert (tmp_path / "ok" / "comparison_report.json").exists()
    assert payload["artifact_admission"]["admitted"] is True
    assert payload["candidate_matrix"]["retrieval-replay-v1"]["quality"] > payload["candidate_matrix"]["baseline"]["quality"]


def test_contamination_blocks_release(tmp_path: Path) -> None:
    payload = run_adaptation_pipeline(
        RECORDS, ADAPTER, tmp_path / "contam", inject_contamination=True
    )
    assert payload["contamination"]["clean"] is False
    assert payload["decision"]["decision"] == "no_ship"
    assert payload["decision"]["selected_candidate_id"] == "baseline"
    assert payload["decision"]["decision_reason"] == "contamination_check_failed_blocked_before_scoring"


def test_contamination_blocks_scoring_before_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Change 2: the step-3 checkpoint must short-circuit BEFORE any candidate is scored.

    Proves it two ways: (1) counts calls to the candidate-evaluation function and asserts it
    was never invoked, and (2) asserts every candidate's metrics/case results are empty.
    """
    calls: list[str] = []
    original = pipeline_module._evaluate_candidate

    def _spy(candidate, *args, **kwargs):
        calls.append(candidate.candidate_id)
        return original(candidate, *args, **kwargs)

    monkeypatch.setattr(pipeline_module, "_evaluate_candidate", _spy)

    payload = run_adaptation_pipeline(
        RECORDS, ADAPTER, tmp_path / "contam-gate", inject_contamination=True
    )

    assert calls == []
    assert payload["decision"]["decision"] == "no_ship"
    assert all(metrics == {} for metrics in payload["candidate_matrix"].values())
    assert all(report == [] for report in payload["candidate_reports"].values())


def test_adapter_admission_failure_blocks_scoring_before_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same checkpoint must also short-circuit on adapter-admission failure, not just
    contamination, and the decision reason must say which gate blocked the run."""
    calls: list[str] = []
    original = pipeline_module._evaluate_candidate

    def _spy(candidate, *args, **kwargs):
        calls.append(candidate.candidate_id)
        return original(candidate, *args, **kwargs)

    monkeypatch.setattr(pipeline_module, "_evaluate_candidate", _spy)
    monkeypatch.setattr(
        pipeline_module,
        "artifact_admission_report",
        lambda artifact, expected_hash: {"admitted": False, "reasons": ["forced_for_test"], "artifact_id": artifact.artifact_id, "expected_hash": expected_hash},
    )

    payload = run_adaptation_pipeline(RECORDS, ADAPTER, tmp_path / "admission-gate")

    assert calls == []
    assert payload["contamination"]["clean"] is True
    assert payload["artifact_admission"]["admitted"] is False
    assert payload["decision"]["decision"] == "no_ship"
    assert payload["decision"]["decision_reason"] == "adapter_admission_failed_blocked_before_scoring"
    assert all(metrics == {} for metrics in payload["candidate_matrix"].values())


def test_safety_regression_blocks_adapter(tmp_path: Path) -> None:
    payload = run_adaptation_pipeline(
        RECORDS, ADAPTER, tmp_path / "safe", inject_safety_regression=True
    )
    assert payload["decision"]["decision"] in {"ship", "no_ship"}
    # Unsafe adapter must not be selected
    assert payload["decision"]["selected_candidate_id"] != "adapter-v1"
    assert payload["decision"]["gate_evidence"]["candidate_gates"]["adapter-v1"]["safety"] is False
    assert payload["decision"]["gate_evidence"]["candidate_gates"]["adapter-v1"]["authorization_regressions"] is False


def test_contamination_detector_exact() -> None:
    records = load_records(RECORDS)
    report = contamination_report(records[:2], [records[0].text])
    assert report["clean"] is False
    assert report["exact_hits"]


def test_contamination_detector_normalized_whitespace_and_case() -> None:
    records = load_records(RECORDS)
    noisy = "  " + records[0].text.upper().replace(" ", "   ") + "  "
    report = contamination_report(records[:2], [noisy])
    assert report["clean"] is False
    assert report["normalized_hits"]


def test_contamination_detector_near_duplicate() -> None:
    records = load_records(RECORDS)
    tokens = records[0].text.split()
    near = " ".join(tokens + ["today"])  # >0.9 Jaccard overlap, not identical
    report = contamination_report(records[:2], [near])
    assert report["clean"] is False
    assert report["near_duplicate_hits"]


def test_deterministic_split_is_stable_and_entity_keyed() -> None:
    records = load_records(RECORDS)
    a = deterministic_split(records)
    b = deterministic_split(records)
    assert a.content_hash == b.content_hash
    # Every record lands in exactly one partition; nothing is dropped or duplicated.
    placed = set(a.train) | set(a.validation) | set(a.protected_test)
    assert placed == {r.record_id for r in records}
    total = len(a.train) + len(a.validation) + len(a.protected_test)
    assert total == len(records)
    assert a.protected_test  # lab determinism guarantees a non-empty protected split
    assert a.subgroup_membership


def test_load_records_requires_provenance(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"schema_version":"1","record_id":"x","text":"t","label":"l",'
        '"content_hash":"sha256:0","source_ref":"","rights_basis":"",'
        '"owner":"o","entity_key":"e"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_records(bad)


def test_admit_adapter_accepts_valid_artifact() -> None:
    art = _artifact()
    assert admit_adapter(art, art.content_hash) is True


def test_artifact_admission_report_explains_rejections() -> None:
    report = artifact_admission_report(
        _artifact(format="bad-format", load_policy="unsafe"),
        _artifact().content_hash,
    )
    assert report["admitted"] is False
    assert "format_unsupported" in report["reasons"]
    assert "load_policy_unsupported" in report["reasons"]


def test_admit_adapter_rejects_hash_mismatch() -> None:
    art = _artifact()
    assert admit_adapter(art, "sha256:" + "0" * 64) is False


def test_admit_adapter_rejects_missing_or_unknown_license() -> None:
    assert admit_adapter(_artifact(license="unknown"), _artifact().content_hash) is False
    assert admit_adapter(_artifact(license="none"), _artifact().content_hash) is False


def test_admit_adapter_rejects_missing_base_model() -> None:
    art = _artifact(base_model="")
    assert admit_adapter(art, art.content_hash) is False


def test_admit_adapter_rejects_missing_artifact_file(tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    art = _artifact(path=str(missing))
    assert admit_adapter(art, art.content_hash) is False


def test_baseline_can_win_as_explicit_no_adaptation(tmp_path: Path) -> None:
    """DR-05: 'no adaptation' is a valid, explicitly-recorded outcome."""
    payload = run_adaptation_pipeline(
        RECORDS, ADAPTER, tmp_path / "safe", inject_safety_regression=True
    )
    decision = payload["decision"]
    # The unsafe adapter is blocked; the surviving winner is a non-adapter candidate.
    assert decision["selected_candidate_id"] != "adapter-v1"
    assert decision["decision"] in {"ship", "no_ship"}


def test_adaptation_verification_writes_scorecard_and_drills(tmp_path: Path) -> None:
    payload = run_adaptation_verification(tmp_path)
    assert payload["gates_passed"] is True
    assert (tmp_path / "adaptation_scorecard.json").exists()
    assert (tmp_path / "safety_drill_report.json").exists()
    scorecard = __import__("json").loads((tmp_path / "adaptation_scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["selected_candidate_id"] == "retrieval-replay-v1"
    assert scorecard["contamination_drill_blocked"] is True
    assert scorecard["safety_drill_blocked"] is True


def test_dataset_manifest_captures_lineage_and_synthetic_breakdown() -> None:
    records = load_records(RECORDS)
    manifest = build_dataset_manifest("policyops-adapt-v1", records)
    assert manifest.record_count == len(records)
    assert manifest.synthetic_record_ids
    assert manifest.lineage_hash and manifest.lineage_hash.startswith("sha256:")


def test_baseline_report_is_written_before_candidate_scoring(tmp_path: Path) -> None:
    """Change 3: `baseline_report.json` is a first-class deliverable produced by step 1, not
    derived afterwards from the candidate matrix."""
    payload = run_adaptation_pipeline(RECORDS, ADAPTER, tmp_path / "baseline")
    report_path = tmp_path / "baseline" / "baseline_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["suite_hash"].startswith("sha256:")
    assert report["suite_hash"] != "sha256:ch02-baseline"
    assert report["case_count"] > 0
    assert report["case_ids"]
    assert report["holdout_verified"] is True
    assert "pass_rate" in report["metrics"]
    assert payload["baseline_report"] == report


def test_baseline_suite_hash_is_derived_from_ch02_cases_not_a_literal(tmp_path: Path) -> None:
    """Change 1: the baseline suite hash must come from Chapter 2's actual locked cases."""
    measurement = measure_ch02_baseline(tmp_path / "ch02-suite")
    assert measurement["suite_hash"].startswith("sha256:")
    assert measurement["suite_hash"] not in {"sha256:ch02-baseline", "sha256:ch02-suite"}
    assert measurement["case_count"] > 0

    payload = run_adaptation_pipeline(RECORDS, ADAPTER, tmp_path / "run")
    experiment = payload["experiment"]
    assert experiment["baseline_suite_hash"] == measurement["suite_hash"]
    assert experiment["suite_hash"] == measurement["suite_hash"]
    assert experiment["baseline_suite_hash"] not in {"sha256:ch02-baseline", "sha256:ch02-suite"}


def test_baseline_measurement_fails_closed_on_missing_cases(tmp_path: Path) -> None:
    with pytest.raises(BaselineMeasurementError):
        measure_ch02_baseline(tmp_path / "ev", cases_root=tmp_path / "does-not-exist")


def test_optional_training_requires_declared_gpu_and_hardware() -> None:
    records = load_records(RECORDS)
    manifest = build_dataset_manifest("policyops-adapt-v1", records)
    with pytest.raises(ValueError):
        plan_training_run(manifest)
    plan = plan_training_run(
        manifest,
        gpu_profile="l4-fixture",
        hardware={"gpu": "L4", "count": 1, "driver": "fixture-driver"},
    )
    assert plan["artifact_hash"].startswith("sha256:")
