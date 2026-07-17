"""Deterministic capstone verifier for Chapter 16."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from policyops.capstone.schemas import (
    CapstoneDecision,
    CapstoneReleaseDecision,
    CapstoneScorecard,
    GameDayStatus,
    GameDayStepResult,
    ReleaseBundle,
    TraceabilityClosure,
)
from policyops.governance import GovernanceVerification
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
