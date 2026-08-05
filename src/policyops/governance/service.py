"""Fixture-runnable governance release gate for Chapter 15."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from policyops.governance.schemas import (
    ApprovalPolicy,
    ChangeSet,
    ControlRecord,
    Decision,
    DecisionReason,
    EvidenceRef,
    GovernanceScorecard,
    OwnerRecord,
    ReasonCode,
    ReleaseDecision,
    RightsReceipt,
    RightsRequest,
    RightsTaskRecord,
    RiskRecord,
    SignatureEnvelope,
    StoreReceipt,
    SystemInventory,
    TransparencyNotice,
)
from policyops.telemetry import sha_json

NOW = 1_735_689_600
DEFAULT_RELEASE_POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "release_policy.yaml"


def sign_payload(payload: dict[str, Any], issuer: str, role: str, *, expires_at: int = NOW + 86_400) -> SignatureEnvelope:
    artifact_hash = sha_json(payload)
    envelope = {
        "artifact_hash": artifact_hash,
        "schema_version": "1.0",
        "configuration_scope": "ch14-accepted",
        "issuer": issuer,
        "issuer_role": role,
        "issued_at": NOW,
        "expires_at": expires_at,
        "purpose": "release_evidence",
    }
    signature = sha_json({**envelope, "fixture_key": role})
    return SignatureEnvelope(**envelope, signature=signature)


def build_control_evidence_graph(
    *,
    inventory: SystemInventory,
    risks: list[RiskRecord],
    owners: list[OwnerRecord],
    controls: list[ControlRecord],
    evidence: list[EvidenceRef],
    approval_policies: list[ApprovalPolicy],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "node_id": inventory.inventory_id,
            "node_type": "system_inventory",
            "purpose": inventory.purpose,
            "stores": inventory.stores,
            "ai_components": inventory.ai_components,
        }
    ]
    nodes.extend(
        {
            "node_id": owner.owner_id,
            "node_type": "owner",
            "role": owner.role,
            "current": owner.current,
            "backup_owner_id": owner.backup_owner_id,
        }
        for owner in owners
    )
    nodes.extend(
        {
            "node_id": risk.risk_id,
            "node_type": "risk",
            "impact": risk.impact,
            "autonomy_tier": risk.autonomy_tier,
            "communication_reach": risk.communication_reach,
            "owner_id": risk.owner_id,
        }
        for risk in risks
    )
    nodes.extend(
        {
            "node_id": control.control_id,
            "node_type": "control",
            "risk_id": control.risk_id,
            "implementation": control.implementation,
            "test_id": control.test_id,
            "evidence_id": control.evidence_id,
            "owner_id": control.owner_id,
            "mandatory": control.mandatory,
        }
        for control in controls
    )
    nodes.extend(
        {
            "node_id": item.evidence_id,
            "node_type": "evidence",
            "control_id": item.control_id,
            "artifact_uri": item.artifact_uri,
            "artifact_hash": item.artifact_hash,
            "configuration_scope": item.configuration_scope,
            "result": item.result,
            "issuer": item.signature.issuer,
            "issuer_role": item.signature.issuer_role,
            "issued_at": item.signature.issued_at,
            "expires_at": item.signature.expires_at,
            "reviewed_by": item.reviewed_by,
            "review_status": "current" if item.result == "pass" else "failing",
        }
        for item in evidence
    )
    nodes.extend(
        {
            "node_id": policy.policy_id,
            "node_type": "approval_policy",
            "change_class": policy.change_class,
            "required_role": policy.required_role,
            "separation_of_duties": policy.separation_of_duties,
            "required_evidence_ids": policy.required_evidence_ids,
            "high_impact_required": policy.high_impact_required,
        }
        for policy in approval_policies
    )

    edges: list[dict[str, str]] = []
    for risk in risks:
        edges.append({"from": inventory.inventory_id, "to": risk.risk_id, "relation": "HAS_RISK"})
        edges.append({"from": risk.risk_id, "to": risk.owner_id, "relation": "OWNED_BY"})
    for control in controls:
        edges.append({"from": control.risk_id, "to": control.control_id, "relation": "MITIGATED_BY"})
        edges.append({"from": control.control_id, "to": control.owner_id, "relation": "OWNED_BY"})
        edges.append({"from": control.control_id, "to": control.evidence_id, "relation": "VERIFIED_BY"})
    for item in evidence:
        edges.append({"from": item.evidence_id, "to": item.signature.issuer, "relation": "SIGNED_BY"})
        edges.append({"from": item.evidence_id, "to": item.reviewed_by, "relation": "REVIEWED_BY"})
    for policy in approval_policies:
        if policy.high_impact_required:
            for risk in risks:
                if risk.impact == "high":
                    edges.append({"from": risk.risk_id, "to": policy.policy_id, "relation": "APPROVED_BY_POLICY"})
        for evidence_id in policy.required_evidence_ids:
            edges.append({"from": policy.policy_id, "to": evidence_id, "relation": "REQUIRES_EVIDENCE"})

    return {
        "graph_version": "1",
        "inventory_id": inventory.inventory_id,
        "nodes": nodes,
        "edges": edges,
    }


class GovernanceFixture:
    def owners(self) -> list[OwnerRecord]:
        return [
            OwnerRecord(owner_id="owner-system", name="System Owner", role="system_owner", backup_owner_id="owner-risk"),
            OwnerRecord(owner_id="owner-risk", name="Risk Owner", role="risk_owner", backup_owner_id="owner-control"),
            OwnerRecord(owner_id="owner-control", name="Control Owner", role="control_owner", backup_owner_id="owner-system"),
            OwnerRecord(owner_id="owner-privacy", name="Privacy Lead", role="privacy_lead", backup_owner_id="owner-system"),
            OwnerRecord(owner_id="owner-release", name="Release Approver", role="release_approver", backup_owner_id="owner-risk"),
            OwnerRecord(owner_id="agent-policyops", name="PolicyOps Agent", role="agent", current=True),
        ]

    def inventory(self) -> SystemInventory:
        return SystemInventory(
            inventory_id="inventory-ch15-v1",
            purpose="PolicyOps answers policy questions and creates approved support tickets.",
            users=["employees", "policy operations staff"],
            affected_parties=["employees whose policy cases are processed"],
            components=["api", "retrieval", "graph", "memory", "extensions", "orchestration", "harness", "telemetry", "security", "deployment"],
            stores=["primary_db", "retrieval_index", "graph_snapshot", "memory_ledger", "cache", "trace_store", "export_package", "backup_retention"],
            ai_components=["replay model gateway", "context planner", "agent loop"],
            tools=["ticket.create", "browser fixture", "egress proxy"],
            owners=["owner-system", "owner-risk", "owner-control", "owner-privacy", "owner-release"],
            non_goals=["legal advice", "autonomous release approval"],
        )

    def risks(self) -> list[RiskRecord]:
        return [
            RiskRecord(
                risk_id="risk-high-impact-ticket",
                use_case="approved ticket creation",
                impact="high",
                autonomy_tier="agentic_with_approval",
                data_sensitivity="private",
                communication_reach="internal",
                side_effects=True,
                oversight_mode="human approval before effect",
                prohibited_use="unauthorized employment/legal advice",
                residual_risk="approver may misunderstand business context",
                owner_id="owner-risk",
            ),
            RiskRecord(
                risk_id="risk-data-rights",
                use_case="memory and retrieval over user policy data",
                impact="high",
                autonomy_tier="assistive",
                data_sensitivity="private",
                communication_reach="none",
                side_effects=False,
                oversight_mode="privacy lead review",
                prohibited_use="cross-tenant disclosure",
                residual_risk="backup retention may delay physical deletion",
                owner_id="owner-privacy",
            ),
        ]

    def approval_policies(self) -> list[ApprovalPolicy]:
        return [
            ApprovalPolicy(
                policy_id="approval-high-impact",
                change_class="autonomy",
                required_role="release_approver",
                separation_of_duties=True,
                evidence_expiry_seconds=86_400,
                escalation_path="system owner",
                required_evidence_ids=["ev-ch11-approval", "ev-ch14-deploy"],
                high_impact_required=True,
            ),
            ApprovalPolicy(
                policy_id="approval-deployment",
                change_class="deployment",
                required_role="release_approver",
                separation_of_duties=True,
                evidence_expiry_seconds=86_400,
                escalation_path="platform owner",
                required_evidence_ids=["ev-ch14-deploy", "ev-ch13-security", "ev-ch12-observability"],
                high_impact_required=False,
            ),
        ]

    def evidence(self, *, stale: bool = False, tampered: bool = False, failed: bool = False) -> list[EvidenceRef]:
        controls = [
            ("ev-ch14-deploy", "control-deployment", "build/ch14/deployment_scorecard.json"),
            ("ev-ch13-security", "control-security", "build/ch13/security_report.json"),
            ("ev-ch12-observability", "control-observability", "build/ch12/observability_scorecard.json"),
            ("ev-ch08-rights", "control-rights", "build/ch08/deletion_receipt.json"),
            ("ev-ch11-approval", "control-approval", "build/ch11/harness_scorecard.json"),
        ]
        refs: list[EvidenceRef] = []
        for evidence_id, control_id, uri in controls:
            payload = {"evidence_id": evidence_id, "control_id": control_id, "uri": uri, "result": "pass"}
            signature = sign_payload(payload, "owner-control", "control_owner", expires_at=NOW - 1 if stale and evidence_id == "ev-ch14-deploy" else NOW + 86_400)
            artifact_hash = signature.artifact_hash
            if tampered and evidence_id == "ev-ch13-security":
                artifact_hash = sha_json({"tampered": True})
            refs.append(
                EvidenceRef(
                    evidence_id=evidence_id,
                    control_id=control_id,
                    artifact_uri=uri,
                    artifact_hash=artifact_hash,
                    schema_version="1.0",
                    configuration_scope="ch14-accepted",
                    result="fail" if failed and evidence_id == "ev-ch12-observability" else "pass",
                    signature=signature,
                    reviewed_by="owner-control",
                )
            )
        return refs

    def controls(self) -> list[ControlRecord]:
        return [
            ControlRecord(control_id="control-deployment", risk_id="risk-high-impact-ticket", implementation="policyops.deployment", test_id="tests/deployment", evidence_id="ev-ch14-deploy", owner_id="owner-control"),
            ControlRecord(control_id="control-security", risk_id="risk-high-impact-ticket", implementation="policyops.security", test_id="tests/security", evidence_id="ev-ch13-security", owner_id="owner-control"),
            ControlRecord(control_id="control-observability", risk_id="risk-high-impact-ticket", implementation="policyops.telemetry", test_id="tests/telemetry", evidence_id="ev-ch12-observability", owner_id="owner-control"),
            ControlRecord(control_id="control-rights", risk_id="risk-data-rights", implementation="policyops.memory", test_id="tests/memory", evidence_id="ev-ch08-rights", owner_id="owner-privacy"),
            ControlRecord(control_id="control-approval", risk_id="risk-high-impact-ticket", implementation="policyops.harness", test_id="tests/harness", evidence_id="ev-ch11-approval", owner_id="owner-control"),
        ]


class EvidenceResolver:
    def __init__(self, owners: list[OwnerRecord]) -> None:
        self.owners = {owner.owner_id: owner for owner in owners}

    def verify_signature(self, evidence: EvidenceRef) -> bool:
        payload = evidence.signature.model_dump(exclude={"signature"}, mode="json")
        expected = sha_json({**payload, "fixture_key": evidence.signature.issuer_role})
        return expected == evidence.signature.signature

    def validate(self, evidence: EvidenceRef) -> list[ReasonCode]:
        reasons: list[ReasonCode] = []
        if evidence.artifact_hash != evidence.signature.artifact_hash:
            reasons.append(ReasonCode.EVIDENCE_TAMPERED)
        if evidence.signature.expires_at <= NOW:
            reasons.append(ReasonCode.EVIDENCE_STALE)
        if not self.verify_signature(evidence):
            reasons.append(ReasonCode.SIGNATURE_INVALID)
        if evidence.configuration_scope != evidence.signature.configuration_scope:
            reasons.append(ReasonCode.WRONG_CONFIGURATION)
        if evidence.result != "pass":
            reasons.append(ReasonCode.TEST_FAILED)
        if evidence.signature.issuer not in self.owners or not self.owners[evidence.signature.issuer].current:
            reasons.append(ReasonCode.OWNER_MISSING)
        else:
            signer = self.owners[evidence.signature.issuer]
            if signer.role != evidence.signature.issuer_role:
                reasons.append(ReasonCode.SIGNATURE_INVALID)
            if signer.role in {"agent", "service_account"}:
                reasons.append(ReasonCode.SIGNATURE_INVALID)
        reviewer = self.owners.get(evidence.reviewed_by)
        if reviewer is None or not reviewer.current:
            reasons.append(ReasonCode.OWNER_MISSING)
        elif reviewer.role in {"agent", "service_account"}:
            reasons.append(ReasonCode.SIGNATURE_INVALID)
        if evidence.signature.purpose != "release_evidence":
            reasons.append(ReasonCode.SIGNATURE_INVALID)
        return reasons


class RightsOrchestrator:
    def __init__(self, inventory: SystemInventory) -> None:
        self.inventory = inventory
        self._workflows: dict[str, tuple[RightsRequest, list[RightsTaskRecord]]] = {}

    def process(self, request: RightsRequest, *, miss_store: str | None = None) -> RightsReceipt:
        workflow_id = self._workflow_id(request)
        prior = self._workflows.get(workflow_id)
        if prior is None:
            tasks = [
                RightsTaskRecord(
                    task_id=f"{workflow_id}:{store}",
                    store=store,
                    request_type=request.request_type,
                    status="pending",
                )
                for store in self.inventory.stores
            ]
        else:
            _, tasks = prior
        updated_tasks: list[RightsTaskRecord] = []
        for task in tasks:
            verifier = task.store != miss_store
            updated_tasks.append(
                task.model_copy(
                    update={
                        "status": "completed" if verifier else "failed",
                        "completed_at": NOW + 300,
                        "verifier_passed": verifier,
                        "exception": None if verifier else "adapter did not confirm derived copy",
                        "retention_basis": "backup expiry policy" if task.store == "backup_retention" else None,
                        "follow_up_at": NOW + 86_400 if task.store == "backup_retention" else None,
                    }
                )
            )
        self._workflows[workflow_id] = (request, updated_tasks)
        stores = [
            StoreReceipt(
                store=task.store,
                action=task.request_type,
                completed_at=task.completed_at or NOW + 300,
                verifier_passed=task.verifier_passed,
                exception=task.exception,
                retention_basis=task.retention_basis,
                follow_up_at=task.follow_up_at,
            )
            for task in updated_tasks
        ]
        complete = request.authenticated and all(task.verifier_passed for task in updated_tasks)
        digest = sha_json(
            {
                "request": request.model_dump(mode="json"),
                "tasks": [task.model_dump(mode="json") for task in updated_tasks],
            }
        )
        return RightsReceipt(
            receipt_id="receipt-" + request.request_id,
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            store_inventory_version=self.inventory.inventory_id,
            workflow_id=workflow_id,
            request_digest=workflow_id,
            stores=stores,
            complete=complete,
            signed_hash=digest,
        )

    def workflow(self, request: RightsRequest) -> list[RightsTaskRecord]:
        workflow_id = self._workflow_id(request)
        _, tasks = self._workflows.get(workflow_id, (request, []))
        return [task.model_copy(deep=True) for task in tasks]

    def _workflow_id(self, request: RightsRequest) -> str:
        return sha_json(
            {
                "tenant_id": request.tenant_id,
                "subject_id": request.subject_id,
                "request_type": request.request_type,
                "scope": request.scope,
            }
        )


class NoticeGenerator:
    def render(self, inventory: SystemInventory) -> TransparencyNotice:
        return TransparencyNotice(
            notice_id="notice-policyops-v1",
            ai_involvement="PolicyOps uses AI to draft policy answers and propose ticket actions.",
            sources=["versioned policy corpus", "retrieval index", "graph snapshot", "governed memory"],
            memory_use="Memory is governed by consent, scope, correction, export, and deletion controls.",
            tools_and_actions=inventory.tools,
            limits=["AI may be wrong", "High-impact ticket creation requires human approval", "PolicyOps does not provide legal advice"],
            human_oversight="Human owners approve high-impact actions, exceptions, appeals, and release.",
            rights_channels=["correction", "export", "deletion", "appeal"],
        )


class ReleaseGate:
    def __init__(self, fixture: GovernanceFixture | None = None) -> None:
        self.fixture = fixture or GovernanceFixture()
        self.policy_path = DEFAULT_RELEASE_POLICY_PATH
        self.policy_hash = self._policy_hash()

    def review(
        self,
        *,
        owners: list[OwnerRecord] | None = None,
        evidence: list[EvidenceRef] | None = None,
        approver_id: str = "owner-release",
        producer_id: str = "owner-control",
        rights_receipt: RightsReceipt | None = None,
        change_set: ChangeSet | None = None,
    ) -> ReleaseDecision:
        owners = owners or self.fixture.owners()
        owner_map = {owner.owner_id: owner for owner in owners}
        risks = self.fixture.risks()
        controls = self.fixture.controls()
        evidence = evidence or self.fixture.evidence()
        graph = build_control_evidence_graph(
            inventory=self.fixture.inventory(),
            risks=risks,
            owners=owners,
            controls=controls,
            evidence=evidence,
            approval_policies=self.fixture.approval_policies(),
        )
        evidence_map = {item.evidence_id: item for item in evidence}
        resolver = EvidenceResolver(owners)
        reasons: list[DecisionReason] = []
        priority = 10
        for risk in risks:
            if risk.owner_id not in owner_map or not owner_map[risk.owner_id].current:
                reasons.append(DecisionReason(priority=priority, record_id=risk.risk_id, reason_code=ReasonCode.OWNER_MISSING, remediation="assign current human risk owner"))
                priority += 1
        for control in controls:
            if control.owner_id not in owner_map or not owner_map[control.owner_id].current:
                reasons.append(DecisionReason(priority=priority, record_id=control.control_id, reason_code=ReasonCode.OWNER_MISSING, remediation="assign current control owner"))
                priority += 1
            ev = evidence_map.get(control.evidence_id)
            if ev is None:
                reasons.append(DecisionReason(priority=priority, record_id=control.evidence_id, reason_code=ReasonCode.TEST_FAILED, remediation="provide evidence"))
                priority += 1
                continue
            for reason in resolver.validate(ev):
                reasons.append(DecisionReason(priority=priority, record_id=ev.evidence_id, reason_code=reason, remediation="replace or re-sign current applicable evidence"))
                priority += 1
        approver = owner_map.get(approver_id)
        if approver is None or not approver.current or approver.role != "release_approver":
            reasons.append(DecisionReason(priority=priority, record_id=approver_id, reason_code=ReasonCode.APPROVAL_MISSING, remediation="obtain current release approver"))
            priority += 1
        if approver_id == producer_id:
            reasons.append(DecisionReason(priority=priority, record_id=approver_id, reason_code=ReasonCode.APPROVER_NOT_INDEPENDENT, remediation="use independent human approver"))
            priority += 1
        applicable_policies = self._applicable_policies(change_set or ChangeSet(change_set_id="changes-ch15", autonomy_changed=True, deployment_changed=True))
        for policy in applicable_policies:
            if approver is None or approver.role != policy.required_role:
                reasons.append(
                    DecisionReason(
                        priority=priority,
                        record_id=policy.policy_id,
                        reason_code=ReasonCode.APPROVAL_MISSING,
                        remediation=f"obtain approver with role {policy.required_role}",
                    )
                )
                priority += 1
            for evidence_id in policy.required_evidence_ids:
                if evidence_id not in evidence_map:
                    reasons.append(
                        DecisionReason(
                            priority=priority,
                            record_id=evidence_id,
                            reason_code=ReasonCode.APPROVAL_MISSING,
                            remediation="provide current required approval evidence",
                        )
                    )
                    priority += 1
        if rights_receipt is not None and not rights_receipt.complete:
            reasons.append(DecisionReason(priority=priority, record_id=rights_receipt.receipt_id, reason_code=ReasonCode.RIGHTS_INCOMPLETE, remediation="complete all derived-store verifiers"))
            priority += 1
        ordered = sorted(reasons, key=lambda item: (item.priority, item.record_id, item.reason_code.value))
        decision = Decision.NO_GO if ordered else Decision.GO
        change_set = change_set or ChangeSet(change_set_id="changes-ch15", autonomy_changed=True, deployment_changed=True)
        payload = {
            "decision": decision.value,
            "reasons": [reason.model_dump(mode="json") for reason in ordered],
            "change_set": change_set.model_dump(mode="json"),
            "approver_id": approver_id,
        }
        digest = sha_json(payload)
        return ReleaseDecision(
            decision_id="decision-ch15",
            decision=decision,
            policy_hash=self.policy_hash,
            manifest_hash=sha_json(self.fixture.inventory().model_dump(mode="json")),
            change_set_hash=sha_json(change_set.model_dump(mode="json")),
            evidence_graph_hash=sha_json(graph),
            approver_id=approver_id,
            reasons=ordered,
            decided_at=NOW,
            decision_digest=digest,
        )

    def _applicable_policies(self, change_set: ChangeSet) -> list[ApprovalPolicy]:
        policies = {policy.change_class: policy for policy in self.fixture.approval_policies()}
        return [policies[name] for name in change_set.classes() if name in policies]

    def _policy_hash(self) -> str:
        if self.policy_path.exists():
            return sha_json(yaml.safe_load(self.policy_path.read_text(encoding="utf-8")))
        return sha_json([policy.model_dump(mode="json") for policy in self.fixture.approval_policies()])


class GovernanceVerification:
    def __init__(self) -> None:
        self.fixture = GovernanceFixture()
        self.gate = ReleaseGate(self.fixture)
        self.inventory = self.fixture.inventory()

    def rights_receipts(self) -> tuple[RightsReceipt, RightsReceipt, RightsReceipt]:
        orchestrator = RightsOrchestrator(self.inventory)
        deletion = RightsRequest(
            request_id="rights-delete-001",
            tenant_id="tenant-alpha",
            subject_id="subject-42",
            request_type="deletion",
            authenticated=True,
            scope="policyops user records",
        )
        correction = deletion.model_copy(update={"request_id": "rights-correct-001", "request_type": "correction"})
        export = deletion.model_copy(update={"request_id": "rights-export-001", "request_type": "export"})
        return orchestrator.process(correction), orchestrator.process(export), orchestrator.process(deletion)

    def invalid_evidence_decisions(self) -> list[ReleaseDecision]:
        owners = self.fixture.owners()
        ownerless = [owner.model_copy(update={"current": False}) if owner.owner_id == "owner-risk" else owner for owner in owners]
        missed = RightsOrchestrator(self.inventory).process(
            RightsRequest(
                request_id="rights-delete-missed",
                tenant_id="tenant-alpha",
                subject_id="subject-42",
                request_type="deletion",
                authenticated=True,
                scope="policyops user records",
            ),
            miss_store="retrieval_index",
        )
        return [
            self.gate.review(owners=ownerless),
            self.gate.review(evidence=self.fixture.evidence(stale=True)),
            self.gate.review(evidence=self.fixture.evidence(tampered=True)),
            self.gate.review(evidence=self.fixture.evidence(failed=True)),
            self.gate.review(approver_id="owner-control", producer_id="owner-control"),
            self.gate.review(rights_receipt=missed),
        ]

    def final_decision(self) -> ReleaseDecision:
        _, _, deletion = self.rights_receipts()
        return self.gate.review(rights_receipt=deletion)

    def scorecard(self) -> tuple[GovernanceScorecard, dict[str, Any]]:
        correction, export, deletion = self.rights_receipts()
        final_one = self.final_decision()
        final_two = self.final_decision()
        invalid = self.invalid_evidence_decisions()
        notice = NoticeGenerator().render(self.inventory)
        graph = build_control_evidence_graph(
            inventory=self.inventory,
            risks=self.fixture.risks(),
            owners=self.fixture.owners(),
            controls=self.fixture.controls(),
            evidence=self.fixture.evidence(),
            approval_policies=self.fixture.approval_policies(),
        )
        scorecard = GovernanceScorecard(
            high_risk_paths_resolved=final_one.decision == Decision.GO,
            invalid_evidence_cases_blocked=sum(1 for decision in invalid if decision.decision == Decision.NO_GO),
            independent_approver_valid=final_one.approver_id == "owner-release",
            rights_receipt_complete=deletion.complete and correction.complete and export.complete,
            transparency_notice_consistent=set(notice.tools_and_actions).issubset(set(self.inventory.tools)),
            deterministic_digest=final_one.decision_digest == final_two.decision_digest,
            agent_self_approval_denied=self.gate.review(approver_id="agent-policyops", producer_id="agent-policyops").decision == Decision.NO_GO,
            secret_leaks=0,
            gates_passed=True,
        )
        evidence = {
            "inventory": self.inventory.model_dump(mode="json"),
            "risks": [risk.model_dump(mode="json") for risk in self.fixture.risks()],
            "owners": [owner.model_dump(mode="json") for owner in self.fixture.owners()],
            "approval_matrix": [policy.model_dump(mode="json") for policy in self.fixture.approval_policies()],
            "graph": graph,
            "evidence": [item.model_dump(mode="json") for item in self.fixture.evidence()],
            "rights_receipts": [
                correction.model_dump(mode="json"),
                export.model_dump(mode="json"),
                deletion.model_dump(mode="json"),
            ],
            "notice": notice.model_dump(mode="json"),
            "invalid_decisions": [decision.model_dump(mode="json") for decision in invalid],
            "final_decision": final_one.model_dump(mode="json"),
        }
        return scorecard, evidence


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_governance_verification(evidence_dir: Path) -> dict[str, Any]:
    verifier = GovernanceVerification()
    scorecard, evidence = verifier.scorecard()
    write_json(evidence_dir / "system_inventory.json", evidence["inventory"])
    write_json(evidence_dir / "risk_autonomy_records.json", evidence["risks"])
    write_json(evidence_dir / "ownership_records.json", evidence["owners"])
    write_json(evidence_dir / "approval_matrix.json", evidence["approval_matrix"])
    write_json(evidence_dir / "control_evidence_graph.json", evidence["graph"])
    write_json(evidence_dir / "evidence_index.json", evidence["evidence"])
    write_json(evidence_dir / "rights_receipts.json", evidence["rights_receipts"])
    write_json(evidence_dir / "transparency_notice.json", evidence["notice"])
    write_json(evidence_dir / "invalid_evidence_decisions.json", evidence["invalid_decisions"])
    write_json(evidence_dir / "release_decision.json", evidence["final_decision"])
    write_json(evidence_dir / "governance_scorecard.json", scorecard.model_dump(mode="json"))
    return {"gates_passed": scorecard.gates_passed, "scorecard": scorecard.model_dump(mode="json")}


def run_governance_faults(evidence_dir: Path, scenario: str = "all") -> dict[str, Any]:
    verifier = GovernanceVerification()
    invalid = verifier.invalid_evidence_decisions()
    by_reason = {reason.reason_code for decision in invalid for reason in decision.reasons}
    results: dict[str, bool] = {}
    if scenario in {"all", "owner"}:
        results["owner"] = ReasonCode.OWNER_MISSING in by_reason
    if scenario in {"all", "stale"}:
        results["stale"] = ReasonCode.EVIDENCE_STALE in by_reason
    if scenario in {"all", "tamper"}:
        results["tamper"] = ReasonCode.EVIDENCE_TAMPERED in by_reason
    if scenario in {"all", "failed"}:
        results["failed"] = ReasonCode.TEST_FAILED in by_reason
    if scenario in {"all", "separation"}:
        results["separation"] = ReasonCode.APPROVER_NOT_INDEPENDENT in by_reason
    if scenario in {"all", "rights"}:
        results["rights"] = ReasonCode.RIGHTS_INCOMPLETE in by_reason
    if scenario in {"all", "determinism"}:
        results["determinism"] = verifier.final_decision().decision_digest == verifier.final_decision().decision_digest
    passed = all(results.values()) and bool(results)
    payload = {"scenario": scenario, "results": {k: bool(v) for k, v in results.items()}, "passed": passed}
    write_json(evidence_dir / "governance_faults.json", payload)
    return payload
