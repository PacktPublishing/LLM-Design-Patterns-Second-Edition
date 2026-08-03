"""Contamination checks for protected evaluation data."""

from __future__ import annotations

from typing import Any

from policyops.adaptation.intake import content_hash, normalize_text
from policyops.adaptation.schemas import DataRecord


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
