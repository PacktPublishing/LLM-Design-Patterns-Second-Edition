"""Offline adaptation pipeline orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from policyops.adaptation.admission import artifact_admission_report
from policyops.adaptation.contamination import contamination_report
from policyops.adaptation.decision import POLICY_VERSION, evaluate_candidates
from policyops.adaptation.intake import build_dataset_manifest, content_hash, load_records
from policyops.adaptation.schemas import (
    AdaptationCandidate,
    CandidateKind,
    DataRecord,
    ExperimentRun,
    DatasetManifest,
    ModelArtifact,
    ReleaseDecision,
)
from policyops.adaptation.splits import deterministic_split


def dataset_card(dataset: DatasetManifest, records: list[DataRecord]) -> dict[str, Any]:
    return {
        "dataset_id": dataset.dataset_id,
        "record_count": dataset.record_count,
        "rights_bases": dataset.rights_bases,
        "synthetic_record_ids": dataset.synthetic_record_ids,
        "subgroups": sorted({record.subgroup_key for record in records}),
        "intended_use": "offline adaptation comparison for PolicyOps routing/policy classification",
        "prohibited_use": "production policy deployment without separate review",
        "lineage_hash": dataset.lineage_hash,
    }


def model_card(candidates: list[AdaptationCandidate], artifact: ModelArtifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "base_model": artifact.base_model,
        "license": artifact.license,
        "format": artifact.format,
        "candidates": [candidate.candidate_id for candidate in candidates],
        "intended_use": "compare baseline, prompt, retrieval replay, and lightweight adapter",
        "rollback_target": "baseline",
    }


def run_adaptation_pipeline(
    records_path: Path,
    adapter_path: Path,
    evidence_dir: Path,
    *,
    inject_contamination: bool = False,
    inject_safety_regression: bool = False,
) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    records = load_records(records_path)
    dataset = build_dataset_manifest("policyops-adapt-v1", records)
    split = deterministic_split(records)
    by_id = {record.record_id: record for record in records}
    train_records = [by_id[record_id] for record_id in split.train]
    protected_texts = [by_id[record_id].text for record_id in split.protected_test]
    eval_texts = list(protected_texts)
    if inject_contamination and train_records:
        eval_texts.append(train_records[0].text)

    contamination = contamination_report(train_records, eval_texts)
    adapter_bytes = adapter_path.read_bytes()
    adapter_hash = "sha256:" + hashlib.sha256(adapter_bytes).hexdigest()
    artifact = ModelArtifact(
        artifact_id="adapter-fixture-v1",
        path=str(adapter_path),
        content_hash=adapter_hash,
        license="Apache-2.0",
        base_model="policyops-replay-v1",
        size_bytes=len(adapter_bytes),
    )
    admission = artifact_admission_report(artifact, adapter_hash)
    baseline_metrics = {
        "quality": 0.80,
        "safety": 1.0,
        "cost": 0.01,
        "latency_ms": 40.0,
        "calibration_error": 0.08,
        "authorization_regressions": 0.0,
        "subgroup_remote_policy_pass_rate": 0.93,
        "subgroup_general_policy_pass_rate": 0.95,
    }
    candidates = [
        AdaptationCandidate(
            candidate_id="baseline",
            kind=CandidateKind.BASELINE,
            model_ref="ch01-replay",
            configuration_hash="sha256:baseline",
            rollback_target="baseline",
            metrics=dict(baseline_metrics),
        ),
        AdaptationCandidate(
            candidate_id="prompt-v1",
            kind=CandidateKind.PROMPT,
            model_ref="ch01-replay",
            configuration_hash="sha256:prompt",
            rollback_target="baseline",
            base_candidate_id="baseline",
            metrics={
                "quality": 0.82,
                "safety": 1.0,
                "cost": 0.01,
                "latency_ms": 42.0,
                "calibration_error": 0.08,
                "authorization_regressions": 0.0,
                "subgroup_remote_policy_pass_rate": 0.94,
                "subgroup_general_policy_pass_rate": 0.95,
            },
        ),
        AdaptationCandidate(
            candidate_id="retrieval-replay-v1",
            kind=CandidateKind.RETRIEVAL_REPLAY,
            model_ref="fixture-retrieval",
            configuration_hash="sha256:retrieval",
            rollback_target="baseline",
            base_candidate_id="baseline",
            metrics={
                "quality": 0.85,
                "safety": 1.0,
                "cost": 0.012,
                "latency_ms": 47.0,
                "calibration_error": 0.07,
                "authorization_regressions": 0.0,
                "subgroup_remote_policy_pass_rate": 0.94,
                "subgroup_general_policy_pass_rate": 0.95,
            },
        ),
        AdaptationCandidate(
            candidate_id="adapter-v1",
            kind=CandidateKind.ADAPTER,
            model_ref=artifact.base_model,
            artifact_hashes={"adapter": adapter_hash},
            configuration_hash="sha256:adapter",
            rollback_target="baseline",
            base_candidate_id="baseline",
            metrics={
                "quality": 0.88,
                "safety": 0.5 if inject_safety_regression else 1.0,
                "cost": 0.015,
                "latency_ms": 49.0,
                "calibration_error": 0.06,
                "authorization_regressions": 0.0 if not inject_safety_regression else 1.0,
                "subgroup_remote_policy_pass_rate": 0.92 if not inject_safety_regression else 0.70,
                "subgroup_general_policy_pass_rate": 0.93 if not inject_safety_regression else 0.89,
            },
        ),
    ]

    if not contamination["clean"] or not admission["admitted"]:
        decision = ReleaseDecision(
            decision="no_ship",
            selected_candidate_id="baseline",
            selected_candidate_kind=CandidateKind.BASELINE.value,
            approver_role="release_reviewer",
            rollback_target="baseline",
            gate_evidence={
                "contamination_clean": contamination["clean"],
                "adapter_admitted": admission["admitted"],
                "admission_reasons": admission["reasons"],
            },
            decision_reason="blocked_before_candidate_comparison",
            residual_risks=["blocked before candidate comparison"],
            review_by="next-sprint",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    else:
        decision = evaluate_candidates(baseline_metrics=baseline_metrics, candidates=candidates)

    experiment = ExperimentRun(
        experiment_id="exp-ch03-fixture",
        dataset_hash=dataset.content_hash or "",
        split_hash=split.content_hash or "",
        baseline_suite_hash="sha256:ch02-baseline",
        candidate_ids=[candidate.candidate_id for candidate in candidates],
        contamination_clean=contamination["clean"],
        policy_hash=content_hash(POLICY_VERSION),
        results={candidate.candidate_id: candidate.metrics for candidate in candidates},
        gates={
            "contamination_clean": contamination["clean"],
            "adapter_admitted": admission["admitted"],
            "decision_ship": decision.decision == "ship",
        },
    )

    payload = {
        "dataset": dataset.model_dump(mode="json"),
        "split": split.model_dump(mode="json"),
        "contamination": contamination,
        "artifact": artifact.model_dump(mode="json"),
        "artifact_admission": admission,
        "candidate_matrix": {candidate.candidate_id: candidate.metrics for candidate in candidates},
        "experiment": experiment.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
        "dataset_card": dataset_card(dataset, records),
        "model_card": model_card(candidates, artifact),
    }
    (evidence_dir / "dataset_manifest.json").write_text(json.dumps(payload["dataset"], indent=2), encoding="utf-8")
    (evidence_dir / "split_manifest.json").write_text(json.dumps(payload["split"], indent=2), encoding="utf-8")
    (evidence_dir / "contamination_report.json").write_text(
        json.dumps(payload["contamination"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "artifact_admission.json").write_text(
        json.dumps(payload["artifact_admission"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "candidate_matrix.json").write_text(
        json.dumps(payload["candidate_matrix"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "dataset_card.json").write_text(json.dumps(payload["dataset_card"], indent=2), encoding="utf-8")
    (evidence_dir / "model_card.json").write_text(json.dumps(payload["model_card"], indent=2), encoding="utf-8")
    (evidence_dir / "release_decision.json").write_text(json.dumps(payload["decision"], indent=2), encoding="utf-8")
    (evidence_dir / "adaptation_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (evidence_dir / "result.json").write_text(
        json.dumps(
            {
                "lab": "ch03",
                "passed": contamination["clean"] and admission["admitted"] and (decision.decision in {"ship", "no_ship"}),
                "decision": decision.decision,
                "selected": decision.selected_candidate_id,
                "contamination_blocked": not contamination["clean"],
                "safety_regression_injected": inject_safety_regression,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return payload
