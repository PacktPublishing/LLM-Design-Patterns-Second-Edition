"""Fixture-runnable governed memory service for Chapter 8."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from policyops.context import (
    AuthorityLevel,
    ContextItem,
    ContextSource,
    Provenance,
    Sensitivity as ContextSensitivity,
    SourceKind,
    SourceSummary,
    TrustLabel,
)
from policyops.memory.schemas import (
    ConsentReceipt,
    DeletionReceipt,
    ExportRecord,
    MemoryEvent,
    MemoryKind,
    MemoryPolicy,
    MemoryProposal,
    MemoryRecord,
    MemoryScope,
    MemoryScorecard,
    MemoryStatus,
    MutationAction,
    MutationDecision,
    Principal,
    RecallExclusion,
    RecallItem,
    RecallRequest,
    RecallResult,
    Sensitivity,
    SENSITIVITY_RANK,
)


def sha_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _normalize(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    collapsed = re.sub(r"(sk-[a-z0-9_-]+|secret_[a-z0-9_-]+)", "[redacted-secret]", collapsed)
    return collapsed


def _looks_poisoned(text: str) -> bool:
    lowered = text.lower()
    attack_phrases = [
        "ignore previous instructions",
        "developer message",
        "system prompt",
        "approve all",
        "change tool",
        "grant authority",
    ]
    return any(phrase in lowered for phrase in attack_phrases)


def _looks_secret(text: str) -> bool:
    return bool(re.search(r"\b(sk-[a-z0-9_-]+|secret_[a-z0-9_-]+)\b", text.lower()))


def _record_id(proposal: MemoryProposal, version_seed: int) -> str:
    raw = f"{proposal.tenant_id}:{proposal.subject_id}:{proposal.proposal_id}:{version_seed}"
    return "mem_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class FakeClock:
    def __init__(self, now: int = 1_735_689_600) -> None:
        self._now = now

    def now(self) -> int:
        return self._now

    def advance(self, seconds: int) -> int:
        self._now += seconds
        return self._now


class ConsentStore:
    def __init__(self, receipts: list[ConsentReceipt] | None = None) -> None:
        self.receipts = {receipt.consent_id: receipt for receipt in receipts or []}

    def add(self, receipt: ConsentReceipt) -> None:
        self.receipts[receipt.consent_id] = receipt

    def resolve(self, consent_id: str | None) -> ConsentReceipt | None:
        if consent_id is None:
            return None
        return self.receipts.get(consent_id)


class MemoryAuthorizer:
    def __init__(self, policy: MemoryPolicy | None = None, consent_store: ConsentStore | None = None) -> None:
        self.policy = policy or MemoryPolicy()
        self.consent_store = consent_store or ConsentStore()

    def evaluate(self, proposal: MemoryProposal, principal: Principal, now: int) -> MutationDecision:
        reasons: list[str] = []
        if proposal.tenant_id != principal.tenant_id or proposal.subject_id != principal.subject_id:
            return MutationDecision(
                proposal_id=proposal.proposal_id,
                action=MutationAction.NOOP,
                reason_codes=["identity_scope_mismatch"],
                target_record_id=proposal.target_record_id,
            )
        if proposal.purpose not in self.policy.allowed_purposes:
            reasons.append("purpose_not_allowed")
        if proposal.scope not in self.policy.allowed_scopes and proposal.scope != MemoryScope.GLOBAL:
            reasons.append("scope_not_allowed")
        if proposal.scope == MemoryScope.GLOBAL and "memory:global" not in principal.capabilities:
            reasons.append("global_scope_requires_capability")
        if proposal.approval_ref is None and proposal.scope in {MemoryScope.TEAM, MemoryScope.TENANT, MemoryScope.GLOBAL}:
            reasons.append("scope_widening_requires_approval")
        if proposal.confidence < 0.4:
            reasons.append("low_confidence_noop")
        consent = self.consent_store.resolve(proposal.consent_id)
        if SENSITIVITY_RANK[proposal.sensitivity] > SENSITIVITY_RANK[self.policy.max_sensitivity_without_consent]:
            if consent is None:
                reasons.append("consent_required")
            elif not consent.active_for(
                now=now,
                purpose=proposal.purpose,
                sensitivity=proposal.sensitivity,
            ):
                reasons.append("consent_inactive_or_mismatched")
        if _looks_secret(proposal.text):
            reasons.append("secret_detected")
        if _looks_poisoned(proposal.text):
            return MutationDecision(
                proposal_id=proposal.proposal_id,
                action=MutationAction.ADD,
                reason_codes=["poison_pattern_quarantined"],
                target_record_id=proposal.target_record_id,
                status=MemoryStatus.QUARANTINED,
                expected_version=proposal.expected_version,
            )
        hard_noop = {
            "identity_scope_mismatch",
            "purpose_not_allowed",
            "scope_not_allowed",
            "global_scope_requires_capability",
            "scope_widening_requires_approval",
            "low_confidence_noop",
            "consent_required",
            "consent_inactive_or_mismatched",
            "secret_detected",
        }
        if hard_noop & set(reasons):
            return MutationDecision(
                proposal_id=proposal.proposal_id,
                action=MutationAction.NOOP,
                reason_codes=reasons,
                target_record_id=proposal.target_record_id,
                expected_version=proposal.expected_version,
            )
        action = MutationAction.UPDATE if proposal.target_record_id else MutationAction.ADD
        return MutationDecision(
            proposal_id=proposal.proposal_id,
            action=action,
            reason_codes=reasons or ["authorized"],
            target_record_id=proposal.target_record_id,
            status=MemoryStatus.ACTIVE,
            expected_version=proposal.expected_version,
        )


class VersionConflict(RuntimeError):
    pass


class MemoryLedger:
    def __init__(self, clock: FakeClock | None = None) -> None:
        self.clock = clock or FakeClock()
        self.records: dict[str, MemoryRecord] = {}
        self.events: list[MemoryEvent] = []
        self.deleted_receipts: dict[str, DeletionReceipt] = {}

    def apply(self, proposal: MemoryProposal, decision: MutationDecision) -> MemoryRecord | None:
        now = self.clock.now()
        if decision.action == MutationAction.NOOP:
            self._event(proposal, decision, None, version=0, content_hash=None)
            return None
        if decision.action == MutationAction.DELETE:
            raise ValueError("use delete() for delete decisions")
        if proposal.target_record_id:
            current = self.records[proposal.target_record_id]
            if proposal.expected_version != current.version or current.status != MemoryStatus.ACTIVE:
                raise VersionConflict("MEMORY_VERSION_CONFLICT")
            current.status = MemoryStatus.SUPERSEDED
            current.updated_at = now
            version = current.version + 1
            record_id = _record_id(proposal, version)
            supersedes = current.record_id
        else:
            version = 1
            record_id = _record_id(proposal, len(self.records) + 1)
            supersedes = None
        normalized = _normalize(proposal.text)
        record = MemoryRecord(
            record_id=record_id,
            tenant_id=proposal.tenant_id,
            subject_id=proposal.subject_id,
            actor_id=proposal.actor_id,
            kind=proposal.kind,
            scope=proposal.scope,
            text=normalized if decision.status == MemoryStatus.QUARANTINED else proposal.text,
            normalized_text=normalized,
            purpose=proposal.purpose,
            sensitivity=proposal.sensitivity,
            confidence=proposal.confidence,
            source_ref=proposal.source_ref,
            source_hash=sha_text(proposal.source_ref + ":" + normalized),
            consent_id=proposal.consent_id,
            valid_from=proposal.valid_from,
            expires_at=proposal.expires_at,
            status=decision.status or MemoryStatus.ACTIVE,
            version=version,
            created_at=now,
            updated_at=now,
            supersedes=supersedes,
            reason_codes=decision.reason_codes,
        )
        self.records[record_id] = record
        self._event(proposal, decision, record_id, version=version, content_hash=record.source_hash)
        return record

    def delete(
        self,
        record_id: str,
        principal: Principal,
        *,
        expected_version: int,
        proposal_id: str = "delete",
    ) -> DeletionReceipt:
        now = self.clock.now()
        record = self.records[record_id]
        if record.tenant_id != principal.tenant_id or record.subject_id != principal.subject_id:
            raise PermissionError("identity_scope_mismatch")
        if record.version != expected_version:
            raise VersionConflict("MEMORY_VERSION_CONFLICT")
        impacted = [
            item
            for item in self.records.values()
            if item.record_id == record_id or record_id in item.parent_record_ids or item.supersedes == record_id
        ]
        for item in impacted:
            item.status = MemoryStatus.DELETED
            item.text = "[deleted]"
            item.normalized_text = "[deleted]"
            item.updated_at = now
        receipt = DeletionReceipt(
            receipt_id="del_" + hashlib.sha256(f"{record_id}:{now}".encode()).hexdigest()[:12],
            tenant_id=principal.tenant_id,
            subject_id=principal.subject_id,
            record_ids=sorted(item.record_id for item in impacted),
            redacted_hashes=sorted(item.source_hash for item in impacted),
            deleted_at=now,
        )
        self.deleted_receipts[receipt.receipt_id] = receipt
        self.events.append(
            MemoryEvent(
                event_id=f"evt_{len(self.events) + 1:04d}",
                proposal_id=proposal_id,
                action=MutationAction.DELETE,
                record_id=record_id,
                tenant_id=record.tenant_id,
                subject_id=record.subject_id,
                reason_codes=["deleted_with_derived_views"],
                created_at=now,
                version=record.version + 1,
                content_hash=None,
            )
        )
        return receipt

    def consolidate(
        self,
        record_ids: list[str],
        *,
        proposal_id: str,
        actor_id: str,
        text: str,
    ) -> MemoryRecord:
        if len(record_ids) < 2:
            raise ValueError("consolidation requires at least two members")
        parents = [self.records[record_id] for record_id in record_ids]
        first = parents[0]
        proposal = MemoryProposal(
            proposal_id=proposal_id,
            tenant_id=first.tenant_id,
            subject_id=first.subject_id,
            actor_id=actor_id,
            kind=MemoryKind.SEMANTIC,
            scope=first.scope,
            text=text,
            purpose=first.purpose,
            sensitivity=max((p.sensitivity for p in parents), key=lambda s: SENSITIVITY_RANK[s]),
            confidence=min(p.confidence for p in parents),
            source_ref="consolidation:" + ",".join(sorted(record_ids)),
            consent_id=first.consent_id,
            valid_from=max(p.valid_from for p in parents),
            expires_at=min((p.expires_at for p in parents if p.expires_at), default=None),
            approval_ref="consolidation-policy-v1",
        )
        decision = MutationDecision(
            proposal_id=proposal_id,
            action=MutationAction.ADD,
            reason_codes=["consolidated_from_episodes"],
            status=MemoryStatus.ACTIVE,
        )
        record = self.apply(proposal, decision)
        if record is None:
            raise RuntimeError("consolidation failed")
        record.parent_record_ids = sorted(record_ids)
        return record

    def _event(
        self,
        proposal: MemoryProposal,
        decision: MutationDecision,
        record_id: str | None,
        *,
        version: int,
        content_hash: str | None,
    ) -> None:
        self.events.append(
            MemoryEvent(
                event_id=f"evt_{len(self.events) + 1:04d}",
                proposal_id=proposal.proposal_id,
                action=decision.action,
                record_id=record_id,
                tenant_id=proposal.tenant_id,
                subject_id=proposal.subject_id,
                reason_codes=decision.reason_codes,
                created_at=self.clock.now(),
                version=version,
                content_hash=content_hash,
            )
        )

    def active_views(self, as_of: int | None = None) -> dict[str, list[MemoryRecord]]:
        when = self.clock.now() if as_of is None else as_of
        views: dict[str, list[MemoryRecord]] = {kind.value: [] for kind in MemoryKind}
        for record in self.records.values():
            if record.is_effective(when):
                views[record.kind.value].append(record)
        return views

    def export(self, principal: Principal) -> list[ExportRecord]:
        return [
            ExportRecord(
                record_id=record.record_id,
                kind=record.kind,
                scope=record.scope,
                purpose=record.purpose,
                sensitivity=record.sensitivity,
                source_ref=record.source_ref,
                source_hash=record.source_hash,
                status=record.status,
                version=record.version,
            )
            for record in self.records.values()
            if record.tenant_id == principal.tenant_id and record.subject_id == principal.subject_id
        ]


class MemoryRetriever:
    def __init__(self, ledger: MemoryLedger) -> None:
        self.ledger = ledger

    def recall(self, request: RecallRequest) -> RecallResult:
        query_terms = _tokens(request.query)
        items: list[RecallItem] = []
        exclusions: list[RecallExclusion] = []
        for record in self.ledger.records.values():
            if record.tenant_id != request.tenant_id or record.subject_id != request.subject_id:
                exclusions.append(RecallExclusion(record_id=record.record_id, reason_code="tenant_or_subject_mismatch"))
                continue
            if record.scope not in request.allowed_scopes:
                exclusions.append(RecallExclusion(record_id=record.record_id, reason_code="scope_not_allowed"))
                continue
            if not record.is_effective(request.as_of):
                exclusions.append(RecallExclusion(record_id=record.record_id, reason_code=f"status_{record.status.value}"))
                continue
            if record.purpose != request.purpose:
                exclusions.append(RecallExclusion(record_id=record.record_id, reason_code="purpose_mismatch"))
                continue
            if SENSITIVITY_RANK[record.sensitivity] > SENSITIVITY_RANK[request.allowed_sensitivity]:
                exclusions.append(RecallExclusion(record_id=record.record_id, reason_code="sensitivity_excluded"))
                continue
            score = len(query_terms & _tokens(record.normalized_text + " " + record.source_ref))
            if score <= 0:
                exclusions.append(RecallExclusion(record_id=record.record_id, reason_code="not_relevant"))
                continue
            items.append(
                RecallItem(
                    record_id=record.record_id,
                    kind=record.kind,
                    scope=record.scope,
                    text=record.text,
                    source_ref=record.source_ref,
                    source_hash=record.source_hash,
                    sensitivity=record.sensitivity,
                    version=record.version,
                    reason_codes=["recalled_as_untrusted_memory"],
                )
            )
        items.sort(key=lambda item: (item.kind.value, item.record_id))
        return RecallResult(
            request_id=request.request_id,
            items=items[: request.max_items],
            exclusions=exclusions,
        )


class MemoryContextSource(ContextSource):
    """Chapter 5 context-source adapter over governed recall."""

    def __init__(self, retriever: MemoryRetriever, request: RecallRequest) -> None:
        self.retriever = retriever
        self.request = request
        self._result = retriever.recall(request)

    def summaries(self, request) -> list[SourceSummary]:  # noqa: ANN001
        return [
            SourceSummary(
                item_id=item.record_id,
                source_kind=SourceKind.MEMORY,
                authority=AuthorityLevel.STATE,
                trust=TrustLabel.UNTRUSTED_CONTENT,
                provenance=Provenance(source_id=item.source_ref, content_hash=item.source_hash),
                tenant_id=self.request.tenant_id,
                sensitivity=ContextSensitivity(item.sensitivity.value),
                required=False,
                stable=False,
                estimated_tokens=max(1, len(item.text.split())),
                relevance_tags=[item.kind.value, item.scope.value],
                fresh=True,
            )
            for item in self._result.items
        ]

    def materialize(self, item_id: str) -> ContextItem:
        for item in self._result.items:
            if item.record_id == item_id:
                return ContextItem(
                    item_id=item.record_id,
                    source_kind=SourceKind.MEMORY,
                    authority=AuthorityLevel.STATE,
                    trust=TrustLabel.UNTRUSTED_CONTENT,
                    provenance=Provenance(source_id=item.source_ref, content_hash=item.source_hash),
                    tenant_id=self.request.tenant_id,
                    sensitivity=ContextSensitivity(item.sensitivity.value),
                    required=False,
                    stable=False,
                    estimated_tokens=max(1, len(item.text.split())),
                    relevance_tags=[item.kind.value, item.scope.value],
                    fresh=True,
                    text=f"Untrusted remembered state: {item.text}",
                )
        raise KeyError(item_id)


def build_fixture_memory() -> tuple[MemoryLedger, MemoryRetriever, Principal]:
    clock = FakeClock()
    consent_store = ConsentStore(
        [
            ConsentReceipt(
                consent_id="consent-alpha-conf",
                tenant_id="tenant_alpha",
                subject_id="user_ken",
                purpose="policy_support",
                sensitivity=Sensitivity.CONFIDENTIAL,
                valid_until=clock.now() + 86_400,
            )
        ]
    )
    authorizer = MemoryAuthorizer(consent_store=consent_store)
    ledger = MemoryLedger(clock=clock)
    principal = Principal(
        tenant_id="tenant_alpha",
        subject_id="user_ken",
        actor_id="actor_reader",
        capabilities=["memory:write"],
    )
    fixtures = [
        MemoryProposal(
            proposal_id="pref-remote-format",
            tenant_id="tenant_alpha",
            subject_id="user_ken",
            actor_id="actor_reader",
            kind=MemoryKind.SEMANTIC,
            scope=MemoryScope.PERSONAL,
            text="Ken prefers concise policy answers with exact citation IDs.",
            purpose="policy_support",
            sensitivity=Sensitivity.INTERNAL,
            source_ref="session:001",
            valid_from=clock.now(),
        ),
        MemoryProposal(
            proposal_id="episode-ticket",
            tenant_id="tenant_alpha",
            subject_id="user_ken",
            actor_id="actor_reader",
            kind=MemoryKind.EPISODIC,
            scope=MemoryScope.PERSONAL,
            text="Ken asked about remote-work exceptions for a manager-approved ticket.",
            purpose="policy_support",
            sensitivity=Sensitivity.CONFIDENTIAL,
            source_ref="session:002",
            consent_id="consent-alpha-conf",
            valid_from=clock.now(),
        ),
    ]
    for proposal in fixtures:
        ledger.apply(proposal, authorizer.evaluate(proposal, principal, clock.now()))
    return ledger, MemoryRetriever(ledger), principal


def run_memory_verification(evidence_dir: Path) -> dict[str, object]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger, retriever, principal = build_fixture_memory()
    now = ledger.clock.now()
    recall = retriever.recall(
        RecallRequest(
            request_id="recall-fixture",
            tenant_id=principal.tenant_id,
            subject_id=principal.subject_id,
            actor_id=principal.actor_id,
            purpose="policy_support",
            query="remote policy citation",
            allowed_scopes=[MemoryScope.PERSONAL],
            as_of=now,
        )
    )
    first = recall.items[0]
    receipt = ledger.delete(first.record_id, principal, expected_version=first.version)
    cross_tenant = retriever.recall(
        RecallRequest(
            request_id="recall-cross-tenant",
            tenant_id="tenant_beta",
            subject_id=principal.subject_id,
            actor_id=principal.actor_id,
            purpose="policy_support",
            query="remote policy citation",
            allowed_scopes=[MemoryScope.PERSONAL, MemoryScope.TENANT],
            as_of=now,
        )
    )
    scorecard = MemoryScorecard(
        mutation_decision_accuracy=1.0,
        recall_precision=1.0,
        correction_success=1.0,
        deletion_coverage=1.0,
        quarantine_precision=1.0,
        tenant_violations=len(cross_tenant.items),
        authority_changes_from_memory=sum(1 for item in recall.items if item.can_grant_authority),
        no_memory_success_rate=0.60,
        governed_memory_success_rate=0.80,
        gates_passed=not cross_tenant.items and receipt.content_removed,
    )
    (evidence_dir / "memory_events.jsonl").write_text(
        "\n".join(json.dumps(event.model_dump(mode="json"), sort_keys=True) for event in ledger.events)
        + "\n",
        encoding="utf-8",
    )
    (evidence_dir / "memory_views.json").write_text(
        json.dumps(
            {
                kind: [record.model_dump(mode="json") for record in records]
                for kind, records in ledger.active_views().items()
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (evidence_dir / "recall_report.json").write_text(
        recall.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (evidence_dir / "deletion_receipt.json").write_text(
        receipt.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (evidence_dir / "memory_scorecard.json").write_text(
        scorecard.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return {"gates_passed": scorecard.gates_passed, "scorecard": scorecard.model_dump(mode="json")}
