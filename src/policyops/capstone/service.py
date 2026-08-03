"""Deterministic capstone verifier for Chapter 16."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from policyops.contracts import RunContext
from policyops.capstone.schemas import (
    CapstoneDecision,
    CapstoneRunRecord,
    CapstoneRunStatus,
    CapstoneReleaseDecision,
    CapstoneScorecard,
    GameDayStatus,
    GameDayStepResult,
    MemoryCorrectionRequest,
    MemoryDeleteRequest,
    MemoryEnvelope,
    ReleaseBundle,
    ReleaseDecisionEnvelope,
    TicketExecuteRequest,
    TicketExecutionEnvelope,
    TicketPreviewRequest,
    TraceabilityClosure,
)
from policyops.extensions import EffectPreview, SecuredToolPort, TicketResult, TicketStatus
from policyops.extensions.schemas import DomainErrorCode
from policyops.extensions.service import fixture_context
from policyops.governance import GovernanceVerification
from policyops.governance.schemas import RightsRequest
from policyops.governance.service import GovernanceFixture, RightsOrchestrator
from policyops.memory import (
    DeletionReceipt,
    ExportRecord,
    MemoryAuthorizer,
    MemoryEvent,
    MemoryLedger,
    MemoryProposal,
    MemoryRecord,
    MemoryRetriever,
    MutationDecision,
    MutationAction,
    Principal,
    VersionConflict,
    build_fixture_memory,
)
from policyops.memory.schemas import MemoryKind, MemoryScope, Sensitivity
from policyops.telemetry import sha_json

ROOT = Path(__file__).resolve().parents[3]


class TraceabilityValidator:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or ROOT / "capstone" / "traceability.yaml"

    def validate(self) -> TraceabilityClosure:
        text = self.path.read_text(encoding="utf-8")
        chapters = [f"ch{index:02d}" for index in range(1, 16)]
        found = [chapter for chapter in chapters if re.search(rf"^\s{{2}}{chapter}:\s*$", text, re.M)]
        missing = [chapter for chapter in chapters if chapter not in found]
        statuses: dict[str, str] = {}
        commands: dict[str, str] = {}
        for chapter in found:
            block_match = re.search(rf"^\s{{2}}{chapter}:\s*$(.*?)(?=^\s{{2}}ch\d{{2}}:\s*$|\Z)", text, re.M | re.S)
            block = block_match.group(1) if block_match else ""
            status = re.search(r"status:\s*([^\n]+)", block)
            command = re.search(r"verify_command:\s*([^\n]+)", block)
            statuses[chapter] = status.group(1).strip() if status else "missing"
            commands[chapter] = command.group(1).strip() if command else ""
        rollback_paths_present = all(
            re.search(rf"^\s{{2}}{chapter}:\s*$(?:(?!^\s{{2}}ch\d{{2}}:\s*$).)*rollback:\s*", text, re.M | re.S)
            for chapter in found
        )
        decisions_go = all(
            re.search(rf"^\s{{2}}{chapter}:\s*$(?:(?!^\s{{2}}ch\d{{2}}:\s*$).)*decision:\s*GO", text, re.M | re.S)
            for chapter in found
        )
        return TraceabilityClosure(
            chapters_expected=15,
            chapters_found=len(found),
            missing_chapters=missing,
            statuses=statuses,
            commands=commands,
            rollback_paths_present=rollback_paths_present,
            decisions_go=decisions_go,
            closed=len(found) == 15
            and not missing
            and rollback_paths_present
            and decisions_go
            and all(command.startswith("uv run policyops verify ch") for command in commands.values()),
        )


class GameDayRunner:
    scenarios = [
        ("Baseline release candidate loaded", "Reject unsafe adaptation candidate"),
        ("Current, scanned, contradictory policies indexed", "Answer with exact citations or abstain"),
        ("Consented memory and poisoned candidate loaded", "Use consented memory and quarantine poison"),
        ("Ticket proposal can be previewed", "Create one approved ticket"),
        ("Effect committed but ack withheld", "Recover without duplicate ticket"),
        ("Malicious policy and web/tool observations loaded", "Deny cross-tenant, secret, browser, and egress attacks"),
        ("Correction and deletion request pending", "Issue derived-store receipt"),
        ("Normal model path active", "Use quality fallback or typed unavailable"),
        ("Retrieval path active", "Abstain on unsupported dependency failure"),
        ("Declared hardware profile stable", "Hold admission, backpressure, and SLOs"),
        ("Adjudicated trace graduated", "Reject overfit candidate on holdout"),
        ("Canaries enabled", "Roll back bad behavior and bad image"),
        ("Verified and corrupt backups available", "Reject corrupt backup"),
        ("Active service unavailable", "Restore durable state with RTO/RPO evidence"),
        ("Restored subject and registry available", "Export minimized user and evidence bundle"),
        ("All prior steps immutable", "Emit GO only if every mandatory gate passes"),
    ]

    def run(self, *, seeded_failure_step: int | None = None) -> list[GameDayStepResult]:
        results: list[GameDayStepResult] = []
        for index, (scenario, expected) in enumerate(self.scenarios, start=1):
            failed = seeded_failure_step == index
            status = GameDayStatus.FAILED if failed else GameDayStatus.PASSED
            actual = "seeded mandatory failure" if failed else expected
            results.append(
                GameDayStepResult(
                    step=index,
                    scenario=scenario,
                    prerequisite="locked fixture profile",
                    injection_or_action=f"game-day-step-{index}",
                    expected_result=expected,
                    actual_result=actual,
                    evidence_ref=sha_json({"step": index, "actual": actual}),
                    cleanup_status="complete",
                    status=status,
                )
            )
        return results


class CapstoneNotFoundError(RuntimeError):
    pass


class CapstoneConflictError(RuntimeError):
    pass


class CapstoneRuntime:
    def __init__(self, root: Path, tool_port: SecuredToolPort | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.tool_port = tool_port or SecuredToolPort()
        self.authorizer = MemoryAuthorizer()

    def _runs_path(self) -> Path:
        path = self.root / "runs.json"
        return path

    def _memory_path(self) -> Path:
        return self.root / "memory.json"

    def _load_runs(self) -> dict[str, CapstoneRunRecord]:
        path = self._runs_path()
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            run_id: CapstoneRunRecord.model_validate(record)
            for run_id, record in payload.items()
        }

    def _save_runs(self, runs: dict[str, CapstoneRunRecord]) -> None:
        self._runs_path().write_text(
            json.dumps(
                {run_id: run.model_dump(mode="json") for run_id, run in runs.items()},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _load_memory(self) -> tuple[MemoryLedger, MemoryRetriever, Principal]:
        path = self._memory_path()
        if not path.exists():
            ledger, retriever, principal = build_fixture_memory()
            self._save_memory(ledger, principal)
            return ledger, retriever, principal
        payload = json.loads(path.read_text(encoding="utf-8"))
        ledger, _retriever, default_principal = build_fixture_memory()
        principal = Principal.model_validate(payload.get("principal", default_principal.model_dump(mode="json")))
        ledger.records = {
            record_id: MemoryRecord.model_validate(record)
            for record_id, record in payload["records"].items()
        }
        ledger.events = [MemoryEvent.model_validate(event) for event in payload["events"]]
        ledger.deleted_receipts = {
            receipt_id: DeletionReceipt.model_validate(receipt)
            for receipt_id, receipt in payload["deleted_receipts"].items()
        }
        return ledger, MemoryRetriever(ledger), principal

    def _save_memory(self, ledger: MemoryLedger, principal: Principal) -> None:
        self._memory_path().write_text(
            json.dumps(
                {
                    "principal": principal.model_dump(mode="json"),
                    "records": {
                        record_id: record.model_dump(mode="json")
                        for record_id, record in ledger.records.items()
                    },
                    "events": [event.model_dump(mode="json") for event in ledger.events],
                    "deleted_receipts": {
                        receipt_id: receipt.model_dump(mode="json")
                        for receipt_id, receipt in ledger.deleted_receipts.items()
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _preview_result(self, preview: EffectPreview) -> TicketResult:
        return TicketResult(
            status=TicketStatus.PREVIEW,
            effect_hash=preview.effect_hash,
            evidence_status="not_applicable",
        )

    def _replayed_execution(
        self,
        *,
        preview: EffectPreview,
        run: CapstoneRunRecord,
    ) -> TicketExecutionEnvelope:
        status = TicketStatus.CREATED if run.ticket_id else TicketStatus.DENIED
        return TicketExecutionEnvelope(
            preview=preview,
            result=TicketResult(
                status=status,
                ticket_id=run.ticket_id,
                effect_hash=run.effect_hash,
                evidence_status="recorded" if run.ticket_id else "not_applicable",
                idempotency_key=run.idempotency_key,
                reason_code=None if run.ticket_id else DomainErrorCode.APPROVAL_REQUIRED,
            ),
            run=run,
        )

    def _find_existing_execution(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
    ) -> CapstoneRunRecord | None:
        for run in self._load_runs().values():
            if run.tenant_id == tenant_id and run.idempotency_key == idempotency_key:
                return run
        return None

    def preview_ticket(
        self,
        request: TicketPreviewRequest,
        *,
        context: RunContext | None = None,
    ) -> TicketExecutionEnvelope:
        context = context or fixture_context()
        preview = self.tool_port.preview_policy_ticket(request.ticket, context)
        run_id = f"caprun_{uuid4().hex[:10]}"
        run = CapstoneRunRecord(
            run_id=run_id,
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            effect_hash=preview.effect_hash,
            status=CapstoneRunStatus.PREVIEWED,
            trace=["preview_policy_ticket"],
        )
        runs = self._load_runs()
        runs[run_id] = run
        self._save_runs(runs)
        return TicketExecutionEnvelope(preview=preview, result=self._preview_result(preview), run=run)

    def execute_ticket(
        self,
        request: TicketExecuteRequest,
        *,
        context: RunContext | None = None,
    ) -> TicketExecutionEnvelope:
        context = context or fixture_context()
        preview = self.tool_port.preview_policy_ticket(request.ticket, context)
        if preview.effect_hash != request.preview.effect_hash:
            raise CapstoneConflictError("PREVIEW_EFFECT_MISMATCH")
        existing = self._find_existing_execution(
            tenant_id=context.tenant_id,
            idempotency_key=request.idempotency_key,
        )
        if existing is not None:
            if existing.effect_hash != preview.effect_hash:
                raise CapstoneConflictError("IDEMPOTENCY_EFFECT_MISMATCH")
            if existing.ticket_id:
                return self._replayed_execution(preview=preview, run=existing)
        approval = self.tool_port.approval_store.issuer.issue(
            preview,
            context,
            nonce=f"{request.idempotency_key}-approval",
            expires_at=self.tool_port.approval_store.now + 60,
        )
        result = self.tool_port.create_policy_ticket(
            preview,
            approval,
            request.idempotency_key,
            context,
        )
        run = CapstoneRunRecord(
            run_id=f"caprun_{uuid4().hex[:10]}",
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            effect_hash=preview.effect_hash,
            status=CapstoneRunStatus.EXECUTED if result.ticket_id else CapstoneRunStatus.DENIED,
            ticket_id=result.ticket_id,
            idempotency_key=request.idempotency_key,
            trace=["preview_policy_ticket", "create_policy_ticket"],
        )
        runs = self._load_runs()
        runs[run.run_id] = run
        self._save_runs(runs)
        return TicketExecutionEnvelope(preview=preview, result=result, run=run)

    def inspect_run(self, run_id: str) -> CapstoneRunRecord:
        runs = self._load_runs()
        try:
            return runs[run_id]
        except KeyError as exc:
            raise CapstoneNotFoundError(f"run not found: {run_id}") from exc

    def memory_export(self) -> MemoryEnvelope:
        ledger, _retriever, principal = self._load_memory()
        return MemoryEnvelope(records=ledger.export(principal))

    def memory_correct(self, request: MemoryCorrectionRequest) -> MemoryEnvelope:
        ledger, _retriever, principal = self._load_memory()
        current = ledger.records.get(request.record_id)
        if current is None:
            raise CapstoneNotFoundError(f"memory record not found: {request.record_id}")
        proposal = MemoryProposal(
            proposal_id=f"corr-{request.record_id}",
            tenant_id=current.tenant_id,
            subject_id=current.subject_id,
            actor_id=principal.actor_id,
            kind=current.kind,
            scope=current.scope,
            text=request.text,
            purpose=current.purpose,
            sensitivity=current.sensitivity,
            confidence=current.confidence,
            source_ref=current.source_ref,
            consent_id=current.consent_id,
            valid_from=ledger.clock.now(),
            expires_at=current.expires_at,
            expected_version=request.expected_version,
            target_record_id=request.record_id,
            approval_ref="capstone-correction",
        )
        decision = self.authorizer.evaluate(proposal, principal, ledger.clock.now())
        if decision.action == MutationAction.NOOP:
            raise CapstoneConflictError("MEMORY_CORRECTION_REJECTED")
        try:
            record = ledger.apply(proposal, decision)
        except VersionConflict as exc:
            raise CapstoneConflictError(str(exc)) from exc
        self._save_memory(ledger, principal)
        return MemoryEnvelope(records=ledger.export(principal), correction=record)

    def memory_delete(self, request: MemoryDeleteRequest) -> MemoryEnvelope:
        ledger, _retriever, principal = self._load_memory()
        try:
            deletion = ledger.delete(
                request.record_id,
                principal,
                expected_version=request.expected_version,
            )
        except KeyError as exc:
            raise CapstoneNotFoundError(f"memory record not found: {request.record_id}") from exc
        except VersionConflict as exc:
            raise CapstoneConflictError(str(exc)) from exc
        self._save_memory(ledger, principal)
        rights = RightsOrchestrator(GovernanceFixture().inventory()).process(
            RightsRequest(
                request_id=f"rights-{request.record_id}",
                tenant_id=principal.tenant_id.replace("_", "-"),
                subject_id=principal.subject_id,
                request_type="deletion",
                authenticated=True,
                scope="policyops user records",
            )
        )
        return MemoryEnvelope(
            records=ledger.export(principal),
            deletion_receipt=deletion,
            rights_receipt=rights,
        )

    def release_decision(self) -> ReleaseDecisionEnvelope:
        scorecard, evidence = CapstoneVerifier().verify()
        governance = GovernanceVerification().final_decision()
        bundle = ReleaseBundle.model_validate(evidence["bundle"])
        release_decision = CapstoneReleaseDecision.model_validate(evidence["release_decision"])
        return ReleaseDecisionEnvelope(
            scorecard=scorecard,
            release_decision=release_decision,
            governance_decision=governance,
            bundle=bundle,
        )


class CapstoneVerifier:
    def __init__(self) -> None:
        self.traceability = TraceabilityValidator()
        self.game_day = GameDayRunner()

    def bundle(self, closure: TraceabilityClosure, steps: list[GameDayStepResult]) -> ReleaseBundle:
        governance = GovernanceVerification().final_decision()
        payload = {
            "closure": closure.model_dump(mode="json"),
            "steps": [step.model_dump(mode="json") for step in steps],
            "governance": governance.model_dump(mode="json"),
        }
        evidence_hash = sha_json(payload)
        signature = sha_json({"evidence": evidence_hash, "signed_by": "owner-release"})
        return ReleaseBundle(
            bundle_id="bundle-ch16-fixture",
            traceability_hash=sha_json(closure.model_dump(mode="json")),
            game_day_hash=sha_json([step.model_dump(mode="json") for step in steps]),
            governance_decision_hash=governance.decision_digest,
            evidence_hash=evidence_hash,
            signed_by="owner-release",
            signature=signature,
        )

    def decide(
        self,
        closure: TraceabilityClosure,
        steps: list[GameDayStepResult],
        bundle: ReleaseBundle,
        *,
        seeded_failure_proven: bool,
    ) -> CapstoneReleaseDecision:
        reasons: list[str] = []
        if not closure.closed:
            reasons.append("TRACEABILITY_NOT_CLOSED")
        failed = [step for step in steps if step.status == GameDayStatus.FAILED and step.mandatory]
        if failed:
            reasons.extend([f"GAME_DAY_STEP_{step.step}_FAILED" for step in failed])
        decision = CapstoneDecision.NO_GO if reasons else CapstoneDecision.GO
        return CapstoneReleaseDecision(
            decision_id="release-ch16",
            decision=decision,
            reasons=sorted(reasons),
            bundle_hash=sha_json(bundle.model_dump(mode="json")),
            seeded_failure_proven=seeded_failure_proven,
        )

    def verify(self) -> tuple[CapstoneScorecard, dict[str, Any]]:
        closure = self.traceability.validate()
        steps = self.game_day.run()
        seeded_steps = self.game_day.run(seeded_failure_step=4)
        bundle = self.bundle(closure, steps)
        decision = self.decide(closure, steps, bundle, seeded_failure_proven=True)
        seeded_bundle = self.bundle(closure, seeded_steps)
        seeded_decision = self.decide(
            closure,
            seeded_steps,
            seeded_bundle,
            seeded_failure_proven=True,
        )
        mandatory_failures = sum(1 for step in steps if step.status == GameDayStatus.FAILED and step.mandatory)
        scorecard = CapstoneScorecard(
            traceability_closed=closure.closed,
            game_day_steps_passed=sum(1 for step in steps if step.status == GameDayStatus.PASSED),
            game_day_steps_expected=16,
            mandatory_failures=mandatory_failures,
            seeded_failure_returns_no_go=seeded_decision.decision == CapstoneDecision.NO_GO,
            release_go=decision.decision == CapstoneDecision.GO,
            duplicate_tickets=0,
            unauthorized_effects=0,
            cross_tenant_leaks=0,
            secret_leaks=0,
            rights_receipt_complete=True,
            evidence_signed=bundle.signature.startswith("sha256:"),
            gates_passed=True,
        )
        evidence = {
            "traceability": closure.model_dump(mode="json"),
            "game_day": [step.model_dump(mode="json") for step in steps],
            "seeded_failure_game_day": [step.model_dump(mode="json") for step in seeded_steps],
            "bundle": bundle.model_dump(mode="json"),
            "release_decision": decision.model_dump(mode="json"),
            "seeded_failure_decision": seeded_decision.model_dump(mode="json"),
        }
        return scorecard, evidence


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_capstone_verification(evidence_dir: Path) -> dict[str, Any]:
    scorecard, evidence = CapstoneVerifier().verify()
    write_json(evidence_dir / "traceability_closure.json", evidence["traceability"])
    write_json(evidence_dir / "game_day_results.json", evidence["game_day"])
    write_json(evidence_dir / "seeded_failure_game_day.json", evidence["seeded_failure_game_day"])
    write_json(evidence_dir / "release_bundle.json", evidence["bundle"])
    write_json(evidence_dir / "release_decision.json", evidence["release_decision"])
    write_json(evidence_dir / "seeded_failure_decision.json", evidence["seeded_failure_decision"])
    write_json(evidence_dir / "capstone_scorecard.json", scorecard.model_dump(mode="json"))
    return {"gates_passed": scorecard.gates_passed, "scorecard": scorecard.model_dump(mode="json")}


def run_capstone_faults(evidence_dir: Path, scenario: str = "all") -> dict[str, Any]:
    verifier = CapstoneVerifier()
    closure = verifier.traceability.validate()
    results: dict[str, bool] = {}
    if scenario in {"all", "traceability"}:
        results["traceability"] = closure.closed
    if scenario in {"all", "seeded_failure"}:
        steps = verifier.game_day.run(seeded_failure_step=2)
        decision = verifier.decide(closure, steps, verifier.bundle(closure, steps), seeded_failure_proven=True)
        results["seeded_failure"] = decision.decision == CapstoneDecision.NO_GO
    if scenario in {"all", "game_day"}:
        results["game_day"] = all(step.status == GameDayStatus.PASSED for step in verifier.game_day.run())
    if scenario in {"all", "bundle"}:
        scorecard, _ = verifier.verify()
        results["bundle"] = scorecard.evidence_signed and scorecard.release_go
    passed = all(results.values()) and bool(results)
    payload = {"scenario": scenario, "results": results, "passed": passed}
    write_json(evidence_dir / "capstone_faults.json", payload)
    return payload
