"""Decision policy and candidate comparison for Chapter 3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from policyops.adaptation.schemas import AdaptationCandidate, CandidateKind, DatasetManifest, ReleaseDecision
from policyops.adaptation.intake import hash_payload

POLICY_VERSION = "adaptation-policy-v2"


def default_release_policy() -> dict[str, Any]:
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


def cost_per_successful_outcome(metrics: dict[str, float]) -> float:
    quality = max(metrics.get("quality", 0.0), 1e-6)
    return metrics.get("cost", 0.0) / quality


def evaluate_candidates(
    *,
    baseline_metrics: dict[str, float],
    candidates: list[AdaptationCandidate],
    release_policy: dict[str, Any] | None = None,
) -> ReleaseDecision:
    """Pick the smallest justified candidate that clears all mandatory gates."""

    policy = release_policy or default_release_policy()
    baseline_cpso = cost_per_successful_outcome(baseline_metrics)
    candidate_gate_details: dict[str, dict[str, bool]] = {}
    candidate_metric_details: dict[str, dict[str, float]] = {}
    candidate_delta_details: dict[str, dict[str, float]] = {}
    eligible: list[AdaptationCandidate] = []
    for candidate in candidates:
        metrics = candidate.metrics
        subgroup_rates = [
            value for key, value in metrics.items() if key.startswith("subgroup_") and key.endswith("_pass_rate")
        ]
        min_subgroup_rate = min(subgroup_rates) if subgroup_rates else 1.0
        cpso = cost_per_successful_outcome(metrics)
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
        candidate_metric_details[candidate.candidate_id] = metrics
        candidate_delta_details[candidate.candidate_id] = {
            "quality_delta": round(metrics.get("quality", 0.0) - baseline_metrics.get("quality", 0.0), 4),
            "latency_delta_pct": round(
                (
                    (
                        metrics.get("latency_ms", 0.0) - baseline_metrics.get("latency_ms", 0.0)
                    )
                    / max(baseline_metrics.get("latency_ms", 1.0), 1.0)
                )
                * 100,
                4,
            ),
            "cost_delta": round(metrics.get("cost", 0.0) - baseline_metrics.get("cost", 0.0), 6),
            "cpso_delta_pct": round(((cpso - baseline_cpso) / max(baseline_cpso, 1e-6)) * 100, 4),
            "min_subgroup_pass_rate": round(min_subgroup_rate, 4),
        }
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
                "candidate_metrics": candidate_metric_details,
                "candidate_deltas": candidate_delta_details,
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
            cost_per_successful_outcome(candidate.metrics),
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
            "candidate_metrics": candidate_metric_details,
            "candidate_deltas": candidate_delta_details,
        },
        decision_reason="best_eligible_candidate_selected" if winner.kind != CandidateKind.BASELINE else "baseline_retained",
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
