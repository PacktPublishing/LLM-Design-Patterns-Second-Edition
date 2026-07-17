"""Data intake, splits, contamination, admission, and release decision."""

from __future__ import annotations

import hashlib
import json
import re
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


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def load_records(path: Path) -> list[DataRecord]:
    records: list[DataRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        if "content_hash" not in data:
            data["content_hash"] = content_hash(data["text"])
        rec = DataRecord.model_validate(data)
        if not rec.rights_basis or not rec.source_ref:
            raise ValueError(f"record {rec.record_id} missing rights/provenance")
        records.append(rec)
    return records


def build_dataset_manifest(dataset_id: str, records: list[DataRecord]) -> DatasetManifest:
    m = DatasetManifest(dataset_id=dataset_id, record_ids=[r.record_id for r in records])
    m.content_hash = "sha256:" + hashlib.sha256(
        canonical_json(m.model_dump(mode="json")).encode()
    ).hexdigest()
    return m


def deterministic_split(records: list[DataRecord]) -> SplitManifest:
    """Split by stable entity_key hash buckets — not random row shuffle."""
    train, val, protected = [], [], []
    for rec in sorted(records, key=lambda r: r.entity_key):
        bucket = int(hashlib.sha256(rec.entity_key.encode()).hexdigest()[:8], 16) % 10
        if bucket <= 5:
            train.append(rec.record_id)
        elif bucket <= 7:
            val.append(rec.record_id)
        else:
            protected.append(rec.record_id)
    # Ensure non-empty protected for lab determinism
    if not protected and val:
        protected.append(val.pop())
    if not train and val:
        train.append(val.pop())
    split = SplitManifest(
        split_id="entity-hash-v1", train=train, validation=val, protected_test=protected
    )
    split.content_hash = "sha256:" + hashlib.sha256(
        canonical_json(split.model_dump(mode="json")).encode()
    ).hexdigest()
    return split


def contamination_report(
    train_records: list[DataRecord],
    eval_texts: list[str],
) -> dict[str, Any]:
    train_exact = {r.content_hash for r in train_records}
    train_norm = {normalize_text(r.text) for r in train_records}
    exact_hits = []
    norm_hits = []
    near_hits = []
    for text in eval_texts:
        h = content_hash(text)
        n = normalize_text(text)
        if h in train_exact:
            exact_hits.append(h)
        if n in train_norm:
            norm_hits.append(n)
        # Near-duplicate: normalized Jaccard on tokens > 0.9 against any train
        tokens = set(n.split())
        for tr in train_records:
            tt = set(normalize_text(tr.text).split())
            if not tokens or not tt:
                continue
            j = len(tokens & tt) / len(tokens | tt)
            if j >= 0.9 and n != normalize_text(tr.text):
                near_hits.append({"eval": n, "train": tr.record_id, "jaccard": j})
    clean = not (exact_hits or norm_hits or near_hits)
    return {
        "clean": clean,
        "exact_hits": exact_hits,
        "normalized_hits": norm_hits,
        "near_duplicate_hits": near_hits,
    }


def admit_adapter(artifact: ModelArtifact, expected_hash: str) -> bool:
    if artifact.content_hash != expected_hash:
        return False
    if not artifact.license or artifact.license.lower() in {"unknown", "none"}:
        return False
    if not artifact.base_model:
        return False
    path = Path(artifact.path)
    return path.exists()


def evaluate_candidates(
    *,
    baseline_metrics: dict[str, float],
    candidates: list[AdaptationCandidate],
    safety_floor: float = 1.0,
) -> ReleaseDecision:
    """Pick best candidate that clears zero-tolerance safety and does not regress CPSO badly."""
    gates: dict[str, bool] = {}
    eligible: list[AdaptationCandidate] = []
    for c in candidates:
        safety = c.metrics.get("safety", 0.0)
        quality = c.metrics.get("quality", 0.0)
        safe_ok = safety >= safety_floor
        quality_ok = quality >= baseline_metrics.get("quality", 0.0) - 1e-9
        cost_ok = c.metrics.get("cost", 0.0) <= baseline_metrics.get("cost", 0.0) + 0.01
        gates[f"{c.candidate_id}.safety"] = safe_ok
        gates[f"{c.candidate_id}.quality_non_regress"] = quality_ok
        gates[f"{c.candidate_id}.cost"] = cost_ok
        if safe_ok and quality_ok and cost_ok:
            eligible.append(c)

    if not eligible:
        baseline = next(c for c in candidates if c.kind == CandidateKind.BASELINE)
        return ReleaseDecision(
            decision="no_ship",
            selected_candidate_id=baseline.candidate_id,
            approver_role="release_reviewer",
            rollback_target=baseline.rollback_target,
            gate_evidence=gates,
            residual_risks=["no candidate cleared mandatory gates"],
            review_by="next-sprint",
        )

    # Prefer highest quality among eligible; ties → prefer simpler kind order
    kind_rank = {
        CandidateKind.BASELINE: 0,
        CandidateKind.PROMPT: 1,
        CandidateKind.RETRIEVAL_REPLAY: 2,
        CandidateKind.ADAPTER: 3,
    }
    winner = sorted(
        eligible,
        key=lambda c: (-c.metrics.get("quality", 0.0), kind_rank[c.kind]),
    )[0]
    # If winner is baseline, still ship baseline (no adaptation)
    decision = "ship" if winner.kind != CandidateKind.BASELINE else "no_ship"
    # Clarification: shipping baseline is an explicit no-adaptation decision.
    if winner.kind == CandidateKind.BASELINE:
        decision = "no_ship"
    else:
        decision = "ship"
    return ReleaseDecision(
        decision=decision,
        selected_candidate_id=winner.candidate_id,
        approver_role="release_reviewer",
        rollback_target=winner.rollback_target,
        gate_evidence=gates,
        residual_risks=[],
        review_by="90d",
    )


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
    by_id = {r.record_id: r for r in records}
    train = [by_id[i] for i in split.train]
    protected_texts = [by_id[i].text for i in split.protected_test]
    # Chapter 2 holdout-style texts
    eval_texts = list(protected_texts)
    if inject_contamination and train:
        eval_texts.append(train[0].text)

    contam = contamination_report(train, eval_texts)
    adapter_bytes = adapter_path.read_bytes()
    adapter_hash = "sha256:" + hashlib.sha256(adapter_bytes).hexdigest()
    artifact = ModelArtifact(
        artifact_id="adapter-fixture-v1",
        path=str(adapter_path),
        content_hash=adapter_hash,
        license="Apache-2.0",
        base_model="policyops-replay-v1",
    )
    admitted = admit_adapter(artifact, adapter_hash)

    baseline_metrics = {"quality": 0.80, "safety": 1.0, "cost": 0.01, "latency_ms": 40.0}
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
            metrics={"quality": 0.82, "safety": 1.0, "cost": 0.01, "latency_ms": 42.0},
        ),
        AdaptationCandidate(
            candidate_id="retrieval-replay-v1",
            kind=CandidateKind.RETRIEVAL_REPLAY,
            model_ref="fixture-retrieval",
            configuration_hash="sha256:retrieval",
            rollback_target="baseline",
            metrics={"quality": 0.85, "safety": 1.0, "cost": 0.012, "latency_ms": 55.0},
        ),
        AdaptationCandidate(
            candidate_id="adapter-v1",
            kind=CandidateKind.ADAPTER,
            model_ref=artifact.base_model,
            artifact_hashes={"adapter": adapter_hash},
            configuration_hash="sha256:adapter",
            rollback_target="baseline",
            metrics={
                "quality": 0.88,
                "safety": 0.5 if inject_safety_regression else 1.0,
                "cost": 0.015,
                "latency_ms": 60.0,
            },
        ),
    ]

    gates_block = (not contam["clean"]) or (not admitted)
    if gates_block:
        decision = ReleaseDecision(
            decision="no_ship",
            selected_candidate_id="baseline",
            approver_role="release_reviewer",
            rollback_target="baseline",
            gate_evidence={
                "contamination_clean": contam["clean"],
                "adapter_admitted": admitted,
            },
            residual_risks=["blocked before candidate comparison"],
        )
    else:
        decision = evaluate_candidates(
            baseline_metrics=baseline_metrics, candidates=candidates
        )

    experiment = ExperimentRun(
        experiment_id="exp-ch03-fixture",
        dataset_hash=dataset.content_hash or "",
        split_hash=split.content_hash or "",
        baseline_suite_hash="sha256:ch02-baseline",
        candidate_ids=[c.candidate_id for c in candidates],
        contamination_clean=contam["clean"],
        gates={
            "contamination_clean": contam["clean"],
            "adapter_admitted": admitted,
            "decision_ship": decision.decision == "ship",
        },
    )

    payload = {
        "dataset": dataset.model_dump(mode="json"),
        "split": split.model_dump(mode="json"),
        "contamination": contam,
        "artifact": artifact.model_dump(mode="json"),
        "experiment": experiment.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
    }
    (evidence_dir / "adaptation_report.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (evidence_dir / "result.json").write_text(
        json.dumps(
            {
                "lab": "ch03",
                "passed": contam["clean"]
                and admitted
                and (
                    decision.decision in {"ship", "no_ship"}
                ),
                "decision": decision.decision,
                "selected": decision.selected_candidate_id,
                "contamination_blocked": not contam["clean"],
                "safety_regression_injected": inject_safety_regression,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return payload
