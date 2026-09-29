"""Artifact admission checks for adaptation candidates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from policyops.adaptation.schemas import ModelArtifact

LICENSE_ALLOWLIST = {"apache-2.0", "mit", "bsd-3-clause"}
SAFE_ARTIFACT_FORMATS = {"fixture-adapter"}
SAFE_LOAD_POLICIES = {"json-safe-load"}


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
