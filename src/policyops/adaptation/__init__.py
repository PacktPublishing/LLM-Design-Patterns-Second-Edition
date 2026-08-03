"""Data intake, splits, contamination, admission, and release decision."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from policyops.adaptation.schemas import (
    AdaptationCandidate,
    CandidateKind,
    DataRecord,
    DatasetManifest,
    ExperimentRun,
    ModelArtifact,
    ReleaseDecision,
    SplitManifest,
)
from policyops.util import canonical_json

RIGHTS_ALLOWLIST = {"internal-licensed", "synthetic-lab", "public-demo"}
LICENSE_ALLOWLIST = {"apache-2.0", "mit", "bsd-3-clause"}
SAFE_ARTIFACT_FORMATS = {"fixture-adapter"}
SAFE_LOAD_POLICIES = {"json-safe-load"}
SECRET_RE = re.compile(r"SECRET_[A-Z0-9_]+|sk-[A-Za-z0-9_-]{8,}", re.I)
POTENTIAL_PII_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
POLICY_VERSION = "adaptation-policy-v2"


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def hash_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _default_subgroup(record: dict[str, Any]) -> str:
    if record.get("label") == "remote_days":
        return "remote_policy"
    if record.get("synthetic"):
        return "synthetic_reviewed"
    return "general_policy"


def _record_rule_violations(record: DataRecord) -> list[str]:
    violations: list[str] = []
    if record.rights_basis not in RIGHTS_ALLOWLIST:
        violations.append("rights_basis_unsupported")
    if not record.source_ref:
        violations.append("source_ref_missing")
    if not record.owner:
        violations.append("owner_missing")
    if not record.provenance_chain:
        violations.append("provenance_chain_missing")
    if record.synthetic and (not record.generator_config or not record.derived_from):
        violations.append("synthetic_lineage_incomplete")
    if SECRET_RE.search(record.text) or POTENTIAL_PII_RE.search(record.text):
        violations.append("sensitive_text_detected")
    return violations


def load_records(path: Path) -> list[DataRecord]:
    records: list[DataRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        data.setdefault("content_hash", content_hash(data["text"]))
        data.setdefault("provenance_chain", [data.get("source_ref", "")])
        data.setdefault("subgroup_key", _default_subgroup(data))
        rec = DataRecord.model_validate(data)
        violations = _record_rule_violations(rec)
        if violations:
            raise ValueError(f"record {rec.record_id} failed validation: {','.join(sorted(violations))}")
        records.append(rec)
    return records


def build_dataset_manifest(dataset_id: str, records: list[DataRecord]) -> DatasetManifest:
    source_breakdown: dict[str, int] = {}
    synthetic_record_ids: list[str] = []
    rights_bases = sorted({record.rights_basis for record in records})
    lineage_payload: dict[str, Any] = {}
    for record in records:
        source_breakdown[record.source_ref] = source_breakdown.get(record.source_ref, 0) + 1
        lineage_payload[record.record_id] = {
            "content_hash": record.content_hash,
            "provenance_chain": record.provenance_chain,
            "derived_from": record.derived_from,
            "deletion_scope": record.deletion_scope,
        }
        if record.synthetic:
            synthetic_record_ids.append(record.record_id)
    manifest = DatasetManifest(
        dataset_id=dataset_id,
        record_ids=[record.record_id for record in records],
        record_count=len(records),
        source_breakdown=source_breakdown,
        rights_bases=rights_bases,
        synthetic_record_ids=sorted(synthetic_record_ids),
        lineage_hash=hash_payload(lineage_payload),
    )
    manifest.content_hash = hash_payload(manifest.model_dump(mode="json"))
    return manifest


def deterministic_split(records: list[DataRecord]) -> SplitManifest:
    """Split by stable entity/subgroup hash buckets — not random row shuffle."""

    train, val, protected = [], [], []
    subgroup_membership: dict[str, list[str]] = {}
    protected_entity_keys: set[str] = set()
    for rec in sorted(records, key=lambda r: (r.subgroup_key, r.entity_key, r.record_id)):
        subgroup_membership.setdefault(rec.subgroup_key, []).append(rec.record_id)
        bucket_key = f"{rec.entity_key}:{rec.subgroup_key}"
        bucket = int(hashlib.sha256(bucket_key.encode()).hexdigest()[:8], 16) % 10
        if bucket <= 5:
            train.append(rec.record_id)
        elif bucket <= 7:
            val.append(rec.record_id)
        else:
            protected.append(rec.record_id)
            protected_entity_keys.add(rec.entity_key)
    if not protected and val:
        moved = val.pop()
        protected.append(moved)
        protected_entity_keys.add(next(rec.entity_key for rec in records if rec.record_id == moved))
    if not train and val:
        train.append(val.pop())
    split = SplitManifest(
        split_id="entity-group-hash-v1",
        train=train,
        validation=val,
        protected_test=protected,
        protected_entity_keys=sorted(protected_entity_keys),
        subgroup_membership={key: sorted(value) for key, value in subgroup_membership.items()},
    )
    split.content_hash = hash_payload(split.model_dump(mode="json"))
    return split


def contamination_report(
    train_records: list[DataRecord],
    eval_texts: list[str],
) -> dict[str, Any]:
    train_exact = {record.content_hash: record.record_id for record in train_records}
    train_norm = {normalize_text(record.text): record.record_id for record in train_records}
    exact_hits: list[dict[str, str]] = []
    norm_hits: list[dict[str, str]] = []
    near_hits: list[dict[str, Any]] = []
    for eval_index, text in enumerate(eval_texts):
        hashed = content_hash(text)
        normalized = normalize_text(text)
        if hashed in train_exact:
            exact_hits.append({"eval_index": str(eval_index), "train_record_id": train_exact[hashed]})
        if normalized in train_norm:
            norm_hits.append({"eval_index": str(eval_index), "train_record_id": train_norm[normalized]})
        tokens = set(normalized.split())
        for train_record in train_records:
            train_tokens = set(normalize_text(train_record.text).split())
            if not tokens or not train_tokens:
                continue
            jaccard = len(tokens & train_tokens) / len(tokens | train_tokens)
            if jaccard >= 0.9 and normalized != normalize_text(train_record.text):
                near_hits.append(
                    {
                        "eval_index": eval_index,
                        "train_record_id": train_record.record_id,
                        "jaccard": round(jaccard, 3),
                    }
                )
    clean = not (exact_hits or norm_hits or near_hits)
    return {
        "clean": clean,
        "exact_hits": exact_hits,
        "normalized_hits": norm_hits,
        "near_duplicate_hits": near_hits,
    }


def artifact_admission_report(
    artifact: ModelArtifact,
    expected_hash: str,
    *,
    expected_base_model: str = "policyops-replay-v1",
) -> dict[str, Any]:
    reasons: list[str] = []
    path = Path(artifact.path)
    if artifact.content_hash != expected_hash:
        reasons.append("hash_mismatch")
    if artifact.license.lower() not in LICENSE_ALLOWLIST:
        reasons.append("license_unapproved")
    if not artifact.base_model or artifact.base_model != expected_base_model:
        reasons.append("base_model_incompatible")
    if artifact.format not in SAFE_ARTIFACT_FORMATS:
        reasons.append("format_unsupported")
    if artifact.load_policy not in SAFE_LOAD_POLICIES:
        reasons.append("load_policy_unsupported")
    if not path.exists():
        reasons.append("artifact_missing")
    else:
        raw_bytes = path.read_bytes()
        actual_hash = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
        if actual_hash != expected_hash or actual_hash != artifact.content_hash:
            reasons.append("artifact_bytes_hash_mismatch")
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            reasons.append("artifact_not_json")
        else:
            if payload.get("format") != artifact.format:
                reasons.append("format_metadata_mismatch")
            if payload.get("base_model") != artifact.base_model:
                reasons.append("artifact_base_model_mismatch")
            if payload.get("license", "").lower() != artifact.license.lower():
                reasons.append("artifact_license_mismatch")
            if {"script", "entrypoint", "pickle_loader"} & set(payload):
                reasons.append("unsafe_loader_fields_present")
    return {
        "admitted": not reasons,
        "reasons": reasons,
        "artifact_id": artifact.artifact_id,
        "expected_hash": expected_hash,
    }


def admit_adapter(artifact: ModelArtifact, expected_hash: str) -> bool:
    return artifact_admission_report(artifact, expected_hash)["admitted"]


def _default_release_policy() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "gates": {
            "safety": {"operator": "gte", "value": 1.0, "mandatory": True},
            "authorization_regressions": {"operator": "eq", "value": 0, "mandatory": True},
            "subgroup_min_pass_rate": {"operator": "gte", "value": 0.90, "mandatory": True},
            "calibration_error": {"operator": "lte", "value": 0.10, "mandatory": True},
            "latency_delta_pct": {"operator": "lte", "value": 20.0, "mandatory": True},
            "cost_delta": {"operator": "lte", "value": 0.01, "mandatory": True},
            "cpso_delta_pct": {"operator": "lte", "value": 15.0, "mandatory": True},
            "quality_non_regress": {"operator": "gte", "value": 0.0, "mandatory": True},
        },
        "decision_on_any_mandatory_failure": "retain_baseline",
    }


def _cost_per_successful_outcome(metrics: dict[str, float]) -> float:
    quality = max(metrics.get("quality", 0.0), 1e-6)
    return metrics.get("cost", 0.0) / quality


def evaluate_candidates(
    *,
    baseline_metrics: dict[str, float],
    candidates: list[AdaptationCandidate],
    release_policy: dict[str, Any] | None = None,
) -> ReleaseDecision:
    """Pick the smallest justified candidate that clears all mandatory gates."""

    policy = release_policy or _default_release_policy()
    baseline_cpso = _cost_per_successful_outcome(baseline_metrics)
    gates: dict[str, bool] = {}
    candidate_gate_details: dict[str, dict[str, bool]] = {}
    eligible: list[AdaptationCandidate] = []
    for candidate in candidates:
        metrics = candidate.metrics
        subgroup_rates = [
            value for key, value in metrics.items() if key.startswith("subgroup_") and key.endswith("_pass_rate")
        ]
        min_subgroup_rate = min(subgroup_rates) if subgroup_rates else 1.0
        cpso = _cost_per_successful_outcome(metrics)
        candidate_gates = {
            "safety": metrics.get("safety", 0.0) >= 1.0,
            "authorization_regressions": metrics.get("authorization_regressions", 0.0) == 0.0,
            "subgroup_min_pass_rate": min_subgroup_rate >= 0.90,
            "calibration_error": metrics.get("calibration_error", 1.0) <= 0.10,
            "latency_delta_pct": metrics.get("latency_ms", 0.0)
            <= baseline_metrics.get("latency_ms", 0.0) * 1.20,
            "cost_delta": metrics.get("cost", 0.0) <= baseline_metrics.get("cost", 0.0) + 0.01,
            "cpso_delta_pct": cpso <= baseline_cpso * 1.15,
            "quality_non_regress": metrics.get("quality", 0.0) >= baseline_metrics.get("quality", 0.0),
        }
        candidate_gate_details[candidate.candidate_id] = candidate_gates
        for gate_name, passed in candidate_gates.items():
            gates[f"{candidate.candidate_id}.{gate_name}"] = passed
        if all(candidate_gates.values()):
            eligible.append(candidate)

    if not eligible:
        baseline = next(candidate for candidate in candidates if candidate.kind == CandidateKind.BASELINE)
        return ReleaseDecision(
            decision="no_ship",
            selected_candidate_id=baseline.candidate_id,
            selected_candidate_kind=baseline.kind.value,
            approver_role="release_reviewer",
            rollback_target=baseline.rollback_target,
            gate_evidence={
                "policy": policy,
                "candidate_gates": candidate_gate_details,
            },
            decision_reason="mandatory_gate_failed",
            residual_risks=["no candidate cleared mandatory gates"],
            review_by="next-sprint",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )

    kind_rank = {
        CandidateKind.BASELINE: 0,
        CandidateKind.PROMPT: 1,
        CandidateKind.RETRIEVAL_REPLAY: 2,
        CandidateKind.ADAPTER: 3,
    }
    winner = sorted(
        eligible,
        key=lambda candidate: (
            -candidate.metrics.get("quality", 0.0),
            _cost_per_successful_outcome(candidate.metrics),
            kind_rank[candidate.kind],
        ),
    )[0]
    decision = "ship" if winner.kind != CandidateKind.BASELINE else "no_ship"
    return ReleaseDecision(
        decision=decision,
        selected_candidate_id=winner.candidate_id,
        selected_candidate_kind=winner.kind.value,
        approver_role="release_reviewer",
        rollback_target=winner.rollback_target,
        gate_evidence={
            "policy": policy,
            "candidate_gates": candidate_gate_details,
        },
        decision_reason="best_eligible_candidate_selected"
        if winner.kind != CandidateKind.BASELINE
        else "baseline_retained",
        residual_risks=[] if winner.kind != CandidateKind.BASELINE else ["simplest candidate retained"],
        review_by="90d",
        expires_at=datetime.now(UTC) + timedelta(days=90),
    )


def plan_training_run(
    dataset: DatasetManifest,
    *,
    gpu_profile: str | None = None,
    hardware: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not gpu_profile or not hardware:
        raise ValueError("optional training requires gpu_profile and declared hardware")
    plan = {
        "dataset_hash": dataset.content_hash,
        "gpu_profile": gpu_profile,
        "hardware": hardware,
        "training_manifest_hash": hash_payload(
            {
                "dataset_hash": dataset.content_hash,
                "gpu_profile": gpu_profile,
                "hardware": hardware,
            }
        ),
    }
    plan["artifact_hash"] = hash_payload(plan)
    return plan


def _dataset_card(dataset: DatasetManifest, records: list[DataRecord]) -> dict[str, Any]:
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


def _model_card(candidates: list[AdaptationCandidate], artifact: ModelArtifact) -> dict[str, Any]:
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
        "dataset_card": _dataset_card(dataset, records),
        "model_card": _model_card(candidates, artifact),
    }
    (evidence_dir / "dataset_manifest.json").write_text(
        json.dumps(payload["dataset"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "split_manifest.json").write_text(
        json.dumps(payload["split"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "contamination_report.json").write_text(
        json.dumps(payload["contamination"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "artifact_admission.json").write_text(
        json.dumps(payload["artifact_admission"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "candidate_matrix.json").write_text(
        json.dumps(payload["candidate_matrix"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "dataset_card.json").write_text(
        json.dumps(payload["dataset_card"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "model_card.json").write_text(
        json.dumps(payload["model_card"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "release_decision.json").write_text(
        json.dumps(payload["decision"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "adaptation_report.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (evidence_dir / "result.json").write_text(
        json.dumps(
            {
                "lab": "ch03",
                "passed": contamination["clean"]
                and admission["admitted"]
                and (decision.decision in {"ship", "no_ship"}),
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
