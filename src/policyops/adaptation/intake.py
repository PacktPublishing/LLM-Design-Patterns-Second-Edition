"""Record intake and dataset manifest helpers for Chapter 3."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from policyops.adaptation.schemas import DataRecord, DatasetManifest
from policyops.util import canonical_json

RIGHTS_ALLOWLIST = {"internal-licensed", "synthetic-lab", "public-demo"}
SECRET_RE = re.compile(r"SECRET_[A-Z0-9_]+|sk-[A-Za-z0-9_-]{8,}", re.I)
POTENTIAL_PII_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


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
