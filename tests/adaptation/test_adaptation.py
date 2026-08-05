"""Chapter 3 adaptation pipeline tests."""

from __future__ import annotations

import hashlib
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
