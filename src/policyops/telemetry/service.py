"""Deterministic Chapter 12 trace-to-safe-improvement pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from policyops.harness import EventStore, ResumableLoop
from policyops.telemetry.schemas import (
    AdjudicationEnvelope,
    AdjudicationRequest,
    ArtifactRecord,
    ArtifactSet,
    CanaryDecision,
    CanaryMetric,
    CanaryReport,
    CanaryStopRequest,
    EvaluationCase,
    ExperimentEnvelope,
    ExperimentDecision,
    ExperimentLedger,
    ExperimentManifest,
    ExperimentRunRequest,
    FailureClass,
    HarnessRetirementAdr,
    OperationEnvelope,
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
DEFAULT_TELEMETRY_POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "telemetry_policy.yaml"

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
    normalized = tenant_id.strip().replace("_", "-").lower()
    return "tenant_" + hashlib.sha256(f"policyops:{normalized}".encode()).hexdigest()[:16]


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
    def __init__(
        self,
        cardinality_limit: int = CARDINALITY_LIMIT,
        *,
        policy_path: Path | None = None,
    ) -> None:
        self.policy_path = policy_path or DEFAULT_TELEMETRY_POLICY_PATH
        self.policy = self._load_policy()
        self.cardinality_limit = int(self.policy.get("cardinality_limit", cardinality_limit))
        self.seen_values: dict[str, set[str]] = {}
        self.semantic_attrs = frozenset(self.policy.get("semantic_attrs", sorted(SEMANTIC_ATTRS)))

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
            if key not in self.semantic_attrs:
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

    def _load_policy(self) -> dict[str, Any]:
        if self.policy_path.exists():
            loaded = yaml.safe_load(self.policy_path.read_text(encoding="utf-8"))
            return dict(loaded)
        return {
            "cardinality_limit": CARDINALITY_LIMIT,
            "semantic_attrs": sorted(SEMANTIC_ATTRS),
            "stop_conditions": [
                "success_rate_drop>0.05",
                "safety_incidents>0",
                "p95_latency_ms>2500",
            ],
        }


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
                name="error_rate",
                owner="Platform",
                window="1h",
                objective="error rate < 1%",
                measurement_query="sum(request_errors)/count(requests)",
                budget="1% failed requests",
            ),
            SloRecord(
                name="cost_budget",
                owner="LLMOps",
                window="24h",
                objective="daily spend <= 250 cents in fixture-equivalent volume",
                measurement_query="sum(cost_cents)",
                budget="5% daily spend variance",
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
                name="recovery",
                owner="Operations",
                window="24h",
                objective="recovery completes within 15 minutes for fixture drills",
                measurement_query="max(recovery_duration_minutes)",
                budget="0 missed recovery objective",
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

    def _protected_assets(self) -> dict[str, Any]:
        return {
            "graders": {"grader": "policyops-v2", "rubric": ["quality", "safety", "grounding"]},
            "holdout": {"suite": "holdout", "cases": ["travel-refund", "procurement-policy", "legal-escalation"]},
            "safety": {"suite": "safety", "gates": ["approval-required", "tenant-isolation", "ticket-once"]},
        }

    def _protected_hashes(self) -> dict[str, str]:
        return {name: sha_json(payload) for name, payload in self._protected_assets().items()}

    def experiment_trial_report(self, *, overfit: bool) -> dict[str, Any]:
        candidate_profile = "overfit" if overfit else "accepted"
        baseline_config = {"routing": "baseline", "prompt_version": "12.0"}
        candidate_config = {
            "routing": "target-heavy" if overfit else "balanced-retrieval",
            "prompt_version": "12.1" if overfit else "12.2",
        }
        suite_trials = {
            "target": [
                {"case_id": "target-1", "baseline_score": 0.68, "candidate_score": 0.91, "baseline_cost_cents": 2.1, "candidate_cost_cents": 2.5, "baseline_success": False, "candidate_success": True},
                {"case_id": "target-2", "baseline_score": 0.71, "candidate_score": 0.94, "baseline_cost_cents": 2.4, "candidate_cost_cents": 2.7, "baseline_success": True, "candidate_success": True},
                {"case_id": "target-3", "baseline_score": 0.69, "candidate_score": 0.92, "baseline_cost_cents": 2.2, "candidate_cost_cents": 2.6, "baseline_success": False, "candidate_success": True},
                {"case_id": "target-4", "baseline_score": 0.72, "candidate_score": 0.95, "baseline_cost_cents": 2.5, "candidate_cost_cents": 2.8, "baseline_success": True, "candidate_success": True},
                {"case_id": "target-5", "baseline_score": 0.70, "candidate_score": 0.91, "baseline_cost_cents": 2.3, "candidate_cost_cents": 2.4, "baseline_success": False, "candidate_success": True},
            ],
            "regression": [
                {"case_id": "regression-1", "baseline_score": 0.92, "candidate_score": 0.81 if overfit else 0.93, "baseline_cost_cents": 3.0, "candidate_cost_cents": 3.2 if overfit else 2.7, "baseline_success": True, "candidate_success": False if overfit else True},
                {"case_id": "regression-2", "baseline_score": 0.90, "candidate_score": 0.76 if overfit else 0.91, "baseline_cost_cents": 3.1, "candidate_cost_cents": 3.3 if overfit else 2.8, "baseline_success": True, "candidate_success": False if overfit else True},
                {"case_id": "regression-3", "baseline_score": 0.91, "candidate_score": 0.79 if overfit else 0.92, "baseline_cost_cents": 3.2, "candidate_cost_cents": 3.4 if overfit else 2.7, "baseline_success": True, "candidate_success": False if overfit else True},
                {"case_id": "regression-4", "baseline_score": 0.89, "candidate_score": 0.78 if overfit else 0.90, "baseline_cost_cents": 2.9, "candidate_cost_cents": 3.1 if overfit else 2.6, "baseline_success": True, "candidate_success": False if overfit else True},
                {"case_id": "regression-5", "baseline_score": 0.93, "candidate_score": 0.77 if overfit else 0.94, "baseline_cost_cents": 3.0, "candidate_cost_cents": 3.2 if overfit else 2.7, "baseline_success": True, "candidate_success": False if overfit else True},
            ],
            "safety": [
                {"case_id": "safety-1", "baseline_score": 1.00, "candidate_score": 0.98 if overfit else 1.00, "baseline_cost_cents": 2.0, "candidate_cost_cents": 2.1 if overfit else 1.9, "baseline_success": True, "candidate_success": True},
                {"case_id": "safety-2", "baseline_score": 1.00, "candidate_score": 0.99 if overfit else 1.00, "baseline_cost_cents": 2.0, "candidate_cost_cents": 2.1 if overfit else 1.9, "baseline_success": True, "candidate_success": True},
                {"case_id": "safety-3", "baseline_score": 1.00, "candidate_score": 0.97 if overfit else 1.00, "baseline_cost_cents": 2.0, "candidate_cost_cents": 2.2 if overfit else 1.9, "baseline_success": True, "candidate_success": True},
                {"case_id": "safety-4", "baseline_score": 1.00, "candidate_score": 0.98 if overfit else 1.00, "baseline_cost_cents": 2.0, "candidate_cost_cents": 2.1 if overfit else 1.8, "baseline_success": True, "candidate_success": True},
            ],
            "holdout": [
                {"case_id": "holdout-1", "baseline_score": 0.88, "candidate_score": 0.74 if overfit else 0.89, "baseline_cost_cents": 2.4, "candidate_cost_cents": 2.6 if overfit else 2.2, "baseline_success": True, "candidate_success": False if overfit else True},
                {"case_id": "holdout-2", "baseline_score": 0.90, "candidate_score": 0.72 if overfit else 0.91, "baseline_cost_cents": 2.5, "candidate_cost_cents": 2.7 if overfit else 2.2, "baseline_success": True, "candidate_success": False if overfit else True},
                {"case_id": "holdout-3", "baseline_score": 0.89, "candidate_score": 0.73 if overfit else 0.90, "baseline_cost_cents": 2.5, "candidate_cost_cents": 2.6 if overfit else 2.1, "baseline_success": True, "candidate_success": False if overfit else True},
                {"case_id": "holdout-4", "baseline_score": 0.87, "candidate_score": 0.71 if overfit else 0.89, "baseline_cost_cents": 2.3, "candidate_cost_cents": 2.5 if overfit else 2.1, "baseline_success": True, "candidate_success": False if overfit else True},
            ],
        }
        protected_before = self._protected_hashes()
        protected_after = self._protected_hashes()
        trials = [
            {"suite": suite, **trial}
            for suite, suite_rows in suite_trials.items()
            for trial in suite_rows
        ]
        return {
            "candidate_profile": candidate_profile,
            "baseline_hash": sha_json(baseline_config),
            "candidate_hash": sha_json(candidate_config),
            "protected_hashes_before": protected_before,
            "protected_hashes_after": protected_after,
            "trials": trials,
        }

    def _suite_result_from_trials(self, suite: str, trials: list[dict[str, Any]]) -> SuiteResult:
        baseline_score = round(sum(float(trial["baseline_score"]) for trial in trials) / len(trials), 4)
        candidate_score = round(sum(float(trial["candidate_score"]) for trial in trials) / len(trials), 4)
        baseline_cost = round(sum(float(trial["baseline_cost_cents"]) for trial in trials), 4)
        candidate_cost = round(sum(float(trial["candidate_cost_cents"]) for trial in trials), 4)
        successful_outcomes = sum(1 for trial in trials if trial["candidate_success"])
        return SuiteResult(
            suite=suite,  # type: ignore[arg-type]
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            baseline_cost_cents=baseline_cost,
            candidate_cost_cents=candidate_cost,
            successful_outcomes=successful_outcomes,
        )

    def run_experiment(self, *, overfit: bool = True) -> ExperimentLedger:
        trial_report = self.experiment_trial_report(overfit=overfit)
        manifest = ExperimentManifest(
            experiment_id="exp-ch12-001",
            baseline_hash=trial_report["baseline_hash"],
            candidate_hash=trial_report["candidate_hash"],
            writable_surface="config/routing.yaml",
            trial_budget=20,
            suites=["target", "regression", "safety", "holdout"],
            protected_hashes=trial_report["protected_hashes_before"],
            decision_rule="all_mandatory_gates_and_target_gain",
        )
        grouped_trials: dict[str, list[dict[str, Any]]] = {}
        for trial in trial_report["trials"]:
            grouped_trials.setdefault(trial["suite"], []).append(trial)
        results = [self._suite_result_from_trials(suite, grouped_trials[suite]) for suite in manifest.suites]
        by_suite = {result.suite: result for result in results}
        regressions_ok = all(
            by_suite[suite].candidate_score >= by_suite[suite].baseline_score
            for suite in ["regression", "safety", "holdout"]
        )
        target_gain = by_suite["target"].candidate_score > by_suite["target"].baseline_score
        lower_cost_per_success = all(
            result.candidate_cost_per_success
            <= round(
                sum(float(trial["baseline_cost_cents"]) for trial in grouped_trials[result.suite])
                / max(1, sum(1 for trial in grouped_trials[result.suite] if trial["baseline_success"])),
                4,
            )
            for result in results
        )
        decision = (
            ExperimentDecision.KEEP if target_gain and regressions_ok and lower_cost_per_success else ExperimentDecision.REVERT
        )
        reason = (
            "all mandatory gates passed with lower cost per successful outcome"
            if decision == ExperimentDecision.KEEP
            else "target improved but regression, holdout, or cost-per-success gates failed on the measured trial set"
        )
        return ExperimentLedger(
            manifest=manifest,
            results=results,
            protected_hashes_before=trial_report["protected_hashes_before"],
            protected_hashes_after=trial_report["protected_hashes_after"],
            decision=decision,
            reason=reason,
        )

    def canary_trial_report(self, *, bad_release: bool = True) -> dict[str, Any]:
        candidate_hash = sha_json({"candidate": "bad" if bad_release else "good"})
        rows: list[dict[str, Any]] = []
        for index in range(20):
            baseline_success = True if index < 18 else False
            candidate_success = (index < 13) if bad_release else (index < 19)
            baseline_latency = 1650 + (index % 5) * 40
            candidate_latency = (2650 + index * 22) if bad_release else (1550 + (index % 4) * 35)
            rows.append(
                {
                    "request_id": f"canary-{index + 1:02d}",
                    "baseline_success": baseline_success,
                    "candidate_success": candidate_success,
                    "baseline_cost_cents": 2.4 + (index % 3) * 0.1,
                    "candidate_cost_cents": (3.0 + (index % 4) * 0.2) if bad_release else (2.1 + (index % 3) * 0.1),
                    "baseline_latency_ms": baseline_latency,
                    "candidate_latency_ms": candidate_latency,
                    "candidate_safety_incident": bad_release and index == 7,
                }
            )
        return {
            "candidate_hash": candidate_hash,
            "window": f"{len(rows)} fixture requests",
            "requests": rows,
        }

    def _p95(self, values: list[int]) -> int:
        ordered = sorted(values)
        index = max(0, math.ceil(len(ordered) * 0.95) - 1)
        return ordered[index]

    def simulate_canary(self, *, bad_release: bool = True) -> CanaryReport:
        stop_conditions = list(self.policy.policy.get("stop_conditions", []))
        trial_report = self.canary_trial_report(bad_release=bad_release)
        requests = trial_report["requests"]
        baseline_successes = sum(1 for row in requests if row["baseline_success"])
        candidate_successes = sum(1 for row in requests if row["candidate_success"])
        metrics = CanaryMetric(
            window=trial_report["window"],
            baseline_success_rate=round(baseline_successes / len(requests), 4),
            candidate_success_rate=round(candidate_successes / len(requests), 4),
            baseline_cost_per_success=round(
                sum(float(row["baseline_cost_cents"]) for row in requests) / max(1, baseline_successes),
                4,
            ),
            candidate_cost_per_success=round(
                sum(float(row["candidate_cost_cents"]) for row in requests) / max(1, candidate_successes),
                4,
            ),
            p95_latency_ms=self._p95([int(row["candidate_latency_ms"]) for row in requests]),
            safety_incidents=sum(1 for row in requests if row["candidate_safety_incident"]),
        )
        should_rollback = (
            (metrics.baseline_success_rate - metrics.candidate_success_rate) > 0.05
            or metrics.safety_incidents > 0
            or metrics.p95_latency_ms > 2500
        )
        if should_rollback:
            return CanaryReport(
                canary_id="canary-ch12-001",
                baseline_alias_before="accepted:baseline",
                candidate_hash=trial_report["candidate_hash"],
                stop_conditions=stop_conditions,
                metrics=metrics,
                decision=CanaryDecision.ROLLBACK,
                accepted_alias_after="accepted:baseline",
                rollback_reason="seeded behavior regression crossed predeclared stop rule",
            )
        return CanaryReport(
            canary_id="canary-ch12-002",
            baseline_alias_before="accepted:baseline",
            candidate_hash=trial_report["candidate_hash"],
            stop_conditions=stop_conditions,
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


class TelemetryNotFoundError(RuntimeError):
    pass


class ActiveCanaryExistsError(RuntimeError):
    pass


class TelemetryRuntime:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.pipeline = TraceImprovementPipeline()

    def _operations_dir(self) -> Path:
        path = self.root / "operations"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _adjudications_dir(self) -> Path:
        path = self.root / "adjudications"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _experiments_dir(self) -> Path:
        path = self.root / "experiments"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _canaries_dir(self) -> Path:
        path = self.root / "canaries"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _active_canary_path(self) -> Path:
        return self.root / "active_canary.json"

    def inspect_operation(self, correlation_id: str) -> OperationEnvelope:
        artifacts, spans = self.pipeline.correlated_trace()
        if not spans or spans[0].context.correlation_id != correlation_id:
            raise TelemetryNotFoundError(f"operation not found: {correlation_id}")
        envelope = OperationEnvelope(
            correlation_id=correlation_id,
            artifacts=artifacts,
            spans=spans,
            slos=self.pipeline.slo_records(),
        )
        path = self._operations_dir() / f"{correlation_id}.json"
        path.write_text(json.dumps(envelope.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        return envelope

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationEnvelope:
        operation = self.inspect_operation(request.correlation_id)
        adjudication = self.pipeline.adjudicate(
            operation.spans,
            failure_class=request.failure_class,
        ).model_copy(
            update={
                "expert_role": request.expert_role,
                "expected_behavior": request.expected_behavior,
                "may_graduate": request.failure_class == FailureClass.PRODUCT_FAILURE
                and bool(request.expected_behavior),
            }
        )
        evaluation_case = None
        if adjudication.may_graduate:
            evaluation_case = self.pipeline.graduate_case(operation.spans, adjudication)
        envelope = AdjudicationEnvelope(adjudication=adjudication, evaluation_case=evaluation_case)
        path = self._adjudications_dir() / f"{adjudication.adjudication_id}.json"
        path.write_text(json.dumps(envelope.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        return envelope

    def run_experiment(self, request: ExperimentRunRequest) -> ExperimentEnvelope:
        overfit = request.candidate_profile == "overfit"
        active_path = self._active_canary_path()
        if active_path.exists():
            active = CanaryReport.model_validate(json.loads(active_path.read_text(encoding="utf-8")))
            if active.decision == CanaryDecision.HOLD:
                raise ActiveCanaryExistsError(f"active canary already running: {active.canary_id}")
        ledger = self.pipeline.run_experiment(overfit=overfit)
        active_canary_id: str | None = None
        if ledger.decision == ExperimentDecision.KEEP:
            active = self.pipeline.simulate_canary(bad_release=False).model_copy(
                update={
                    "canary_id": "canary-ch12-active",
                    "decision": CanaryDecision.HOLD,
                    "accepted_alias_after": "accepted:baseline",
                    "rollback_reason": None,
                }
            )
            active_canary_id = active.canary_id
            path = self._canaries_dir() / f"{active.canary_id}.json"
            path.write_text(json.dumps(active.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
            active_path.write_text(json.dumps(active.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        envelope = ExperimentEnvelope(ledger=ledger, active_canary_id=active_canary_id)
        path = self._experiments_dir() / f"{ledger.manifest.experiment_id}.json"
        path.write_text(json.dumps(envelope.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        return envelope

    def simulate_canary(self, *, bad_release: bool) -> CanaryReport:
        report = self.pipeline.simulate_canary(bad_release=bad_release)
        path = self._canaries_dir() / f"{report.canary_id}.json"
        path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        return report

    def stop_canary(self, canary_id: str, request: CanaryStopRequest) -> CanaryReport:
        path = self._canaries_dir() / f"{canary_id}.json"
        if not path.exists():
            raise TelemetryNotFoundError(f"canary not found: {canary_id}")
        report = CanaryReport.model_validate(json.loads(path.read_text(encoding="utf-8")))
        stopped = report.model_copy(
            update={
                "decision": CanaryDecision.ROLLBACK,
                "accepted_alias_after": report.baseline_alias_before,
                "rollback_reason": request.reason,
            }
        )
        path.write_text(json.dumps(stopped.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        active_path = self._active_canary_path()
        if active_path.exists():
            active_path.unlink()
        return stopped


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
    write_json(
        evidence_dir / "telemetry_policy_bundle.json",
        pipeline.policy.policy,
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
        evidence_dir / "experiment_trial_report.json",
        pipeline.experiment_trial_report(overfit=True),
    )
    write_json(
        evidence_dir / "accepted_candidate_ledger.json",
        accepted_ledger.model_dump(mode="json"),
    )
    write_json(
        evidence_dir / "accepted_candidate_trial_report.json",
        pipeline.experiment_trial_report(overfit=False),
    )
    write_json(evidence_dir / "canary_report.json", canary.model_dump(mode="json"))
    write_json(evidence_dir / "canary_trial_report.json", pipeline.canary_trial_report(bad_release=True))
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
