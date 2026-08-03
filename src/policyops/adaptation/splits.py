"""Deterministic split generation for Chapter 3 adaptation experiments."""

from __future__ import annotations

import hashlib

from policyops.adaptation.schemas import DataRecord, SplitManifest
from policyops.adaptation.intake import hash_payload


def deterministic_split(records: list[DataRecord]) -> SplitManifest:
    """Split by stable entity/subgroup hash buckets instead of random row shuffle."""

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
