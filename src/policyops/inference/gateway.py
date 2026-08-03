"""Deterministic adaptive inference gateway for the Chapter 4 lab."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from policyops.contracts import (
    Answer,
    Citation,
    ErrorCode,
    ModelFailure,
    ModelFailureResult,
    ModelRequest,
    ModelResult,
    ModelSuccess,
    RetryClass,
    RunContext,
    Usage,
)
from policyops.inference.schemas import (
    BenchmarkReport,
    BenchmarkRow,
    CacheEntry,
    CacheKey,
    CandidateResult,
    FailureReason,
    GatewayResult,
    InferenceBudget,
    InferenceRequest,
    ModelProfile,
    ReasoningEffort,
    RiskTier,
    TaskClass,
    VerificationResult,
)
from policyops.util import canonical_json


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def fixture_profiles() -> dict[str, ModelProfile]:
    return {
        "small-fast": ModelProfile(
            profile_id="small-fast", quality=0.82, latency_ms=45, cost_per_1k_tokens=0.25
        ),
        "standard": ModelProfile(
            profile_id="standard", quality=0.84, latency_ms=90, cost_per_1k_tokens=0.75
        ),
        "reasoned": ModelProfile(
            profile_id="reasoned", quality=0.93, latency_ms=160, cost_per_1k_tokens=1.80
        ),
        "quantized-small": ModelProfile(
            profile_id="quantized-small",
            quality=0.72,
            latency_ms=30,
            cost_per_1k_tokens=0.12,
            quantized=True,
        ),
        "draft-reasoned": ModelProfile(
            profile_id="draft-reasoned",
            quality=0.91,
            latency_ms=105,
            cost_per_1k_tokens=1.10,
            draft_profile_id="small-fast",
        ),
    }


class GatewayClock:
    """Tiny fake clock so timeout, TTL, and replay behavior are deterministic."""

    def __init__(self) -> None:
        self.now_ms = 0

    def advance(self, duration_ms: int) -> None:
        self.now_ms += max(0, duration_ms)


class ResponseCache:
    """In-memory response cache with complete-key validation."""

    def __init__(self, ttl_ms: int = 300_000) -> None:
        self.ttl_ms = ttl_ms
        self._entries: dict[str, CacheEntry] = {}

    @staticmethod
    def identity(key: CacheKey) -> str:
        return _sha(canonical_json(key.model_dump(mode="json")))

    def get(self, key: CacheKey, now_ms: int) -> tuple[CacheEntry | None, str]:
        entry = self._entries.get(self.identity(key))
        if entry is None:
            return None, "miss"
        if (
            entry.key != key
            or entry.expires_ms <= now_ms
            or not entry.candidate.valid
            or entry.validator_version != "verifier-v1"
        ):
            self._entries.pop(self.identity(key), None)
            return None, "rejected"
        return entry, "hit"

    def put(self, key: CacheKey, candidate: CandidateResult, now_ms: int) -> None:
        if not candidate.valid:
            return
        self._entries[self.identity(key)] = CacheEntry(
            key=key,
            candidate=candidate.model_copy(update={"cache_hit": False}),
            created_ms=now_ms,
            expires_ms=now_ms + self.ttl_ms,
        )

    def inject(self, entry: CacheEntry) -> None:
        self._entries[self.identity(entry.key)] = entry


class BudgetLedger:
    def __init__(self, budget: InferenceBudget) -> None:
        self.budget = budget
        self.duration_ms = 0
        self.spend_units = 0.0
        self.candidates = 0

    def can_attempt(self, profile: ModelProfile, estimate_tokens: int) -> bool:
        projected_spend = self.spend_units + _cost_units(profile, estimate_tokens)
        return (
            self.candidates < self.budget.max_candidates
            and self.duration_ms + profile.latency_ms <= self.budget.max_duration_ms
            and projected_spend <= self.budget.max_spend_units
        )

    def commit(self, profile: ModelProfile, tokens: int) -> tuple[int, float]:
        self.candidates += 1
        spend = _cost_units(profile, tokens)
        self.spend_units += spend
        self.duration_ms += profile.latency_ms
        return profile.latency_ms, spend


def _cost_units(profile: ModelProfile, tokens: int) -> float:
    return round(profile.cost_per_1k_tokens * tokens / 1000, 4)


class AdaptiveInferenceGateway:
    """A fixture gateway that demonstrates bounded test-time compute."""

    def __init__(
        self,
        *,
        profiles: dict[str, ModelProfile] | None = None,
        cache: ResponseCache | None = None,
        clock: GatewayClock | None = None,
    ) -> None:
        self.profiles = profiles or fixture_profiles()
        self.cache = cache or ResponseCache()
        self.clock = clock or GatewayClock()

    async def ready(self) -> bool:
        return True

    async def generate(self, request: ModelRequest, context: RunContext) -> ModelResult:
        """Implement the Chapter 1 ModelClient port with gateway metadata in usage.adapter."""
        inference_request = InferenceRequest(
            request_id=context.request_id,
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            authorization_fingerprint=_sha(
                canonical_json(context.authorization_context.model_dump(mode="json"))
            ),
            configuration_hash=context.configuration_id,
            policy_version=request.policy_version or context.configuration_versions.get(
                "policy", "policy-v1"
            ),
            question=request.question,
            risk_tier=RiskTier.HIGH if context.data_classification == "confidential" else RiskTier.MEDIUM,
            data_classification=context.data_classification,
            budget=InferenceBudget(
                max_input_tokens=context.budget.max_input_tokens,
                max_output_tokens=context.budget.max_output_tokens,
                max_duration_ms=5000,
                max_spend_units=25,
                max_candidates=3,
                min_quality=0.8,
            ),
        )
        gateway_result = self.run(inference_request)
        if gateway_result.selected is None:
            code = (
                ErrorCode.DEADLINE_EXCEEDED
                if gateway_result.failure_reason == FailureReason.DEADLINE_EXCEEDED
                else ErrorCode.MODEL_BAD_OUTPUT
            )
            return ModelFailureResult(
                failure=ModelFailure(
                    code=code,
                    retry_class=RetryClass.UPSTREAM,
                    message=gateway_result.failure_reason.value,
                    correlation_token=context.trace_id,
                )
            )
        selected = gateway_result.selected
        citation = Citation(
            source_id="policy-handbook",
            title="PolicyOps fixture handbook",
            locator=f"{inference_request.policy_version}#remote-work",
            excerpt=selected.citations[0] if selected.citations else "fixture citation",
        )
        return ModelSuccess(
            answer=Answer(text=selected.text, citations=[citation]),
            usage=Usage(
                input_tokens=min(context.budget.max_input_tokens, 128),
                output_tokens=min(context.budget.max_output_tokens, 96),
                adapter=f"gateway:{selected.profile_id}:{gateway_result.cache_status}",
            ),
        )

    def run(self, request: InferenceRequest) -> GatewayResult:
        ledger = BudgetLedger(request.budget)
        route = self.plan_route(request)
        cache_status = "bypass"
        if request.cacheable and request.data_classification != "confidential":
            key = self.cache_key(request, route[0])
            cache_entry, cache_status = self.cache.get(key, self.clock.now_ms)
            if cache_entry:
                cached = cache_entry.candidate.model_copy(update={"cache_hit": True})
                cached_verification = self.verify_cached_candidate(cached, request)
                if not cached_verification.passed:
                    self.cache._entries.pop(self.cache.identity(key), None)
                    cache_status = "rejected"
                else:
                    cached = cached.model_copy(
                        update={
                            "valid": True,
                            "quality_score": cached_verification.quality_score,
                            "verifier_reasons": cached_verification.reasons,
                        }
                    )
                if cache_status == "hit":
                    return GatewayResult(
                        request_id=request.request_id,
                        selected=cached,
                        candidates=[cached],
                        route=[route[0], "cache-hit"],
                    cache_status="hit",
                    early_exit=True,
                    duration_ms=1,
                    spend_units=0.0,
                )
        elif request.data_classification == "confidential":
            cache_status = "bypass"

        candidates: list[CandidateResult] = []
        estimate_tokens = min(request.budget.max_input_tokens + request.budget.max_output_tokens, 1200)
        for index, profile_id in enumerate(route):
            profile = self.profiles[profile_id]
            if not ledger.can_attempt(profile, estimate_tokens):
                failure = (
                    FailureReason.DEADLINE_EXCEEDED
                    if ledger.duration_ms + profile.latency_ms > request.budget.max_duration_ms
                    else FailureReason.BUDGET_EXHAUSTED
                )
                return GatewayResult(
                    request_id=request.request_id,
                    candidates=candidates,
                    route=route[: index + 1],
                    cache_status=cache_status,
                    duration_ms=ledger.duration_ms,
                    spend_units=ledger.spend_units,
                    budget_exhausted=failure == FailureReason.BUDGET_EXHAUSTED,
                    failure_reason=failure,
                )
            latency_ms, spend = ledger.commit(profile, estimate_tokens)
            self.clock.advance(latency_ms)
            verification = self.verify(profile, request)
            candidate = CandidateResult(
                candidate_id=f"{request.request_id}:{index + 1}",
                profile_id=profile.profile_id,
                text=self._answer_text(profile, request),
                citations=self._citations(profile, request),
                quality_score=verification.quality_score,
                latency_ms=latency_ms,
                cost_units=spend,
                valid=verification.passed,
                verifier_reasons=verification.reasons,
                reasoning_effort=self.reasoning_effort(request, profile),
            )
            candidates.append(candidate)
            if candidate.valid:
                if (
                    request.cacheable
                    and request.data_classification != "confidential"
                    and cache_status != "bypass"
                ):
                    self.cache.put(self.cache_key(request, route[0]), candidate, self.clock.now_ms)
                return GatewayResult(
                    request_id=request.request_id,
                    selected=candidate,
                    candidates=candidates,
                    route=route[: index + 1],
                    cache_status=cache_status,
                    early_exit=True,
                    duration_ms=ledger.duration_ms,
                    spend_units=ledger.spend_units,
                )

        return GatewayResult(
            request_id=request.request_id,
            candidates=candidates,
            route=route,
            cache_status=cache_status,
            duration_ms=ledger.duration_ms,
            spend_units=ledger.spend_units,
            failure_reason=FailureReason.NO_VERIFIED_CANDIDATE,
        )

    def plan_route(self, request: InferenceRequest) -> list[str]:
        if request.risk_tier == RiskTier.HIGH or request.task_class == TaskClass.CONTROLLED_ACTION:
            return ["standard", "reasoned", "draft-reasoned"][: request.budget.max_candidates]
        if "ambiguous" in request.question.lower() or "exception" in request.question.lower():
            return ["small-fast", "standard", "reasoned"][: request.budget.max_candidates]
        if request.task_class == TaskClass.CLASSIFICATION:
            return ["quantized-small", "small-fast", "standard"][: request.budget.max_candidates]
        return ["small-fast", "standard", "reasoned"][: request.budget.max_candidates]

    def cache_key(self, request: InferenceRequest, first_profile_id: str) -> CacheKey:
        canonical_request = {
            "question": " ".join(request.question.lower().split()),
            "task_class": request.task_class.value,
            "risk_tier": request.risk_tier.value,
            "require_citations": request.require_citations,
        }
        return CacheKey(
            tenant_hash=_sha(request.tenant_id),
            authorization_hash=_sha(request.authorization_fingerprint),
            semantic_request_hash=_sha(canonical_json(canonical_request)),
            model_profile=f"{first_profile_id}@{request.configuration_hash}",
            configuration_hash=request.configuration_hash,
            policy_hash=_sha(request.policy_version),
            source_freshness=request.source_freshness,
        )

    def reasoning_effort(
        self, request: InferenceRequest, profile: ModelProfile
    ) -> ReasoningEffort:
        if profile.profile_id in {"reasoned", "draft-reasoned"} or request.risk_tier == RiskTier.HIGH:
            return ReasoningEffort.HIGH
        if profile.profile_id == "standard" or request.risk_tier == RiskTier.MEDIUM:
            return ReasoningEffort.MEDIUM
        return ReasoningEffort.LOW

    def verify(self, profile: ModelProfile, request: InferenceRequest) -> VerificationResult:
        quality = profile.quality
        reasons: list[str] = []
        if request.risk_tier == RiskTier.HIGH and profile.profile_id in {
            "small-fast",
            "quantized-small",
        }:
            quality -= 0.08
            reasons.append("high_risk_requires_stronger_profile")
        if "ambiguous" in request.question.lower() and profile.profile_id in {
            "small-fast",
            "quantized-small",
        }:
            quality -= 0.10
            reasons.append("ambiguous_question_failed_small_profile")
        citations = self._citations(profile, request)
        if request.require_citations and not citations:
            reasons.append("missing_required_citation")
        if "unsafe" in request.question.lower():
            reasons.append("semantic_guard_failed")
        passed = quality >= request.budget.min_quality and not any(
            r in reasons for r in ["missing_required_citation", "semantic_guard_failed"]
        )
        if passed:
            reasons.append("verified")
        return VerificationResult(
            passed=passed,
            quality_score=max(0.0, min(1.0, round(quality, 3))),
            reasons=reasons,
        )

    def verify_cached_candidate(
        self, candidate: CandidateResult, request: InferenceRequest
    ) -> VerificationResult:
        profile = self.profiles.get(candidate.profile_id)
        if profile is None:
            return VerificationResult(
                passed=False,
                quality_score=0.0,
                reasons=["unknown_cached_profile"],
            )
        verification = self.verify(profile, request)
        if request.require_citations and not candidate.citations:
            return VerificationResult(
                passed=False,
                quality_score=verification.quality_score,
                reasons=[*verification.reasons, "missing_required_citation"],
            )
        return verification

    def _citations(self, profile: ModelProfile, request: InferenceRequest) -> list[str]:
        if not request.require_citations:
            return []
        if profile.profile_id == "small-fast" and (
            request.risk_tier == RiskTier.HIGH or "ambiguous" in request.question.lower()
        ):
            return []
        return [f"{request.policy_version}:policy-handbook#remote-work"]

    def _answer_text(self, profile: ModelProfile, request: InferenceRequest) -> str:
        return (
            f"{profile.profile_id} answered '{request.question}' using "
            f"{self.reasoning_effort(request, profile).value} reasoning."
        )


def _workload() -> list[InferenceRequest]:
    base = {
        "tenant_id": "tenant_alpha",
        "actor_id": "actor_reader",
        "authorization_fingerprint": "authz:reader",
        "configuration_hash": "sha256:gateway-fixture",
        "policy_version": "policy-v1",
    }
    return [
        InferenceRequest(request_id="ch04-easy", question="How many remote days?", **base),
        InferenceRequest(
            request_id="ch04-ambiguous",
            question="Ambiguous exception for remote work approval?",
            risk_tier=RiskTier.MEDIUM,
            **base,
        ),
        InferenceRequest(
            request_id="ch04-high-risk",
            question="Can I approve a confidential payroll policy exception?",
            risk_tier=RiskTier.HIGH,
            data_classification="confidential",
            **base,
        ),
        InferenceRequest(
            request_id="ch04-classify",
            question="Classify this policy ticket.",
            task_class=TaskClass.CLASSIFICATION,
            require_citations=False,
            **base,
        ),
    ]


def _dominance(rows: list[BenchmarkRow]) -> list[BenchmarkRow]:
    updated: list[BenchmarkRow] = []
    for row in rows:
        dominated = False
        for other in rows:
            if row.profile == other.profile:
                continue
            if (
                other.quality >= row.quality
                and other.latency_ms <= row.latency_ms
                and other.spend_units <= row.spend_units
                and (
                    other.quality > row.quality
                    or other.latency_ms < row.latency_ms
                    or other.spend_units < row.spend_units
                )
            ):
                dominated = True
                break
        updated.append(row.model_copy(update={"dominated": dominated}))
    return updated


def benchmark_gateway(evidence_dir: Path | None = None) -> BenchmarkReport:
    rows: list[BenchmarkRow] = []
    quality_floor = 0.80
    for profile_name, cache_state in [
        ("direct-small", "bypass"),
        ("routed-cold", "cold"),
        ("routed-warm", "warm"),
        ("quantized", "bypass"),
        ("speculative", "bypass"),
    ]:
        cache = ResponseCache()
        gateway = AdaptiveInferenceGateway(cache=cache)
        if profile_name == "direct-small":
            gateway.plan_route = lambda request: ["small-fast"]  # type: ignore[method-assign]
        elif profile_name == "quantized":
            gateway.plan_route = lambda request: ["quantized-small", "standard"]  # type: ignore[method-assign]
        elif profile_name == "speculative":
            gateway.plan_route = lambda request: ["draft-reasoned"]  # type: ignore[method-assign]

        for request in _workload():
            if cache_state == "warm":
                gateway.run(request)
            result = gateway.run(request)
            selected = result.selected
            success = selected is not None and selected.valid and selected.quality_score >= quality_floor
            spend = result.spend_units
            rows.append(
                BenchmarkRow(
                    request_id=request.request_id,
                    profile=profile_name,
                    cache_state=cache_state,
                    success=success,
                    quality=selected.quality_score if selected else 0.0,
                    latency_ms=result.duration_ms,
                    spend_units=spend,
                    cost_per_successful_outcome=round(spend, 4) if success else None,
                    selected_profile=selected.profile_id if selected else None,
                )
            )
    rows = _dominance(rows)
    grouped: dict[str, list[BenchmarkRow]] = {}
    for row in rows:
        grouped.setdefault(row.profile, []).append(row)
    profile_scores: list[tuple[str, float, int, float, bool]] = []
    for profile, profile_rows in grouped.items():
        success_rows = [row for row in profile_rows if row.success]
        success_rate = len(success_rows) / len(profile_rows)
        avg_quality = sum(row.quality for row in profile_rows) / len(profile_rows)
        avg_latency = int(sum(row.latency_ms for row in profile_rows) / len(profile_rows))
        total_spend = round(sum(row.spend_units for row in profile_rows), 4)
        clears_floor = success_rate >= 1.0 and avg_quality >= quality_floor
        profile_scores.append((profile, avg_quality, avg_latency, total_spend, clears_floor))
    eligible = [score for score in profile_scores if score[4]]
    selected_profile = sorted(eligible, key=lambda s: (s[3], s[2], -s[1]))[0][0]
    pareto_profiles = sorted({row.profile for row in rows if not row.dominated})
    report = BenchmarkReport(
        workload_id="ch04-fixture-v1",
        quality_floor=quality_floor,
        rows=rows,
        selected_profile=selected_profile,
        pareto_profiles=pareto_profiles,
    )
    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "benchmark_rows.jsonl").write_text(
            "\n".join(row.model_dump_json() for row in rows) + "\n",
            encoding="utf-8",
        )
        (evidence_dir / "inference_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        adr = {
            "decision": "Use the routed fixture profile for the mandatory lab gate.",
            "selected_profile": selected_profile,
            "quality_floor": quality_floor,
            "note": "Fixture latency and spend are replay evidence, not provider benchmarks.",
        }
        (evidence_dir / "serving_adr.json").write_text(json.dumps(adr, indent=2), encoding="utf-8")
    return report


def run_gateway_verification(evidence_dir: Path) -> dict[str, Any]:
    report = benchmark_gateway(evidence_dir)
    selected_rows = [row for row in report.rows if row.profile == report.selected_profile]
    passed = bool(selected_rows) and all(row.success for row in selected_rows)
    payload = {
        "passed": passed,
        "selected_profile": report.selected_profile,
        "pareto_profiles": report.pareto_profiles,
        "quality_floor": report.quality_floor,
    }
    (evidence_dir / "gateway_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
