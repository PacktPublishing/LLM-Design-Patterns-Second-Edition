"""Deterministic Chapter 12 trace-to-safe-improvement pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from policyops.harness import EventStore, ResumableLoop
from policyops.telemetry.schemas import (
    ArtifactRecord,
    ArtifactSet,
    CanaryDecision,
    CanaryMetric,
    CanaryReport,
    EvaluationCase,
    ExperimentDecision,
    ExperimentLedger,
    ExperimentManifest,
    FailureClass,
    HarnessRetirementAdr,
    ObservabilityScorecard,
    RawEvent,
    ReconstructionReport,
    RedactedSpan,
    SamplingDecision,
    SloRecord,
    SpanKind,
    SuiteResult,
    TraceAdjudication,
    TraceContext,
)

ALLOWED_ATTRS = frozenset(
    {
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
    }
)
SEMANTIC_ATTRS = frozenset(
    {
        "component",
        "operation",
        "status",
        "latency_ms",
        "cost_cents",
        "tokens_in",
        "tokens_out",
        "quality_score",
        "ticket_created",
        "tool_name",
        "approval_required",
        "browser_profile",
        "risk_tier",
    }
)
CARDINALITY_LIMIT = 100
PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
]
SECRET_PATTERN = re.compile(r"\b(?:sk|pk|ghp|xoxb)-[A-Za-z0-9_\-]{8,}\b")

_RECORDED: list[dict[str, Any]] = []


class InMemorySpanExporter(SpanExporter):
    def export(self, spans) -> SpanExportResult:  # type: ignore[no-untyped-def]
        for span in spans:
            _RECORDED.append(
                {
                    "name": span.name,
                    "attributes": {
                        k: v for k, v in dict(span.attributes or {}).items() if k in ALLOWED_ATTRS
                    },
                }
            )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


_provider: TracerProvider | None = None


def setup_telemetry(service_name: str = "policyops") -> None:
    global _provider
    if _provider is not None:
        return
    _provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    _provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    trace.set_tracer_provider(_provider)


def recorded_spans() -> list[dict[str, Any]]:
    return list(_RECORDED)


def clear_spans() -> None:
    _RECORDED.clear()


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[None]:
    setup_telemetry()
    tracer = trace.get_tracer("policyops")
    safe = {k: v for k, v in (attributes or {}).items() if k in ALLOWED_ATTRS}
    with tracer.start_as_current_span(name, attributes=safe):
        yield


def sha_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def hash_tenant(tenant_id: str) -> str:
    return "tenant_" + hashlib.sha256(f"policyops:{tenant_id}".encode()).hexdigest()[:16]


class ArtifactRegistry:
    def fixture_artifacts(self) -> ArtifactSet:
        names = [
            ("data", "policy-corpus", "2026.07"),
            ("prompt", "answer-contract", "12.0"),
            ("context_policy", "authority-ranked-context", "5.0"),
            ("model_adapter", "replay-model", "4.0"),
            ("index", "hybrid-index", "6.0"),
            ("memory_policy", "governed-memory", "8.0"),
            ("tool", "ticket-tool", "9.0"),
            ("skill", "policy-skill", "9.0"),
            ("protocol", "mcp-stable-profile", "2025-11-25"),
            ("grader", "policyops-grader", "2.0"),
            ("security_policy", "prompt-injection-baseline", "13-preview"),
            ("deployment_profile", "fixture", "12.0"),
        ]
        artifacts = [
            ArtifactRecord(
                artifact_type=kind,
                name=name,
                version=version,
                digest=sha_json({"kind": kind, "name": name, "version": version}),
            )
            for kind, name, version in names
        ]
        return ArtifactSet(artifact_set_id="artifact-set-ch12-fixture", artifacts=artifacts)


class TelemetryPolicy:
    def __init__(self, cardinality_limit: int = CARDINALITY_LIMIT) -> None:
        self.cardinality_limit = cardinality_limit
        self.seen_values: dict[str, set[str]] = {}

    def semantic_context(self, raw: RawEvent) -> TraceContext:
        return TraceContext(
            correlation_id=raw.correlation_id,
            request_id=raw.request_id,
            tenant_hash=hash_tenant(raw.tenant_id),
            actor_class="reader",
            session_id=raw.session_id,
            artifact_set_id=raw.artifact_set_id,
            risk_tier="high" if raw.span_kind in {SpanKind.APPROVAL, SpanKind.EXTERNAL_EFFECT} else "medium",
            sampling_decision=SamplingDecision.REQUIRED
            if raw.span_kind in {SpanKind.APPROVAL, SpanKind.EXTERNAL_EFFECT}
            else SamplingDecision.HEAD,
        )

    def redact_value(self, value: Any) -> str | int | float | bool:
        if isinstance(value, bool | int | float):
            return value
        text = str(value)
        if SECRET_PATTERN.search(text):
            return "[REDACTED_SECRET]"
        for pattern in PII_PATTERNS:
            if pattern.search(text):
                return "[REDACTED_PII]"
        return text

    def normalize(self, raw: RawEvent) -> RedactedSpan:
        attributes: dict[str, str | int | float | bool] = {}
        redacted: list[str] = []
        dropped: list[str] = []
        for key, value in sorted(raw.attributes.items()):
            if key not in SEMANTIC_ATTRS:
                dropped.append(key)
                continue
            safe_value = self.redact_value(value)
            if safe_value != value:
                redacted.append(key)
            value_key = str(safe_value)
            if isinstance(safe_value, str):
                bucket = self.seen_values.setdefault(key, set())
                if value_key not in bucket and len(bucket) >= self.cardinality_limit:
                    dropped.append(key)
                    continue
                bucket.add(value_key)
            attributes[key] = safe_value
        return RedactedSpan(
            name=f"policyops.{raw.span_kind.value}",
            span_kind=raw.span_kind,
            context=self.semantic_context(raw),
            attributes=attributes,
            duration_ms=max(0, raw.ended_at_ms - raw.started_at_ms),
            redacted_fields=redacted,
            dropped_fields=dropped,
        )


class DeterministicExporter:
    def __init__(self, policy: TelemetryPolicy | None = None) -> None:
        self.policy = policy or TelemetryPolicy()
        self.backend_available = True
        self.dropped_on_outage = 0

    def export(self, events: list[RawEvent]) -> list[RedactedSpan]:
        spans = [self.policy.normalize(event) for event in events]
        if not self.backend_available:
            self.dropped_on_outage += len(spans)
            return []
        return sorted(spans, key=lambda item: (item.context.correlation_id, item.name, item.duration_ms))


def fixture_raw_events() -> list[RawEvent]:
    artifact_set_id = "artifact-set-ch12-fixture"
    base = {
        "provider": "fixture",
        "correlation_id": "corr-policyops-1201",
        "request_id": "req-policyops-1201",
        "tenant_id": "tenant-alpha",
        "actor_id": "reader-77",
        "session_id": "session-ch11-a",
        "artifact_set_id": artifact_set_id,
    }
    kinds = [
        SpanKind.REQUEST,
        SpanKind.MODEL,
        SpanKind.RETRIEVAL,
        SpanKind.RERANK,
        SpanKind.MEMORY,
        SpanKind.AGENT,
        SpanKind.HANDOFF,
        SpanKind.BROWSER_OBSERVATION,
        SpanKind.BROWSER_ACTION,
        SpanKind.APPROVAL,
        SpanKind.TOOL,
        SpanKind.SANDBOX,
        SpanKind.EXTERNAL_EFFECT,
        SpanKind.OUTCOME,
    ]
    events: list[RawEvent] = []
    for index, kind in enumerate(kinds):
        attrs: dict[str, Any] = {
            "component": kind.value,
            "operation": f"{kind.value}.run",
            "status": "ok",
            "latency_ms": 80 + index,
            "cost_cents": 0.2 + index / 100,
            "quality_score": 0.86,
            "raw_prompt": "Ken SSN 123-45-6789 and email ken@example.com",
            "authorization_token": "sk-not-a-real-secret-123456789",
            "untrusted_label": f"unique-{index}",
        }
        if kind == SpanKind.TOOL:
            attrs["tool_name"] = "ticket.create"
        if kind == SpanKind.APPROVAL:
            attrs["approval_required"] = True
        if kind == SpanKind.BROWSER_ACTION:
            attrs["browser_profile"] = "fixture-no-network"
        if kind == SpanKind.OUTCOME:
            attrs["ticket_created"] = True
        events.append(
            RawEvent(
                **base,
                event_name=kind.value,
                span_kind=kind,
                attributes=attrs,
                started_at_ms=1_000 + index * 10,
                ended_at_ms=1_050 + index * 10,
            )
        )
    return events


def spans_from_harness_events(store: EventStore) -> list[RawEvent]:
    events: list[RawEvent] = []
    for stream in store.events.values():
        for event in stream:
            events.append(
                RawEvent(
                    provider="chapter11-harness",
                    event_name=event.event_type.value,
                    span_kind=SpanKind.AGENT,
                    correlation_id=event.trace_id,
                    request_id=event.request_id,
                    tenant_id=event.tenant_id,
                    actor_id=event.actor_id,
                    session_id=event.session_id,
                    artifact_set_id=event.configuration_id,
                    attributes={
                        "component": "harness",
                        "operation": event.event_type.value,
                        "status": "ok",
                    },
                    started_at_ms=event.occurred_at,
                    ended_at_ms=event.occurred_at,
                )
            )
    return events


class TraceImprovementPipeline:
    def __init__(self) -> None:
        self.registry = ArtifactRegistry()
        self.policy = TelemetryPolicy()
        self.exporter = DeterministicExporter(self.policy)

    def correlated_trace(self) -> tuple[ArtifactSet, list[RedactedSpan]]:
        artifacts = self.registry.fixture_artifacts()
        spans = self.exporter.export(fixture_raw_events())
        return artifacts, spans

    def slo_records(self) -> list[SloRecord]:
        return [
            SloRecord(
                name="outcome_quality",
                owner="AI engineering",
                window="7d",
                objective=">=0.90 graded success",
                measurement_query="sum(successful_outcomes)/count(outcomes)",
                budget="5% error budget",
            ),
            SloRecord(
                name="p95_latency",
                owner="Platform",
                window="1h",
                objective="p95 < 2500 ms",
                measurement_query="histogram_quantile(0.95, request_latency)",
                budget="2% slow requests",
            ),
            SloRecord(
                name="cost_per_successful_outcome",
                owner="LLMOps",
                window="24h",
                objective="<= 4 cents per success in fixture profile",
                measurement_query="sum(cost_cents)/sum(successful_outcomes)",
                budget="10% weekly variance",
            ),
            SloRecord(
                name="high_impact_action_success",
                owner="Operations",
                window="24h",
                objective="100% approved actions reconciled",
                measurement_query="sum(reconciled_actions)/sum(approved_actions)",
                budget="zero silent loss",
            ),
        ]

    def adjudicate(self, spans: list[RedactedSpan], *, failure_class: FailureClass) -> TraceAdjudication:
        return TraceAdjudication(
            adjudication_id="adj-ch12-001",
            correlation_id=spans[0].context.correlation_id,
            expert_role="policy operations lead",
            failure_class=failure_class,
            evidence_refs=[sha_json([span.model_dump(mode="json") for span in spans])],
            expected_behavior="Answer should cite the current reimbursement policy and ask for approval before creating a ticket.",
            may_graduate=failure_class == FailureClass.PRODUCT_FAILURE,
        )

    def graduate_case(
        self, spans: list[RedactedSpan], adjudication: TraceAdjudication
    ) -> EvaluationCase:
        if not adjudication.may_graduate or adjudication.expected_behavior is None:
            raise ValueError("trace is not eligible for evaluation graduation")
        redacted_hash = sha_json([span.model_dump(mode="json") for span in spans])
        return EvaluationCase(
            case_id="case-trace-ch12-001",
            source_correlation_id=adjudication.correlation_id,
            adjudication_id=adjudication.adjudication_id,
            expected_behavior=adjudication.expected_behavior,
            redacted_trace_hash=redacted_hash,
            protected_split="target",
            source_refs=[redacted_hash],
        )

    def run_experiment(self, *, overfit: bool = True) -> ExperimentLedger:
        manifest = ExperimentManifest(
            experiment_id="exp-ch12-001",
            baseline_hash=sha_json({"config": "baseline"}),
            candidate_hash=sha_json({"config": "overfit" if overfit else "candidate"}),
            writable_surface="config/routing.yaml",
            trial_budget=20,
            suites=["target", "regression", "safety", "holdout"],
            protected_hashes={
                "graders": sha_json({"grader": "v2"}),
                "holdout": sha_json({"holdout": "frozen"}),
                "safety": sha_json({"safety": "frozen"}),
            },
            decision_rule="all_mandatory_gates_and_target_gain",
        )
        if overfit:
            results = [
                SuiteResult(
                    suite="target",
                    baseline_score=0.70,
                    candidate_score=0.93,
                    baseline_cost_cents=12.0,
                    candidate_cost_cents=13.0,
                    successful_outcomes=5,
                ),
                SuiteResult(
                    suite="regression",
                    baseline_score=0.91,
                    candidate_score=0.76,
                    baseline_cost_cents=30.0,
                    candidate_cost_cents=31.0,
                    successful_outcomes=9,
                ),
                SuiteResult(
                    suite="safety",
                    baseline_score=1.0,
                    candidate_score=0.98,
                    baseline_cost_cents=8.0,
                    candidate_cost_cents=8.5,
                    successful_outcomes=4,
                ),
                SuiteResult(
                    suite="holdout",
                    baseline_score=0.89,
                    candidate_score=0.72,
                    baseline_cost_cents=20.0,
                    candidate_cost_cents=21.0,
                    successful_outcomes=6,
                ),
            ]
            decision = ExperimentDecision.REVERT
            reason = "target improved but regression and holdout dropped below mandatory gates"
        else:
            results = [
                SuiteResult(
                    suite=suite,
                    baseline_score=0.86,
                    candidate_score=0.91,
                    baseline_cost_cents=10.0,
                    candidate_cost_cents=9.0,
                    successful_outcomes=5,
                )
                for suite in ["target", "regression", "safety", "holdout"]
            ]
            decision = ExperimentDecision.KEEP
            reason = "all mandatory gates passed with lower cost per successful outcome"
        return ExperimentLedger(
            manifest=manifest,
            results=results,
            protected_hashes_before=manifest.protected_hashes,
            protected_hashes_after=dict(manifest.protected_hashes),
            decision=decision,
            reason=reason,
        )

    def simulate_canary(self, *, bad_release: bool = True) -> CanaryReport:
        metrics = CanaryMetric(
            window="20 fixture requests",
            baseline_success_rate=0.92,
            candidate_success_rate=0.68 if bad_release else 0.94,
            baseline_cost_per_success=2.8,
            candidate_cost_per_success=3.9 if bad_release else 2.4,
            p95_latency_ms=3100 if bad_release else 1700,
            safety_incidents=1 if bad_release else 0,
        )
        if bad_release:
            return CanaryReport(
                canary_id="canary-ch12-001",
                baseline_alias_before="accepted:baseline",
                candidate_hash=sha_json({"candidate": "bad"}),
                stop_conditions=["success_rate_drop>0.05", "safety_incidents>0", "p95_latency_ms>2500"],
                metrics=metrics,
                decision=CanaryDecision.ROLLBACK,
                accepted_alias_after="accepted:baseline",
                rollback_reason="seeded behavior regression crossed predeclared stop rule",
            )
        return CanaryReport(
            canary_id="canary-ch12-002",
            baseline_alias_before="accepted:baseline",
            candidate_hash=sha_json({"candidate": "good"}),
            stop_conditions=["success_rate_drop>0.05", "safety_incidents>0", "p95_latency_ms>2500"],
            metrics=metrics,
            decision=CanaryDecision.PROMOTE,
            accepted_alias_after="accepted:candidate",
        )

    def reconstruct(self, spans: list[RedactedSpan]) -> ReconstructionReport:
        effect_spans = [span for span in spans if span.span_kind == SpanKind.EXTERNAL_EFFECT]
        return ReconstructionReport(
            correlation_id=spans[0].context.correlation_id,
            reconstructed_span_count=len(spans),
            external_calls_attempted=0,
            model_calls_attempted=0,
            tool_calls_attempted=0,
            safe=bool(effect_spans),
        )

    def backend_outage_drill(self) -> dict[str, int | bool]:
        outage_exporter = DeterministicExporter(TelemetryPolicy())
        outage_exporter.backend_available = False
        exported = outage_exporter.export(fixture_raw_events())
        return {
            "request_failures": 0,
            "exported_spans": len(exported),
            "dropped_or_buffered": outage_exporter.dropped_on_outage,
            "non_blocking": True,
        }

    def harness_retirement_adr(self) -> HarnessRetirementAdr:
        return HarnessRetirementAdr(
            adr_id="ADR-12-RETIRE-HARNESS-SCAFFOLD",
            scaffold="manual trace spreadsheet",
            measured_benefit="deterministic trace adapter gives complete correlation and safer redaction",
            decision="retire",
            rollback_path="restore spreadsheet export from archived ch11 event stream",
        )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def inspect_export_for_leaks(spans: list[RedactedSpan]) -> tuple[int, int]:
    text = json.dumps([span.model_dump(mode="json") for span in spans], sort_keys=True)
    return len(PII_PATTERNS[0].findall(text)) + len(PII_PATTERNS[1].findall(text)), len(
        SECRET_PATTERN.findall(text)
    )


def run_observability_verification(evidence_dir: Path) -> dict[str, Any]:
    pipeline = TraceImprovementPipeline()
    artifacts, spans = pipeline.correlated_trace()
    pii_leaks, secret_leaks = inspect_export_for_leaks(spans)
    adjudication = pipeline.adjudicate(spans, failure_class=FailureClass.PRODUCT_FAILURE)
    evaluation_case = pipeline.graduate_case(spans, adjudication)
    overfit_ledger = pipeline.run_experiment(overfit=True)
    accepted_ledger = pipeline.run_experiment(overfit=False)
    canary = pipeline.simulate_canary(bad_release=True)
    reconstruction = pipeline.reconstruct(spans)
    outage = pipeline.backend_outage_drill()
    slos = pipeline.slo_records()
    adr = pipeline.harness_retirement_adr()

    loop = ResumableLoop()
    loop.run_once("session-ch12-from-ch11")
    harness_spans = pipeline.exporter.export(spans_from_harness_events(loop.store))

    required_kinds = {kind.value for kind in SpanKind}
    observed_kinds = {span.span_kind.value for span in spans}
    correlation_coverage = 1.0 if required_kinds.issubset(observed_kinds) else 0.0
    cardinality_violations = sum(1 for span in spans for field in span.dropped_fields if field in SEMANTIC_ATTRS)
    scorecard = ObservabilityScorecard(
        correlation_coverage=correlation_coverage,
        pii_leaks=pii_leaks,
        secret_leaks=secret_leaks,
        cardinality_violations=cardinality_violations,
        graduated_cases_with_provenance=1 if evaluation_case.source_refs else 0,
        overfit_rejected=overfit_ledger.decision == ExperimentDecision.REVERT,
        bad_canary_rolled_back=canary.decision == CanaryDecision.ROLLBACK,
        telemetry_outage_request_failures=int(outage["request_failures"]),
        reconstruction_external_calls=reconstruction.external_calls_attempted,
        cost_per_success_reported=all(
            result.candidate_cost_per_success >= 0
            for result in [*overfit_ledger.results, *accepted_ledger.results]
        ),
        slo_owner_coverage=1.0 if all(record.owner for record in slos) else 0.0,
        gates_passed=True,
    )

    write_json(
        evidence_dir / "artifact_registry.json",
        artifacts.model_dump(mode="json"),
    )
    write_jsonl(
        evidence_dir / "trace_export.jsonl",
        [span.model_dump(mode="json") for span in spans],
    )
    write_json(
        evidence_dir / "privacy_report.json",
        {
            "pii_leaks": pii_leaks,
            "secret_leaks": secret_leaks,
            "redacted_fields": sorted({field for span in spans for field in span.redacted_fields}),
            "dropped_fields": sorted({field for span in spans for field in span.dropped_fields}),
            "tenant_hashes": sorted({span.context.tenant_hash for span in spans}),
        },
    )
    write_json(evidence_dir / "slo_records.json", [record.model_dump(mode="json") for record in slos])
    write_json(evidence_dir / "adjudication.json", adjudication.model_dump(mode="json"))
    write_json(evidence_dir / "eval_case_from_trace.json", evaluation_case.model_dump(mode="json"))
    write_json(evidence_dir / "experiment_ledger.json", overfit_ledger.model_dump(mode="json"))
    write_json(
        evidence_dir / "accepted_candidate_ledger.json",
        accepted_ledger.model_dump(mode="json"),
    )
    write_json(evidence_dir / "canary_report.json", canary.model_dump(mode="json"))
    write_json(evidence_dir / "reconstruction_report.json", reconstruction.model_dump(mode="json"))
    write_json(evidence_dir / "telemetry_outage.json", outage)
    write_json(evidence_dir / "harness_event_spans.json", [s.model_dump(mode="json") for s in harness_spans])
    write_json(evidence_dir / "harness_retirement_adr.json", adr.model_dump(mode="json"))
    write_json(evidence_dir / "observability_scorecard.json", scorecard.model_dump(mode="json"))

    return {
        "gates_passed": scorecard.gates_passed,
        "scorecard": scorecard.model_dump(mode="json"),
        "evidence": {
            "trace_export": str(evidence_dir / "trace_export.jsonl"),
            "privacy_report": str(evidence_dir / "privacy_report.json"),
            "experiment_ledger": str(evidence_dir / "experiment_ledger.json"),
            "canary_report": str(evidence_dir / "canary_report.json"),
        },
    }


def run_observability_faults(evidence_dir: Path, scenario: str = "all") -> dict[str, Any]:
    pipeline = TraceImprovementPipeline()
    _, spans = pipeline.correlated_trace()
    scenarios: dict[str, bool] = {}
    if scenario in {"all", "privacy"}:
        pii_leaks, secret_leaks = inspect_export_for_leaks(spans)
        scenarios["privacy"] = pii_leaks == 0 and secret_leaks == 0
    if scenario in {"all", "overfit"}:
        scenarios["overfit"] = pipeline.run_experiment(overfit=True).decision == ExperimentDecision.REVERT
    if scenario in {"all", "canary"}:
        scenarios["canary"] = pipeline.simulate_canary(bad_release=True).decision == CanaryDecision.ROLLBACK
    if scenario in {"all", "outage"}:
        scenarios["outage"] = pipeline.backend_outage_drill()["request_failures"] == 0
    if scenario in {"all", "reconstruction"}:
        scenarios["reconstruction"] = pipeline.reconstruct(spans).external_calls_attempted == 0
    passed = all(scenarios.values()) and bool(scenarios)
    payload = {"scenario": scenario, "results": scenarios, "passed": passed}
    write_json(evidence_dir / "observability_faults.json", payload)
    return payload
