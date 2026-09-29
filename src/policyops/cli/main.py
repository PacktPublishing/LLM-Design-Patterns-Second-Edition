"""policyops CLI — env / verify / fault / eval for chapter labs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(add_completion=False, no_args_is_help=True)
env_app = typer.Typer(help="Lab environment lifecycle")
eval_app = typer.Typer(help="Evaluation suite commands (Chapter 2+)")
session_app = typer.Typer(help="Session runtime commands (Chapter 11)")
triage_app = typer.Typer(help="Triage runtime commands (Chapter 10)")
trace_app = typer.Typer(help="Trace inspection commands (Chapter 12)")
experiment_app = typer.Typer(help="Experiment commands (Chapter 12)")
canary_app = typer.Typer(help="Canary commands (Chapter 12)")
ticket_app = typer.Typer(help="Capstone ticket workflow commands (Chapter 16)")
memory_app = typer.Typer(help="Capstone memory lifecycle commands (Chapter 16)")
release_app = typer.Typer(help="Capstone release decision commands (Chapter 16)")
ops_app = typer.Typer(help="Deployment status commands (Chapter 14)")
queue_app = typer.Typer(help="Deployment queue commands (Chapter 14)")
outbox_app = typer.Typer(help="Deployment outbox commands (Chapter 14)")
backup_app = typer.Typer(help="Deployment backup commands (Chapter 14)")
restore_app = typer.Typer(help="Deployment restore commands (Chapter 14)")
game_day_app = typer.Typer(help="Deployment game-day commands (Chapter 14)")
extensions_app = typer.Typer(help="Extension lifecycle commands (Chapter 9)")
app.add_typer(env_app, name="env")
app.add_typer(eval_app, name="eval")
app.add_typer(session_app, name="session")
app.add_typer(triage_app, name="triage")
app.add_typer(trace_app, name="trace")
app.add_typer(experiment_app, name="experiment")
app.add_typer(canary_app, name="canary")
app.add_typer(ticket_app, name="ticket")
app.add_typer(memory_app, name="memory")
app.add_typer(release_app, name="release")
app.add_typer(ops_app, name="ops")
app.add_typer(queue_app, name="queue")
app.add_typer(outbox_app, name="outbox")
app.add_typer(backup_app, name="backup")
app.add_typer(restore_app, name="restore")
app.add_typer(game_day_app, name="game-day")
app.add_typer(extensions_app, name="extensions")
console = Console()

ROOT = Path(__file__).resolve().parents[3]


def _lab_dir(lab: str) -> Path:
    return ROOT / "labs" / lab


def _build_dir(lab: str) -> Path:
    path = ROOT / "build" / lab
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fixture_pack(lab: str) -> Path:
    lab_fixtures = _lab_dir(lab) / "fixtures"
    if lab_fixtures.exists():
        return lab_fixtures
    return ROOT / "labs" / "ch01" / "fixtures"


def _session_runtime_root() -> Path:
    path = _build_dir("ch11") / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _triage_runtime_root() -> Path:
    path = _build_dir("ch10") / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _telemetry_runtime_root() -> Path:
    path = _build_dir("ch12") / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deployment_runtime_root() -> Path:
    path = _build_dir("ch14") / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extensions_runtime_root() -> Path:
    path = _build_dir("ch09") / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _capstone_runtime_root() -> Path:
    path = _build_dir("ch16") / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return "sha256:" + ("0" * 64)
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _lock_hash() -> str | None:
    for name in ("uv.lock", "requirements.lock", "poetry.lock"):
        path = ROOT / name
        if path.exists():
            return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return None


@env_app.command("up")
def env_up(
    lab: str = typer.Option(..., "--lab"),
    profile: str = typer.Option("fixture", "--profile"),
) -> None:
    lab_path = _lab_dir(lab)
    if not lab_path.exists():
        console.print(f"[red]lab missing:[/red] {lab_path}")
        raise typer.Exit(1)
    os.environ["POLICYOPS_PROFILE"] = profile
    os.environ["POLICYOPS_ADAPTER"] = "replay" if profile == "fixture" else "local"
    os.environ["POLICYOPS_FIXTURE_PACK"] = str(_fixture_pack(lab))
    os.environ["POLICYOPS_LAB_ID"] = lab
    marker = _build_dir(lab) / "env-up.json"
    marker.write_text(
        json.dumps({"lab": lab, "profile": profile, "status": "up"}, indent=2),
        encoding="utf-8",
    )
    console.print(f"[green]env up[/green] lab={lab} profile={profile}")


@env_app.command("down")
def env_down(lab: str = typer.Option(..., "--lab")) -> None:
    marker = _build_dir(lab) / "env-up.json"
    if marker.exists():
        marker.unlink()
    console.print(f"[green]env down[/green] lab={lab}")


@eval_app.command("run")
def eval_run(
    suite: str = typer.Option("regression", "--suite"),
    profile: str = typer.Option("fixture", "--profile"),
) -> None:
    from policyops.eval.runner import run_suite

    evidence = _build_dir("ch02") / suite
    summary = asyncio.run(
        run_suite(
            cases_root=ROOT / "evals" / "cases",
            suite=suite,
            evidence_dir=evidence,
            profile=profile,
        )
    )
    console.print(
        f"suite={suite} pass_rate={summary.pass_rate:.3f} gates_passed={summary.gates_passed}"
    )
    if not summary.gates_passed:
        raise typer.Exit(1)


@eval_app.command("compare")
def eval_compare(
    baseline: str = typer.Option(..., "--baseline"),
    candidate: str = typer.Option(..., "--candidate"),
) -> None:
    """Compare evidence summaries when present; fixture baseline is informational."""
    base = _build_dir("ch02") / "summary.json"
    cand = _build_dir("ch02") / "regression" / "summary.json"
    report = {
        "baseline": baseline,
        "candidate": candidate,
        "baseline_summary": str(base) if base.exists() else None,
        "candidate_summary": str(cand) if cand.exists() else None,
        "note": "Fixture CPSO is labeled; not a hosted-model comparison.",
    }
    out = _build_dir("ch02") / "compare.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    console.print(f"[green]compare written[/green] {out}")


@eval_app.command("graduate")
def eval_graduate(
    correlation_id: str = typer.Option("corr-policyops-1201", "--correlation-id"),
    failure_class: str = typer.Option("product_failure", "--failure-class"),
    expert_role: str = typer.Option("policy operations lead", "--expert-role"),
    expected_behavior: str = typer.Option(
        "Answer should cite the current reimbursement policy and ask for approval before creating a ticket.",
        "--expected-behavior",
    ),
) -> None:
    from policyops.telemetry import AdjudicationRequest, FailureClass, TelemetryRuntime

    envelope = TelemetryRuntime(_telemetry_runtime_root()).adjudicate(
        AdjudicationRequest(
            correlation_id=correlation_id,
            failure_class=FailureClass(failure_class),
            expert_role=expert_role,
            expected_behavior=expected_behavior,
        )
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@session_app.command("run")
def session_run(
    session_id: str = typer.Argument(...),
    tenant_id: str = typer.Option("tenant_alpha", "--tenant-id"),
    actor_id: str = typer.Option("actor_reader", "--actor-id"),
    expected_version: int = typer.Option(0, "--expected-version"),
    owner_id: str = typer.Option("worker-a", "--owner-id"),
    fault: str | None = typer.Option(None, "--fault"),
) -> None:
    from policyops.harness import FaultScenario, SessionRunRequest, SessionRuntime

    runtime = SessionRuntime(_session_runtime_root())
    request = SessionRunRequest(
        expected_version=expected_version,
        owner_id=owner_id,
        fault=FaultScenario(fault) if fault else None,
    )
    envelope = runtime.run(
        session_id,
        request,
        tenant_id=tenant_id,
        actor_id=actor_id,
        configuration_id="cli-session-runtime",
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@session_app.command("inspect")
def session_inspect(session_id: str = typer.Argument(...)) -> None:
    from policyops.harness import SessionRuntime

    envelope = SessionRuntime(_session_runtime_root()).inspect(session_id)
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@session_app.command("replay")
def session_replay(
    session_id: str = typer.Argument(...),
    no_effects: bool = typer.Option(False, "--no-effects"),
) -> None:
    from policyops.harness import SessionRuntime

    if not no_effects:
        console.print("[red]session replay requires --no-effects[/red]")
        raise typer.Exit(1)
    envelope = SessionRuntime(_session_runtime_root()).replay_no_effects(session_id)
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@session_app.command("reconcile")
def session_reconcile(session_id: str = typer.Argument(...)) -> None:
    from policyops.harness import SessionRuntime

    envelope = SessionRuntime(_session_runtime_root()).reconcile(session_id)
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@session_app.command("resume")
def session_resume(
    session_id: str = typer.Argument(...),
    tenant_id: str = typer.Option("tenant_alpha", "--tenant-id"),
    actor_id: str = typer.Option("actor_reader", "--actor-id"),
    expected_version: int | None = typer.Option(None, "--expected-version"),
    owner_id: str = typer.Option("worker-b", "--owner-id"),
) -> None:
    from policyops.harness import SessionResumeRequest, SessionRuntime

    envelope = SessionRuntime(_session_runtime_root()).resume(
        session_id,
        SessionResumeRequest(expected_version=expected_version, owner_id=owner_id),
        tenant_id=tenant_id,
        actor_id=actor_id,
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@session_app.command("cancel")
def session_cancel(
    session_id: str = typer.Argument(...),
    tenant_id: str = typer.Option("tenant_alpha", "--tenant-id"),
    actor_id: str = typer.Option("actor_reader", "--actor-id"),
    expected_version: int | None = typer.Option(None, "--expected-version"),
    owner_id: str = typer.Option("operator-a", "--owner-id"),
) -> None:
    from policyops.harness import SessionCancelRequest, SessionRuntime

    envelope = SessionRuntime(_session_runtime_root()).cancel(
        session_id,
        SessionCancelRequest(expected_version=expected_version, owner_id=owner_id),
        tenant_id=tenant_id,
        actor_id=actor_id,
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@triage_app.command("run")
def triage_run(
    variant: str = typer.Option(..., "--variant"),
    scenario_id: str = typer.Option("policy-triage-default", "--scenario-id"),
    tenant_id: str = typer.Option("tenant_alpha", "--tenant-id"),
    actor_id: str = typer.Option("actor_reader", "--actor-id"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    browser_profile: str | None = typer.Option(None, "--browser-profile"),
    worker_limit: int | None = typer.Option(None, "--worker-limit"),
) -> None:
    from datetime import UTC, datetime

    from policyops.contracts import AuthorizationContext, Budget, RunContext
    from policyops.orchestration import BudgetLedger, TopologyVariant, TriageRunRequest, TriageRuntime

    budget = BudgetLedger(worker_limit=worker_limit) if worker_limit is not None else None
    context = RunContext(
        request_id=f"req_triage_{variant}",
        trace_id=f"trace_triage_{variant}",
        tenant_id=tenant_id,
        actor_id=actor_id,
        roles=["policy-reader"],
        purpose="policy-triage",
        configuration_id="cli-triage-runtime",
        configuration_versions={"orchestration": "1.0.0"},
        deadline_at=datetime(2030, 1, 1, 0, 0, 5, tzinfo=UTC),
        budget=Budget(max_input_tokens=2048, max_output_tokens=512),
        authorization_context=AuthorizationContext(
            scopes=["policy:read", "ticket:create", "ticket:preview"],
            decision_id="authz-triage-cli",
        ),
    )
    envelope = TriageRuntime(_triage_runtime_root()).create(
        TriageRunRequest(
            scenario_id=scenario_id,
            variant=TopologyVariant(variant),
            budget=budget,
            browser_profile=browser_profile,
            idempotency_key=idempotency_key,
        ),
        context=context,
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@triage_app.command("inspect")
def triage_inspect(run_id: str = typer.Argument(...)) -> None:
    from policyops.orchestration import TriageRuntime

    envelope = TriageRuntime(_triage_runtime_root()).inspect(run_id)
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@triage_app.command("pause")
def triage_pause(
    run_id: str = typer.Argument(...),
    expected_version: int = typer.Option(..., "--expected-version"),
) -> None:
    from policyops.orchestration import TriageControlRequest, TriageRuntime

    envelope = TriageRuntime(_triage_runtime_root()).pause(
        run_id,
        TriageControlRequest(expected_version=expected_version),
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@triage_app.command("resume")
def triage_resume(
    run_id: str = typer.Argument(...),
    expected_version: int = typer.Option(..., "--expected-version"),
) -> None:
    from policyops.orchestration import TriageControlRequest, TriageRuntime

    envelope = TriageRuntime(_triage_runtime_root()).resume(
        run_id,
        TriageControlRequest(expected_version=expected_version),
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@triage_app.command("cancel")
def triage_cancel(
    run_id: str = typer.Argument(...),
    expected_version: int = typer.Option(..., "--expected-version"),
) -> None:
    from policyops.orchestration import TriageControlRequest, TriageRuntime

    envelope = TriageRuntime(_triage_runtime_root()).cancel(
        run_id,
        TriageControlRequest(expected_version=expected_version),
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@ticket_app.command("preview")
def ticket_preview(
    title: str = typer.Option("Remote-work exception support", "--title"),
    description: str = typer.Option(
        "Create a policy support ticket for a manager-approved remote-work exception.",
        "--description",
    ),
    severity: str = typer.Option("medium", "--severity"),
    source_ref: list[str] = typer.Option(
        ["policy_remote:v2:span_remote_approval"],
        "--source-ref",
    ),
    tenant_id: str = typer.Option("tenant_alpha", "--tenant-id"),
    actor_id: str = typer.Option("actor_reader", "--actor-id"),
) -> None:
    from policyops.capstone import CapstoneRuntime, TicketPreviewRequest
    from policyops.contracts import AuthorizationContext, Budget, RunContext
    from policyops.extensions import TicketInput
    from datetime import UTC, datetime

    context = RunContext(
        request_id="req_capstone_preview",
        trace_id="trace_capstone_preview",
        tenant_id=tenant_id,
        actor_id=actor_id,
        roles=["policy_support"],
        purpose="policy_support",
        configuration_id="cli-capstone-runtime",
        configuration_versions={"capstone": "1.0.0"},
        deadline_at=datetime(2030, 1, 1, 0, 0, 5, tzinfo=UTC),
        budget=Budget(max_input_tokens=2048, max_output_tokens=512),
        authorization_context=AuthorizationContext(
            scopes=["ticket:preview", "ticket:create"],
            decision_id="authz-capstone-cli",
        ),
    )
    envelope = CapstoneRuntime(_capstone_runtime_root()).preview_ticket(
        TicketPreviewRequest(
            ticket=TicketInput(
                tenant_id=tenant_id,
                title=title,
                description=description,
                severity=severity,
                source_refs=source_ref,
            )
        ),
        context=context,
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@ticket_app.command("execute")
def ticket_execute(
    title: str = typer.Option("Remote-work exception support", "--title"),
    description: str = typer.Option(
        "Create a policy support ticket for a manager-approved remote-work exception.",
        "--description",
    ),
    severity: str = typer.Option("medium", "--severity"),
    source_ref: list[str] = typer.Option(
        ["policy_remote:v2:span_remote_approval"],
        "--source-ref",
    ),
    idempotency_key: str = typer.Option("capstone-cli-1", "--idempotency-key"),
    tenant_id: str = typer.Option("tenant_alpha", "--tenant-id"),
    actor_id: str = typer.Option("actor_reader", "--actor-id"),
) -> None:
    from policyops.capstone import CapstoneRuntime, TicketExecuteRequest, TicketPreviewRequest
    from policyops.contracts import AuthorizationContext, Budget, RunContext
    from policyops.extensions import TicketInput
    from datetime import UTC, datetime

    runtime = CapstoneRuntime(_capstone_runtime_root())
    context = RunContext(
        request_id="req_capstone_execute",
        trace_id="trace_capstone_execute",
        tenant_id=tenant_id,
        actor_id=actor_id,
        roles=["policy_support"],
        purpose="policy_support",
        configuration_id="cli-capstone-runtime",
        configuration_versions={"capstone": "1.0.0"},
        deadline_at=datetime(2030, 1, 1, 0, 0, 5, tzinfo=UTC),
        budget=Budget(max_input_tokens=2048, max_output_tokens=512),
        authorization_context=AuthorizationContext(
            scopes=["ticket:preview", "ticket:create"],
            decision_id="authz-capstone-cli",
        ),
    )
    ticket = TicketInput(
        tenant_id=tenant_id,
        title=title,
        description=description,
        severity=severity,
        source_refs=source_ref,
    )
    preview = runtime.preview_ticket(TicketPreviewRequest(ticket=ticket), context=context)
    envelope = runtime.execute_ticket(
        TicketExecuteRequest(
            ticket=ticket,
            preview=preview.preview,
            idempotency_key=idempotency_key,
        ),
        context=context,
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@ticket_app.command("inspect-run")
def ticket_inspect_run(run_id: str = typer.Argument(...)) -> None:
    from policyops.capstone import CapstoneRuntime

    run = CapstoneRuntime(_capstone_runtime_root()).inspect_run(run_id)
    console.print_json(json.dumps(run.model_dump(mode="json")))


@memory_app.command("export")
def memory_export() -> None:
    from policyops.capstone import CapstoneRuntime

    envelope = CapstoneRuntime(_capstone_runtime_root()).memory_export()
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@memory_app.command("correct")
def memory_correct(
    record_id: str = typer.Argument(...),
    expected_version: int = typer.Option(..., "--expected-version"),
    text: str = typer.Option(..., "--text"),
) -> None:
    from policyops.capstone import CapstoneRuntime, MemoryCorrectionRequest

    envelope = CapstoneRuntime(_capstone_runtime_root()).memory_correct(
        MemoryCorrectionRequest(
            record_id=record_id,
            expected_version=expected_version,
            text=text,
        )
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@memory_app.command("delete")
def memory_delete(
    record_id: str = typer.Argument(...),
    expected_version: int = typer.Option(..., "--expected-version"),
) -> None:
    from policyops.capstone import CapstoneRuntime, MemoryDeleteRequest

    envelope = CapstoneRuntime(_capstone_runtime_root()).memory_delete(
        MemoryDeleteRequest(record_id=record_id, expected_version=expected_version)
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@ops_app.command("status")
def ops_status(
    role: str = typer.Option("operator", "--role"),
) -> None:
    from policyops.deployment import DeploymentRuntime

    payload = DeploymentRuntime(_deployment_runtime_root()).status(role=role)
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@queue_app.command("drain")
def queue_drain(
    role: str = typer.Option("operator", "--role"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
) -> None:
    from policyops.deployment import DeploymentRuntime

    payload = DeploymentRuntime(_deployment_runtime_root()).queue_drain(role=role, dry_run=dry_run)
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@outbox_app.command("reconcile")
def outbox_reconcile(
    role: str = typer.Option("operator", "--role"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
) -> None:
    from policyops.deployment import DeploymentRuntime

    payload = DeploymentRuntime(_deployment_runtime_root()).outbox_reconcile(role=role, dry_run=dry_run)
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@extensions_app.command("verify")
def extensions_verify(
    package: str = typer.Argument("policyops-ticket-pack"),
    tampered: bool = typer.Option(False, "--tampered"),
) -> None:
    from policyops.extensions import ExtensionRuntime, fixture_manifest

    runtime = ExtensionRuntime(_extensions_runtime_root())
    manifest, files = fixture_manifest(runtime.loader, tampered=tampered)
    payload = runtime.verify_package(manifest, files)
    console.print_json(json.dumps({"package": package, **payload.model_dump(mode="json")}))


@extensions_app.command("install")
def extensions_install(
    package: str = typer.Argument("policyops-ticket-pack"),
) -> None:
    from policyops.extensions import ExtensionRuntime, fixture_manifest

    runtime = ExtensionRuntime(_extensions_runtime_root())
    manifest, files = fixture_manifest(runtime.loader)
    payload = runtime.install_package(manifest, files)
    console.print_json(json.dumps({"package": package, **payload.model_dump(mode="json")}))


@extensions_app.command("stage")
def extensions_stage(
    package: str = typer.Argument("policyops-ticket-pack"),
    version: str = typer.Option("1.1.0", "--version"),
    predecessor: str = typer.Option("1.0.0", "--predecessor"),
) -> None:
    from policyops.extensions import ExtensionRuntime, fixture_manifest

    runtime = ExtensionRuntime(_extensions_runtime_root())
    manifest, files = fixture_manifest(runtime.loader, version=version, predecessor=predecessor)
    payload = runtime.stage_package(manifest, files)
    console.print_json(json.dumps({"package": package, **payload.model_dump(mode="json")}))


@extensions_app.command("activate")
def extensions_activate(
    extension_id: str = typer.Argument("policyops-ticket-pack"),
    version: str | None = typer.Option(None, "--version"),
) -> None:
    from policyops.extensions import ExtensionRuntime

    payload = ExtensionRuntime(_extensions_runtime_root()).activate_extension(extension_id, version)
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@extensions_app.command("disable")
def extensions_disable(
    extension_id: str = typer.Argument("policyops-ticket-pack"),
) -> None:
    from policyops.extensions import ExtensionRuntime

    payload = ExtensionRuntime(_extensions_runtime_root()).disable_extension(extension_id)
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@extensions_app.command("rollback")
def extensions_rollback(
    extension_id: str = typer.Argument("policyops-ticket-pack"),
) -> None:
    from policyops.extensions import ExtensionRuntime

    payload = ExtensionRuntime(_extensions_runtime_root()).rollback_extension(extension_id)
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@extensions_app.command("revoke")
def extensions_revoke(
    extension_id: str = typer.Argument("policyops-ticket-pack"),
) -> None:
    from policyops.extensions import ExtensionRuntime

    payload = ExtensionRuntime(_extensions_runtime_root()).revoke_extension(extension_id)
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@release_app.command("decide")
def release_decide() -> None:
    from policyops.capstone import CapstoneRuntime

    envelope = CapstoneRuntime(_capstone_runtime_root()).release_decision()
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@release_app.command("canary")
def release_canary(
    role: str = typer.Option("release-engineer", "--role"),
    candidate_digest: str = typer.Option("sha256:goodcandidate", "--candidate-digest"),
    bad_image: bool = typer.Option(False, "--bad-image/--good-image"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
) -> None:
    from policyops.deployment import DeploymentRuntime

    payload = DeploymentRuntime(_deployment_runtime_root()).canary_release(
        role=role,
        candidate_digest=candidate_digest,
        bad_image=bad_image,
        dry_run=dry_run,
    )
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@release_app.command("rollback")
def release_rollback(
    role: str = typer.Option("release-engineer", "--role"),
    target_digest: str = typer.Option("sha256:acceptedbaseline", "--target-digest"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
) -> None:
    from policyops.deployment import DeploymentRuntime

    payload = DeploymentRuntime(_deployment_runtime_root()).rollback_release(
        role=role,
        target_digest=target_digest,
        dry_run=dry_run,
    )
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@backup_app.command("verify")
def backup_verify(
    role: str = typer.Option("database-engineer", "--role"),
    backup_id: str = typer.Option("backup-valid", "--backup-id"),
) -> None:
    from policyops.deployment import DeploymentRuntime

    payload = DeploymentRuntime(_deployment_runtime_root()).verify_backup(role=role, backup_id=backup_id)
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@restore_app.command("run")
def restore_run(
    role: str = typer.Option("database-engineer", "--role"),
    backup_id: str = typer.Option("backup-valid", "--backup-id"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
) -> None:
    from policyops.deployment import DeploymentRuntime

    payload = DeploymentRuntime(_deployment_runtime_root()).run_restore(
        role=role,
        backup_id=backup_id,
        dry_run=dry_run,
    )
    console.print_json(json.dumps(payload.model_dump(mode="json")))


@game_day_app.command("execute")
def game_day_execute(
    role: str = typer.Option("operator", "--role"),
) -> None:
    from policyops.deployment import DeploymentRuntime, run_deployment_faults, run_deployment_verification

    runtime = DeploymentRuntime(_deployment_runtime_root())
    status = runtime.status(role=role)
    evidence_dir = _build_dir("ch14") / "game_day"
    verify = run_deployment_verification(evidence_dir)
    faults = run_deployment_faults(evidence_dir, "all")
    payload = {
        "status": status.model_dump(mode="json"),
        "verify": verify,
        "faults": faults,
        "passed": verify["gates_passed"] and faults["passed"],
    }
    console.print_json(json.dumps(payload))


@trace_app.command("inspect")
def trace_inspect(
    correlation_id: str = typer.Argument(...),
) -> None:
    from policyops.telemetry import TelemetryRuntime

    envelope = TelemetryRuntime(_telemetry_runtime_root()).inspect_operation(correlation_id)
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@experiment_app.command("run")
def experiment_run(
    candidate_profile: str = typer.Option("overfit", "--candidate-profile"),
) -> None:
    from policyops.telemetry import ExperimentRunRequest, TelemetryRuntime

    envelope = TelemetryRuntime(_telemetry_runtime_root()).run_experiment(
        ExperimentRunRequest(candidate_profile=candidate_profile)
    )
    console.print_json(json.dumps(envelope.model_dump(mode="json")))


@canary_app.command("simulate")
def canary_simulate(
    bad_release: bool = typer.Option(True, "--bad-release/--good-release"),
) -> None:
    from policyops.telemetry import TelemetryRuntime

    report = TelemetryRuntime(_telemetry_runtime_root()).simulate_canary(
        bad_release=bad_release
    )
    console.print_json(json.dumps(report.model_dump(mode="json")))


@canary_app.command("stop")
def canary_stop(
    canary_id: str = typer.Argument(...),
    reason: str = typer.Option("operator stopped canary", "--reason"),
) -> None:
    from policyops.telemetry import CanaryStopRequest, TelemetryRuntime

    report = TelemetryRuntime(_telemetry_runtime_root()).stop_canary(
        canary_id,
        CanaryStopRequest(reason=reason),
    )
    console.print_json(json.dumps(report.model_dump(mode="json")))


@app.command("verify")
def verify(
    lab: str = typer.Argument(...),
    profile: str = typer.Option("fixture", "--profile"),
    all_: bool = typer.Option(False, "--all", help="Run all cumulative gates when supported"),
    junit: Optional[Path] = typer.Option(None, "--junit"),
    evidence: Optional[Path] = typer.Option(None, "--evidence"),
) -> None:
    env_up(lab=lab, profile=profile)
    evidence_dir = Path(evidence) if evidence else _build_dir(lab)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    junit_path = Path(junit) if junit else evidence_dir / "junit.xml"
    custom_scorecard: dict[str, object] | None = None
    custom_trace_payload: dict[str, object] | None = None

    env = os.environ.copy()
    env["POLICYOPS_PROFILE"] = profile
    env["POLICYOPS_ADAPTER"] = "replay" if profile == "fixture" else "local"
    env["POLICYOPS_FIXTURE_PACK"] = str(_fixture_pack(lab))
    env["POLICYOPS_LAB_ID"] = lab
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

    test_targets = {
        "ch01": [
            "tests/contract",
            "tests/api",
            "tests/fault",
            "tests/boundary",
            "tests/config",
            "tests/telemetry",
            "tests/util",
        ],
        "ch02": ["tests/eval", "tests/contract", "tests/boundary"],
        "ch03": ["tests/adaptation", "tests/boundary"],
        "ch04": ["tests/inference", "tests/contract", "tests/boundary"],
        "ch05": ["tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch06": ["tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch07": ["tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch08": ["tests/memory", "tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch09": ["tests/extensions", "tests/memory", "tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch10": ["tests/orchestration", "tests/extensions", "tests/memory", "tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch11": ["tests/harness", "tests/orchestration", "tests/extensions", "tests/memory", "tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch12": ["tests/telemetry", "tests/harness", "tests/orchestration", "tests/extensions", "tests/memory", "tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch13": ["tests/security", "tests/telemetry", "tests/harness", "tests/orchestration", "tests/extensions", "tests/memory", "tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch14": ["tests/deployment", "tests/security", "tests/telemetry", "tests/harness", "tests/orchestration", "tests/extensions", "tests/memory", "tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch15": ["tests/governance", "tests/deployment", "tests/security", "tests/telemetry", "tests/harness", "tests/orchestration", "tests/extensions", "tests/memory", "tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
        "ch16": ["tests/capstone", "tests/governance", "tests/deployment", "tests/security", "tests/telemetry", "tests/harness", "tests/orchestration", "tests/extensions", "tests/memory", "tests/graph", "tests/retrieval", "tests/context", "tests/inference", "tests/contract", "tests/boundary"],
    }.get(lab, ["tests"])
    if all_ and lab != "ch16":
        console.print(f"[yellow]--all is only meaningful for ch16; running {lab} configured gates[/yellow]")

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *test_targets,
        "-q",
        f"--junitxml={junit_path}",
    ]
    result = subprocess.run(cmd, cwd=ROOT, env=env, check=False)

    eval_ok = True
    if lab == "ch01" and result.returncode == 0:
        from policyops.api.verification import run_foundation_verification

        payload = run_foundation_verification(evidence_dir, ROOT / "labs" / "ch01" / "fixtures")
        eval_ok = payload["gates_passed"] is True
        custom_scorecard = payload["scorecard"]
        custom_trace_payload = payload["trace_redaction"]
    elif lab == "ch02" and result.returncode == 0:
        from policyops.eval.runner import run_suite

        summary = asyncio.run(
            run_suite(
                cases_root=ROOT / "evals" / "cases",
                suite="all",
                evidence_dir=evidence_dir,
                profile=profile,
            )
        )
        eval_ok = summary.gates_passed
    elif lab == "ch03" and result.returncode == 0:
        from policyops.adaptation import run_adaptation_verification

        payload = run_adaptation_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch04" and result.returncode == 0:
        from policyops.inference import run_gateway_verification

        payload = run_gateway_verification(evidence_dir)
        eval_ok = payload["passed"] is True
    elif lab == "ch05" and result.returncode == 0:
        from policyops.context import run_context_verification

        payload = run_context_verification(evidence_dir)
        eval_ok = payload["passed"] is True
    elif lab == "ch06" and result.returncode == 0:
        from policyops.retrieval import run_retrieval_verification

        payload = run_retrieval_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch07" and result.returncode == 0:
        from policyops.graph import run_graph_verification

        payload = run_graph_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch08" and result.returncode == 0:
        from policyops.memory import run_memory_verification

        payload = run_memory_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch09" and result.returncode == 0:
        from policyops.extensions import run_extension_verification

        payload = run_extension_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch10" and result.returncode == 0:
        from policyops.orchestration import run_orchestration_verification

        payload = run_orchestration_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch11" and result.returncode == 0:
        from policyops.harness import run_harness_verification

        payload = run_harness_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch12" and result.returncode == 0:
        from policyops.telemetry import run_observability_verification

        payload = run_observability_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch13" and result.returncode == 0:
        from policyops.security import run_security_verification

        payload = run_security_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch14" and result.returncode == 0:
        from policyops.deployment import run_deployment_verification

        payload = run_deployment_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch15" and result.returncode == 0:
        from policyops.governance import run_governance_verification

        payload = run_governance_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True
    elif lab == "ch16" and result.returncode == 0:
        from policyops.capstone import run_capstone_verification

        payload = run_capstone_verification(evidence_dir)
        eval_ok = payload["gates_passed"] is True

    settings_fingerprint = None
    fixture_hash = _tree_hash(_fixture_pack(lab))
    try:
        from policyops.config import Settings

        settings_fingerprint = Settings(
            profile=profile,
            adapter="replay" if profile == "fixture" else "local",
            fixture_pack=_fixture_pack(lab),
            lab_id=lab,
        ).fingerprint()
    except Exception:
        settings_fingerprint = "unavailable"

    # Chapter 1's evidence is intentionally modest but explicit: it proves
    # deterministic fixture identity, non-secret configuration identity, and
    # the redacted span allowlist that later evaluation/governance chapters
    # consume.
    from policyops.telemetry import clear_spans, recorded_spans, span

    clear_spans()
    with span(
        "policyops.verify",
        {
            "tenant_id": "tenant_alpha",
            "actor_id": "actor_reader",
            "trace_id": "trace_verify_fixture",
            "request_id": "req_verify_fixture",
            "configuration_id": settings_fingerprint,
            "question": "this raw prompt-like field must not be recorded",
            "authorization_token": "sk-not-a-real-token",
        },
    ):
        pass

    trace_payload = custom_trace_payload or {
        "lab": lab,
        "profile": profile,
        "redaction": "allowlist",
        "sample_spans": recorded_spans(),
        "allowed_attributes": sorted(
            [
                "tenant_id",
                "actor_id",
                "trace_id",
                "request_id",
                "configuration_id",
                "adapter",
                "status",
                "error_code",
                "http.method",
                "http.route",
                "http.status_code",
            ]
        ),
        "forbidden_attributes": ["prompt", "question", "answer_text", "authorization_token"],
    }
    (evidence_dir / "trace_redaction.json").write_text(
        json.dumps(trace_payload, indent=2),
        encoding="utf-8",
    )

    fingerprints = {
        "lab": lab,
        "profile": profile,
        "configuration_id": settings_fingerprint,
        "fixture_pack_hash": fixture_hash,
        "dependency_lock_hash": _lock_hash(),
        "python_version": sys.version.split()[0],
    }
    (evidence_dir / "fingerprints.json").write_text(
        json.dumps(fingerprints, indent=2),
        encoding="utf-8",
    )

    gates = {
        "lab": lab,
        "profile": profile,
        "exit_code": result.returncode if eval_ok else 1,
        "junit": str(junit_path).replace("\\", "/"),
        "trace_redaction": str(evidence_dir / "trace_redaction.json").replace("\\", "/"),
        "fingerprints": str(evidence_dir / "fingerprints.json").replace("\\", "/"),
        "passed": result.returncode == 0 and eval_ok,
    }
    (evidence_dir / "result.json").write_text(json.dumps(gates, indent=2), encoding="utf-8")
    scorecard = custom_scorecard or {
        "lab": lab,
        "profile": profile,
        "note": "fixture latency is not provider performance",
        "configuration_id": settings_fingerprint,
        "fixture_pack_hash": fixture_hash,
        "gates_passed": gates["passed"],
    }
    (evidence_dir / "scorecard.json").write_text(
        json.dumps(scorecard, indent=2), encoding="utf-8"
    )
    if not gates["passed"]:
        console.print("[red]verify failed[/red]")
        raise typer.Exit(1)
    console.print(f"[green]verify passed[/green] evidence={evidence_dir}")


@app.command("fault")
def fault(
    lab: str = typer.Argument(...),
    scenario: str = typer.Option("all", "--scenario"),
) -> None:
    evidence_dir = _build_dir(lab)
    if lab == "ch12":
        from policyops.telemetry import run_observability_faults

        payload = run_observability_faults(evidence_dir, scenario)
        if not payload["passed"]:
            raise typer.Exit(1)
        console.print("[green]fault drills passed[/green]")
        return
    if lab == "ch13":
        from policyops.security import run_security_faults

        payload = run_security_faults(evidence_dir, scenario)
        if not payload["passed"]:
            raise typer.Exit(1)
        console.print("[green]fault drills passed[/green]")
        return
    if lab == "ch14":
        from policyops.deployment import run_deployment_faults

        payload = run_deployment_faults(evidence_dir, scenario)
        if not payload["passed"]:
            raise typer.Exit(1)
        console.print("[green]fault drills passed[/green]")
        return
    if lab == "ch15":
        from policyops.governance import run_governance_faults

        payload = run_governance_faults(evidence_dir, scenario)
        if not payload["passed"]:
            raise typer.Exit(1)
        console.print("[green]fault drills passed[/green]")
        return
    if lab == "ch16":
        from policyops.capstone import run_capstone_faults

        payload = run_capstone_faults(evidence_dir, scenario)
        if not payload["passed"]:
            raise typer.Exit(1)
        console.print("[green]fault drills passed[/green]")
        return
    if lab != "ch01":
        console.print(f"[yellow]fault drills for {lab} reuse ch01 model faults[/yellow]")
    env = os.environ.copy()
    env["POLICYOPS_FIXTURE_PACK"] = str(_fixture_pack("ch01"))
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "pytest", "tests/fault", "-q"]
    if scenario != "all":
        cmd.extend(["-k", scenario])
    rc = subprocess.run(cmd, cwd=ROOT, env=env, check=False).returncode
    results = [{"scenario": scenario, "exit_code": rc}]
    (evidence_dir / "faults.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    if rc != 0:
        raise typer.Exit(1)
    console.print("[green]fault drills passed[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
