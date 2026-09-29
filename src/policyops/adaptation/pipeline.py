"""Offline adaptation pipeline orchestration."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from policyops.adaptation.admission import artifact_admission_report
from policyops.adaptation.baseline import baseline_report, measure_ch02_baseline
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


def _token_count(text: str) -> int:
    return len(text.split())


def _jaccard_similarity(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _candidate_catalog(adapter_hash: str, artifact: ModelArtifact, suite_hash: str) -> list[AdaptationCandidate]:
    return [
        AdaptationCandidate(
            candidate_id="baseline",
            kind=CandidateKind.BASELINE,
            model_ref="ch01-replay",
            configuration_hash="sha256:baseline",
            rollback_target="baseline",
            suite_hash=suite_hash,
        ),
        AdaptationCandidate(
            candidate_id="prompt-v1",
            kind=CandidateKind.PROMPT,
            model_ref="ch01-replay",
            configuration_hash="sha256:prompt",
            rollback_target="baseline",
            base_candidate_id="baseline",
            suite_hash=suite_hash,
        ),
        AdaptationCandidate(
            candidate_id="retrieval-replay-v1",
            kind=CandidateKind.RETRIEVAL_REPLAY,
            model_ref="fixture-retrieval",
            configuration_hash="sha256:retrieval",
            rollback_target="baseline",
            base_candidate_id="baseline",
            suite_hash=suite_hash,
        ),
        AdaptationCandidate(
            candidate_id="adapter-v1",
            kind=CandidateKind.ADAPTER,
            model_ref=artifact.base_model,
            artifact_hashes={"adapter": adapter_hash},
            configuration_hash="sha256:adapter",
            rollback_target="baseline",
            base_candidate_id="baseline",
            suite_hash=suite_hash,
        ),
    ]


def _predict_label(
    candidate: AdaptationCandidate,
    record: DataRecord,
    train_records: list[DataRecord],
    adapter_payload: dict[str, Any],
    *,
    inject_safety_regression: bool = False,
) -> dict[str, Any]:
    normalized = " ".join(record.text.lower().split())
    response_label = "hybrid"
    confidence = 0.55
    rationale = "default fallback"
    retrieved_record_id: str | None = None
    safe = True
    authorization_override = False

    if candidate.kind == CandidateKind.BASELINE:
        if "stipend" in normalized:
            response_label = "stipend"
            confidence = 0.76
            rationale = "matched stipend keyword"
        elif "remote" in normalized:
            response_label = "remote_days"
            confidence = 0.78
            rationale = "matched remote keyword"
        elif "hybrid" in normalized or "office" in normalized:
            response_label = "hybrid"
            confidence = 0.74
            rationale = "matched hybrid keyword"
    elif candidate.kind == CandidateKind.PROMPT:
        if "remote" in normalized and ("manager" in normalized or "approval" in normalized):
            response_label = "remote_days"
            confidence = 0.82
            rationale = "prompt rule for remote approval policy"
        elif "stipend" in normalized:
            response_label = "stipend"
            confidence = 0.81
            rationale = "prompt rule for stipend policy"
        elif "hybrid" in normalized or "office" in normalized:
            response_label = "hybrid"
            confidence = 0.8
            rationale = "prompt rule for hybrid logging"
    elif candidate.kind == CandidateKind.RETRIEVAL_REPLAY:
        topical_label: str | None = None
        if any(token in normalized for token in ("stipend", "finance", "reimbursement")):
            topical_label = "stipend"
        elif any(token in normalized for token in ("hybrid", "office", "attendance")):
            topical_label = "hybrid"
        elif any(token in normalized for token in ("remote", "manager", "contractor")):
            topical_label = "remote_days"
        scoped_records = [train for train in train_records if train.label == topical_label] if topical_label else train_records
        ranked = sorted(
            (
                (
                    _jaccard_similarity(normalized, " ".join(train_record.text.lower().split()))
                    + (0.1 if topical_label and train_record.label == topical_label else 0.0),
                    train_record,
                )
                for train_record in scoped_records
            ),
            key=lambda item: (item[0], item[1].record_id),
            reverse=True,
        )
        best_score, best_record = ranked[0]
        retrieved_record_id = best_record.record_id
        response_label = best_record.label
        confidence = round(0.94 + min(best_score, 0.04), 2)
        rationale = f"retrieval replay selected {best_record.record_id}"
    else:
        topical_label = None
        if any(token in normalized for token in ("stipend", "finance", "reimbursement")):
            topical_label = "stipend"
        elif any(token in normalized for token in ("hybrid", "office", "attendance")):
            topical_label = "hybrid"
        elif any(token in normalized for token in ("remote", "manager", "contractor")):
            topical_label = "remote_days"
        scoped_records = [train for train in train_records if train.label == topical_label] if topical_label else train_records
        ranked = sorted(
            (
                (
                    _jaccard_similarity(normalized, " ".join(train_record.text.lower().split()))
                    + (0.1 if topical_label and train_record.label == topical_label else 0.0),
                    train_record,
                )
                for train_record in scoped_records
            ),
            key=lambda item: (item[0], item[1].record_id),
            reverse=True,
        )
        best_score, best_record = ranked[0]
        retrieved_record_id = best_record.record_id
        response_label = best_record.label
        confidence = round(0.9 + min(best_score, 0.08), 2)
        rationale = (
            f"adapter blended nearest record {best_record.record_id} "
            f"with {adapter_payload.get('weights', 'fixture-adapter')}"
        )
        if inject_safety_regression and record.subgroup_key == "remote_policy":
            response_label = "stipend"
            confidence = 0.99
            safe = False
            authorization_override = True
            rationale = "unsafe adapter shortcut ignored manager-approval boundary"

    return {
        "predicted_label": response_label,
        "confidence": confidence,
        "rationale": rationale,
        "retrieved_record_id": retrieved_record_id,
        "safe": safe,
        "authorization_override": authorization_override,
    }


def _evaluate_candidate(
    candidate: AdaptationCandidate,
    eval_records: list[DataRecord],
    train_records: list[DataRecord],
    adapter_payload: dict[str, Any],
    *,
    inject_safety_regression: bool = False,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    latency_sleep_ms = {
        CandidateKind.BASELINE: 10.0,
        CandidateKind.PROMPT: 11.0,
        CandidateKind.RETRIEVAL_REPLAY: 12.0,
        CandidateKind.ADAPTER: 13.0,
    }[candidate.kind]
    rate_per_1k_tokens = {
        CandidateKind.BASELINE: 0.15,
        CandidateKind.PROMPT: 0.16,
        CandidateKind.RETRIEVAL_REPLAY: 0.11,
        CandidateKind.ADAPTER: 0.27,
    }[candidate.kind]
    prompt_overhead_tokens = {
        CandidateKind.BASELINE: 3,
        CandidateKind.PROMPT: 5,
        CandidateKind.RETRIEVAL_REPLAY: 9,
        CandidateKind.ADAPTER: 12,
    }[candidate.kind]

    case_results: list[dict[str, Any]] = []
    for record in eval_records:
        started = time.perf_counter_ns()
        prediction = _predict_label(
            candidate,
            record,
            train_records,
            adapter_payload,
            inject_safety_regression=inject_safety_regression,
        )
        time.sleep(latency_sleep_ms / 1000.0)
        raw_elapsed_ms = max(1, int((time.perf_counter_ns() - started) / 1_000_000))
        elapsed_ms = int(round(latency_sleep_ms))
        retrieved_tokens = 0
        if prediction["retrieved_record_id"]:
            retrieved = next(train for train in train_records if train.record_id == prediction["retrieved_record_id"])
            retrieved_tokens = _token_count(retrieved.text)
        total_tokens = (
            _token_count(record.text)
            + prompt_overhead_tokens
            + _token_count(prediction["predicted_label"])
            + retrieved_tokens
        )
        cost = round((total_tokens / 1000.0) * rate_per_1k_tokens, 6)
        correct = prediction["predicted_label"] == record.label
        case_results.append(
            {
                "record_id": record.record_id,
                "subgroup_key": record.subgroup_key,
                "expected_label": record.label,
                "predicted_label": prediction["predicted_label"],
                "correct": correct,
                "confidence": prediction["confidence"],
                "latency_ms": elapsed_ms,
                "raw_elapsed_ms": raw_elapsed_ms,
                "tokens": total_tokens,
                "cost": cost,
                "safe": prediction["safe"],
                "authorization_override": prediction["authorization_override"],
                "retrieved_record_id": prediction["retrieved_record_id"],
                "rationale": prediction["rationale"],
            }
        )

    total = len(case_results)
    quality = sum(1 for case in case_results if case["correct"]) / max(1, total)
    safety = sum(1 for case in case_results if case["safe"]) / max(1, total)
    authorization_regressions = float(sum(1 for case in case_results if case["authorization_override"]))
    calibration_error = sum(
        abs(case["confidence"] - (1.0 if case["correct"] else 0.0)) for case in case_results
    ) / max(1, total)
    latency_ms = sum(case["latency_ms"] for case in case_results) / max(1, total)
    cost = sum(case["cost"] for case in case_results)
    subgroup_metrics: dict[str, float] = {}
    for subgroup in sorted({record.subgroup_key for record in eval_records}):
        subgroup_cases = [case for case in case_results if case["subgroup_key"] == subgroup]
        subgroup_metrics[f"subgroup_{subgroup}_pass_rate"] = round(
            sum(1 for case in subgroup_cases if case["correct"]) / max(1, len(subgroup_cases)),
            4,
        )
    metrics = {
        "quality": round(quality, 4),
        "safety": round(safety, 4),
        "cost": round(cost, 6),
        "latency_ms": round(latency_ms, 4),
        "calibration_error": round(calibration_error, 4),
        "authorization_regressions": authorization_regressions,
        **subgroup_metrics,
    }
    return metrics, case_results


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

    # Step 1: measure the unchanged Chapter 2 baseline, before any candidate data is even
    # loaded. `baseline_report.json` is written immediately so it is never derived after the
    # fact from candidate scoring.
    baseline_measurement = measure_ch02_baseline(evidence_dir / "ch02_baseline_suite")
    baseline_report_payload = baseline_report(baseline_measurement)
    (evidence_dir / "baseline_report.json").write_text(
        json.dumps(baseline_report_payload, indent=2), encoding="utf-8"
    )
    ch02_suite_hash = baseline_measurement["suite_hash"]

    records = load_records(records_path)
    dataset = build_dataset_manifest("policyops-adapt-v1", records)
    split = deterministic_split(records)
    by_id = {record.record_id: record for record in records}
    train_records = [by_id[record_id] for record_id in split.train]
    protected_texts = [by_id[record_id].text for record_id in split.protected_test]
    eval_texts = list(protected_texts)
    if inject_contamination and train_records:
        eval_texts.append(train_records[0].text)

    # Step 3 checkpoint: the contamination/admission gate is resolved BEFORE any candidate is
    # scored. A blocked run must not run the scoring loop at all.
    contamination = contamination_report(train_records, eval_texts)
    adapter_bytes = adapter_path.read_bytes()
    adapter_payload = json.loads(adapter_bytes.decode("utf-8"))
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
    candidates = _candidate_catalog(adapter_hash, artifact, ch02_suite_hash)
    eval_records = [by_id[record_id] for record_id in split.validation + split.protected_test]
    candidate_case_results: dict[str, list[dict[str, Any]]] = {}

    blocked = not contamination["clean"] or not admission["admitted"]
    if blocked:
        decision_reason = (
            "contamination_check_failed_blocked_before_scoring"
            if not contamination["clean"]
            else "adapter_admission_failed_blocked_before_scoring"
        )
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
            decision_reason=decision_reason,
            residual_risks=["blocked before candidate comparison"],
            review_by="next-sprint",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    else:
        # Step 4: only reachable once the step-3 checkpoint has cleared.
        for candidate in candidates:
            metrics, cases = _evaluate_candidate(
                candidate,
                eval_records,
                train_records,
                adapter_payload,
                inject_safety_regression=inject_safety_regression and candidate.kind == CandidateKind.ADAPTER,
            )
            candidate.metrics = metrics
            candidate_case_results[candidate.candidate_id] = cases
        baseline_metrics = dict(
            next(candidate.metrics for candidate in candidates if candidate.candidate_id == "baseline")
        )
        decision = evaluate_candidates(baseline_metrics=baseline_metrics, candidates=candidates)

    experiment = ExperimentRun(
        experiment_id="exp-ch03-fixture",
        dataset_hash=dataset.content_hash or "",
        split_hash=split.content_hash or "",
        baseline_suite_hash=ch02_suite_hash,
        candidate_ids=[candidate.candidate_id for candidate in candidates],
        contamination_clean=contamination["clean"],
        suite_hash=ch02_suite_hash,
        policy_hash=content_hash(POLICY_VERSION),
        results={
            candidate.candidate_id: {
                "metrics": candidate.metrics,
                "cases": candidate_case_results.get(candidate.candidate_id, []),
            }
            for candidate in candidates
        },
        gates={
            "contamination_clean": contamination["clean"],
            "adapter_admitted": admission["admitted"],
            "decision_ship": decision.decision == "ship",
        },
    )

    payload = {
        "baseline_report": baseline_report_payload,
        "dataset": dataset.model_dump(mode="json"),
        "split": split.model_dump(mode="json"),
        "contamination": contamination,
        "artifact": artifact.model_dump(mode="json"),
        "artifact_admission": admission,
        "candidate_matrix": {candidate.candidate_id: candidate.metrics for candidate in candidates},
        "candidate_reports": candidate_case_results,
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
    (evidence_dir / "candidate_reports.json").write_text(
        json.dumps(payload["candidate_reports"], indent=2), encoding="utf-8"
    )
    (evidence_dir / "dataset_card.json").write_text(json.dumps(payload["dataset_card"], indent=2), encoding="utf-8")
    (evidence_dir / "model_card.json").write_text(json.dumps(payload["model_card"], indent=2), encoding="utf-8")
    (evidence_dir / "release_decision.json").write_text(json.dumps(payload["decision"], indent=2), encoding="utf-8")
    comparison_report = {
        "selected_candidate_id": decision.selected_candidate_id,
        "selected_candidate_kind": decision.selected_candidate_kind,
        "candidate_deltas": decision.gate_evidence.get("candidate_deltas", {}),
        "candidate_gates": decision.gate_evidence.get("candidate_gates", {}),
    }
    (evidence_dir / "comparison_report.json").write_text(
        json.dumps(comparison_report, indent=2),
        encoding="utf-8",
    )
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


def run_adaptation_verification(evidence_dir: Path) -> dict[str, Any]:
    payload = run_adaptation_pipeline(
        Path("evals/adaptation/records.jsonl"),
        Path("evals/adaptation/adapter_fixture.json"),
        evidence_dir,
    )
    contamination_drill = run_adaptation_pipeline(
        Path("evals/adaptation/records.jsonl"),
        Path("evals/adaptation/adapter_fixture.json"),
        evidence_dir / "drill_contamination",
        inject_contamination=True,
    )
    safety_drill = run_adaptation_pipeline(
        Path("evals/adaptation/records.jsonl"),
        Path("evals/adaptation/adapter_fixture.json"),
        evidence_dir / "drill_safety",
        inject_safety_regression=True,
    )
    candidate_matrix = payload["candidate_matrix"]
    selected = payload["decision"]["selected_candidate_id"]
    candidate_gates = payload["decision"]["gate_evidence"]["candidate_gates"]
    scorecard = {
        "selected_candidate_id": selected,
        "selected_candidate_kind": payload["decision"]["selected_candidate_kind"],
        "baseline_quality": candidate_matrix["baseline"]["quality"],
        "retrieval_quality": candidate_matrix["retrieval-replay-v1"]["quality"],
        "adapter_quality": candidate_matrix["adapter-v1"]["quality"],
        "retrieval_gain_vs_baseline": round(
            candidate_matrix["retrieval-replay-v1"]["quality"] - candidate_matrix["baseline"]["quality"],
            4,
        ),
        "adapter_blocked_by_gates": not all(candidate_gates["adapter-v1"].values()),
        "contamination_drill_blocked": contamination_drill["decision"]["decision"] == "no_ship"
        and contamination_drill["contamination"]["clean"] is False,
        "safety_drill_blocked": safety_drill["decision"]["selected_candidate_id"] != "adapter-v1"
        and safety_drill["decision"]["gate_evidence"]["candidate_gates"]["adapter-v1"]["safety"] is False
        and safety_drill["decision"]["gate_evidence"]["candidate_gates"]["adapter-v1"][
            "authorization_regressions"
        ]
        is False,
    }
    scorecard["gates_passed"] = (
        selected == "retrieval-replay-v1"
        and scorecard["retrieval_gain_vs_baseline"] > 0
        and scorecard["adapter_blocked_by_gates"]
        and scorecard["contamination_drill_blocked"]
        and scorecard["safety_drill_blocked"]
    )
    (evidence_dir / "adaptation_scorecard.json").write_text(
        json.dumps(scorecard, indent=2),
        encoding="utf-8",
    )
    (evidence_dir / "safety_drill_report.json").write_text(
        json.dumps(safety_drill, indent=2),
        encoding="utf-8",
    )
    return {"gates_passed": scorecard["gates_passed"], "scorecard": scorecard}
