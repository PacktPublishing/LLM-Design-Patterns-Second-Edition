"""Deterministic adaptive inference gateway for the Chapter 4 lab."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
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
from policyops.inference import route_policy
from policyops.inference.fixtures import load_gateway_workload
from policyops.inference.route_policy import RouteProfile
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
    MatchedPairComparison,
    MatchedPairOutcome,
    ModelProfile,
    ProfileAggregate,
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


def hard_gate(request: InferenceRequest, citations: list[str] | None = None) -> VerificationResult:
    """Deterministic, non-recoverable checks: authorization, schema/safety, and citation
    integrity. These run BEFORE any model-based profile selection (authorization and the
    semantic guard need no candidate at all) and again per-candidate once citations exist
    (citation integrity). A hard-gate failure STOPS the request outright: it is never
    recoverable and never escalates to another model.
    """
    reasons: list[str] = []
    if not request.authorized:
        reasons.append("authorization_denied")
    if "unsafe" in request.question.lower():
        reasons.append("semantic_guard_failed")
    if citations:
        allowed_prefix = f"{request.policy_version}:"
        if any(not citation.startswith(allowed_prefix) for citation in citations):
            reasons.append("fabricated_citation")
    passed = not reasons
    return VerificationResult(
        passed=passed,
        quality_score=1.0 if passed else 0.0,
        reasons=reasons or ["hard_gate_passed"],
        gate="hard",
        recoverable=False,
    )


def quality_gate(
    profile: ModelProfile, request: InferenceRequest, citations: list[str]
) -> VerificationResult:
    """Evidence-alignment and escalation checks. A quality-gate failure MAY escalate to the
    next model in the route sequence if budget remains — unlike a hard-gate failure.
    """
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
    if request.require_citations and not citations:
        reasons.append("missing_required_citation")
    passed = quality >= request.budget.min_quality and "missing_required_citation" not in reasons
    if passed:
        reasons.append("verified")
    return VerificationResult(
        passed=passed,
        quality_score=max(0.0, min(1.0, round(quality, 3))),
        reasons=reasons,
        gate="quality",
        recoverable=True,
    )


class AdaptiveInferenceGateway:
    """A fixture gateway that demonstrates bounded test-time compute."""

    def __init__(
        self,
        *,
        profiles: dict[str, ModelProfile] | None = None,
        cache: ResponseCache | None = None,
        clock: GatewayClock | None = None,
        route_profiles: dict[str, RouteProfile] | None = None,
        forced_route: list[str] | None = None,
    ) -> None:
        self.profiles = profiles or fixture_profiles()
        self.cache = cache or ResponseCache()
        self.clock = clock or GatewayClock()
        self.route_profiles = route_profiles or route_policy.route_profiles()
        # Supported way to pin a specific route without monkeypatching `plan_route`.
        self.forced_route = list(forced_route) if forced_route is not None else None

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
            authorized=bool(context.authorization_context.scopes),
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
            if gateway_result.failure_reason == FailureReason.DEADLINE_EXCEEDED:
                code = ErrorCode.DEADLINE_EXCEEDED
            elif gateway_result.failure_reason == FailureReason.AUTHORIZATION_DENIED:
                code = ErrorCode.FORBIDDEN
            else:
                code = ErrorCode.MODEL_BAD_OUTPUT
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
        # Deterministic rejection checks run BEFORE any model-based selection: authorization
        # and the semantic safety guard need no candidate and no route at all. A failure here
        # is non-recoverable, so no model is ever invoked for a denied request.
        preflight = hard_gate(request)
        if not preflight.passed:
            reason = (
                FailureReason.AUTHORIZATION_DENIED
                if "authorization_denied" in preflight.reasons
                else FailureReason.HARD_GATE_FAILED
            )
            return GatewayResult(
                request_id=request.request_id,
                candidates=[],
                route=[],
                cache_status="bypass",
                duration_ms=0,
                spend_units=0.0,
                failure_reason=reason,
            )

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
            if not verification.recoverable:
                # Hard-gate failure on this candidate's output: stop outright, never escalate.
                return GatewayResult(
                    request_id=request.request_id,
                    candidates=candidates,
                    route=route[: index + 1],
                    cache_status=cache_status,
                    duration_ms=ledger.duration_ms,
                    spend_units=ledger.spend_units,
                    failure_reason=FailureReason.HARD_GATE_FAILED,
                )
            # Recoverable quality-gate failure: fall through to escalate to the next profile.

        return GatewayResult(
            request_id=request.request_id,
            candidates=candidates,
            route=route,
            cache_status=cache_status,
            duration_ms=ledger.duration_ms,
            spend_units=ledger.spend_units,
            failure_reason=FailureReason.NO_VERIFIED_CANDIDATE,
        )

    def select_route_profile(self, request: InferenceRequest) -> RouteProfile:
        """Select a named RouteProfile for this request (Change 1 — route profiles as data)."""
        if request.risk_tier == RiskTier.HIGH or request.task_class == TaskClass.CONTROLLED_ACTION:
            return self.route_profiles["enhanced-with-candidates"]
        if request.task_class == TaskClass.CLASSIFICATION:
            return self.route_profiles["direct-baseline"]
        return self.route_profiles["routed-with-escalation"]

    def plan_route(self, request: InferenceRequest) -> list[str]:
        if self.forced_route is not None:
            return list(self.forced_route)
        profile = self.select_route_profile(request)
        limit = min(request.budget.max_candidates, profile.max_candidates)
        return list(profile.model_sequence[:limit])

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
        """Run the hard gate, then (if it passes) the quality gate, for one candidate.

        Change 2: verification is split into `hard_gate` (schema, citation integrity,
        authorization — non-recoverable) and `quality_gate` (evidence alignment and
        escalation triggers — recoverable). This method is the composition point the rest of
        the gateway calls; `run()` inspects `VerificationResult.recoverable` to decide whether
        to stop outright or escalate to the next profile in the route.
        """
        citations = self._citations(profile, request)
        hard = hard_gate(request, citations)
        if not hard.passed:
            return hard
        return quality_gate(profile, request, citations)

    def verify_cached_candidate(
        self, candidate: CandidateResult, request: InferenceRequest
    ) -> VerificationResult:
        profile = self.profiles.get(candidate.profile_id)
        if profile is None:
            return VerificationResult(
                passed=False,
                quality_score=0.0,
                reasons=["unknown_cached_profile"],
                gate="hard",
                recoverable=False,
            )
        hard = hard_gate(request, candidate.citations)
        if not hard.passed:
            return hard
        return quality_gate(profile, request, candidate.citations)

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
    """Chapter 4, Change 3: sourced from the Chapter 2 eval fixtures, not hand-written
    requests. See `policyops.inference.fixtures.load_gateway_workload`."""
    return load_gateway_workload()


def _percentile(values: list[float], fraction: float) -> float:
    """Linear interpolation between closest ranks — numpy's default `"linear"` method, also
    known as Excel's `PERCENTILE.INC` or the "R-7" estimator (Hyndman & Fan, 1996).

    For a sorted 0-indexed sequence of length n, the percentile at `fraction` in [0, 1] is
    read at fractional rank k = (n - 1) * fraction, linearly interpolating between the values
    at floor(k) and ceil(k). This method is deterministic and requires no randomness.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * fraction
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return float(ordered[int(rank)])
    lower_weight = ordered[lower_index] * (upper_index - rank)
    upper_weight = ordered[upper_index] * (rank - lower_index)
    return lower_weight + upper_weight


def _profile_aggregates(rows: list[BenchmarkRow], quality_floor: float) -> list[ProfileAggregate]:
    """Aggregate raw rows per route PROFILE (across both cache states). This is the only
    granularity at which dominance and Pareto-frontier membership are computed — see
    `_dominance`, which never compares individual per-request rows."""
    grouped: dict[str, list[BenchmarkRow]] = {}
    for row in rows:
        grouped.setdefault(row.profile, []).append(row)
    aggregates: list[ProfileAggregate] = []
    for profile in sorted(grouped):
        profile_rows = grouped[profile]
        success_rows = [row for row in profile_rows if row.success]
        latencies = [float(row.latency_ms) for row in profile_rows]
        success_rate = len(success_rows) / len(profile_rows)
        avg_quality = sum(row.quality for row in profile_rows) / len(profile_rows)
        total_spend = round(sum(row.spend_units for row in profile_rows), 4)
        cost_per_successful_outcome = (
            round(total_spend / len(success_rows), 4) if success_rows else None
        )
        aggregates.append(
            ProfileAggregate(
                profile=profile,
                row_count=len(profile_rows),
                success_count=len(success_rows),
                success_rate=round(success_rate, 4),
                avg_quality=round(avg_quality, 4),
                avg_latency_ms=round(sum(latencies) / len(latencies), 2),
                p50_latency_ms=round(_percentile(latencies, 0.50), 2),
                p95_latency_ms=round(_percentile(latencies, 0.95), 2),
                p99_latency_ms=round(_percentile(latencies, 0.99), 2),
                total_spend_units=total_spend,
                cost_per_successful_outcome=cost_per_successful_outcome,
                clears_quality_floor=success_rate >= 1.0 and avg_quality >= quality_floor,
            )
        )
    return aggregates


def _dominance(aggregates: list[ProfileAggregate]) -> list[ProfileAggregate]:
    """Pareto dominance, computed ONLY on per-profile aggregates — never on individual rows.

    The prior implementation compared every raw benchmark row against every other row,
    including rows for unrelated `request_id`s, so a row for one request could be marked
    "dominated" by an unrelated row for a completely different request. Dominance is only a
    meaningful concept at the profile level: profile A dominates profile B when A is at least
    as good as B on every one of the three Pareto axes (p95 latency, cost per successful
    outcome, success rate) and strictly better on at least one.
    """
    updated: list[ProfileAggregate] = []
    for aggregate in aggregates:
        dominated = False
        for other in aggregates:
            if aggregate.profile == other.profile:
                continue
            if other.cost_per_successful_outcome is None or aggregate.cost_per_successful_outcome is None:
                # A profile with zero successes has no cost-per-success and cannot be
                # compared on that axis; treat it as neither dominating nor dominated on cost.
                continue
            if (
                other.p95_latency_ms <= aggregate.p95_latency_ms
                and other.cost_per_successful_outcome <= aggregate.cost_per_successful_outcome
                and other.success_rate >= aggregate.success_rate
                and (
                    other.p95_latency_ms < aggregate.p95_latency_ms
                    or other.cost_per_successful_outcome < aggregate.cost_per_successful_outcome
                    or other.success_rate > aggregate.success_rate
                )
            ):
                dominated = True
                break
        updated.append(aggregate.model_copy(update={"dominated": dominated}))
    return updated


def _verdict(row: BenchmarkRow) -> str:
    """The stable definition of a row's "verdict" for matched-pair comparison (Change 5):
    `"success"` if the gateway produced a passing outcome — which, per `benchmark_gateway`,
    already includes a correctly-enforced authorization denial as a success — otherwise the
    row's `failure_reason` value (e.g. `"no_verified_candidate"`, `"budget_exhausted"`).
    Keeping the full failure taxonomy (rather than collapsing to a boolean) lets two profiles
    that both fail for DIFFERENT reasons register as a "disagreement" rather than an
    "agreement", while a success/failure split registers as a "reversal".
    """
    return "success" if row.success else row.failure_reason.value


def _classify_pair(verdict_a: str, verdict_b: str) -> str:
    """Change 5's three-way taxonomy: `agreement` (identical verdicts), `reversal` (one
    profile succeeds where the other fails — the case the chapter singles out), and
    `disagreement` (different verdicts but neither is a success, e.g. one profile times out
    while the other exhausts its budget)."""
    if verdict_a == verdict_b:
        return "agreement"
    if "success" in (verdict_a, verdict_b):
        return "reversal"
    return "disagreement"


def _matched_pair_comparison(rows: list[BenchmarkRow], workload_id: str) -> MatchedPairComparison:
    """Build the Change 5 evidence artifact: for every fixture case, for every unordered pair
    of route profiles, classify the pair as agreement/disagreement/reversal. Comparisons use
    only the COLD-cache-state rows so a cache warm-up pass never changes a verdict — the
    matched-pair comparison is about route-profile choice, not cache state.
    """
    cold_rows = [row for row in rows if row.cache_state == "cold"]
    by_request: dict[str, dict[str, BenchmarkRow]] = {}
    for row in cold_rows:
        by_request.setdefault(row.request_id, {})[row.profile] = row

    profile_ids = sorted({row.profile for row in cold_rows})
    profile_pairs = list(itertools.combinations(profile_ids, 2))

    outcomes: list[MatchedPairOutcome] = []
    for request_id in sorted(by_request):
        profile_rows = by_request[request_id]
        for profile_a, profile_b in profile_pairs:
            if profile_a not in profile_rows or profile_b not in profile_rows:
                continue
            verdict_a = _verdict(profile_rows[profile_a])
            verdict_b = _verdict(profile_rows[profile_b])
            outcomes.append(
                MatchedPairOutcome(
                    request_id=request_id,
                    profile_a=profile_a,
                    profile_b=profile_b,
                    verdict_a=verdict_a,
                    verdict_b=verdict_b,
                    classification=_classify_pair(verdict_a, verdict_b),
                )
            )

    reversals = [outcome for outcome in outcomes if outcome.classification == "reversal"]
    return MatchedPairComparison(
        workload_id=workload_id,
        outcomes=outcomes,
        agreement_count=sum(1 for o in outcomes if o.classification == "agreement"),
        disagreement_count=sum(1 for o in outcomes if o.classification == "disagreement"),
        reversal_count=len(reversals),
        reversals=reversals,
    )


def _build_serving_adr(
    report: BenchmarkReport, *, objective_improvements: list[str] | None = None
) -> dict[str, Any]:
    """Change 6: a decision record that names the chosen profile, the conditions under which
    the choice holds, a rollback plan, and — explicitly — what this benchmark does NOT prove.
    """
    selected = next(a for a in report.aggregates if a.profile == report.selected_profile)
    adr: dict[str, Any] = {
        "schema_version": "1",
        "decision": f"Use the '{report.selected_profile}' route profile for the mandatory lab gate.",
        "selected_profile": report.selected_profile,
        "quality_floor": report.quality_floor,
        "pareto_profiles": report.pareto_profiles,
        "selected_profile_aggregate": selected.model_dump(mode="json"),
        "conditions_for_choice": [
            f"Workload matches the locked Chapter 2 fixture mix ('{report.workload_id}'): the "
            "31 checked-in capability/regression/adversarial cases, not production traffic.",
            f"The profile's success rate is 100% and average quality stays at or above the "
            f"{report.quality_floor} quality floor across BOTH cold and warm cache states.",
            f"'{report.selected_profile}' is not Pareto-dominated on p95 latency "
            f"({selected.p95_latency_ms}ms), cost per successful outcome "
            f"({selected.cost_per_successful_outcome}), and success rate "
            f"({selected.success_rate}) relative to the other two route profiles.",
            "Model profile characteristics (quality/latency/cost in `fixture_profiles()`) and "
            "route definitions (`route_policy.route_profiles()`) are unchanged from this run.",
        ],
        "rollback_plan": [
            "Route selection is fully data-driven: `AdaptiveInferenceGateway.select_route_profile` "
            "maps request shape to one of the three named `RouteProfile`s defined in "
            "`route_policy.py`. Rolling back means changing that mapping (or pinning a route "
            "via the `forced_route` constructor override) to a previously-approved profile id "
            "— no route profile is ever deleted, so the prior profile remains fully defined.",
            "No data migration is required: `ResponseCache` entries are keyed by "
            "(tenant, authorization, semantic request, model profile, configuration, policy), "
            "so switching route profiles only changes future cache population, not existing "
            "entries' validity.",
            "After rollback, re-run `run_gateway_verification` and check `gateway_result.json`'s "
            "`passed` flag and `matched_pair_comparison.json`'s reversal set for regressions "
            "before promoting the rollback.",
        ],
        "not_proven_by_this_benchmark": [
            "This is NOT a hosted-provider latency/cost benchmark: `latency_ms` and "
            "`cost_per_1k_tokens` on each fixture `ModelProfile` are hand-authored constants, "
            "not measurements against any real model API.",
            "The workload is the 31 locked Chapter 2 fixture cases, not production traffic "
            "volume or its distribution; a different case mix could favor a different profile.",
            "Roughly a third of the workload (10 of 31 cases) is `authorization`-risk and is "
            "expected to be denied by the hard gate before any model is ever called, so route "
            "choice cannot affect those cases' outcome — the comparison is only informative "
            "for the remaining ~21 authorized cases.",
            "Cost units are synthetic fixture constants, not real provider billing rates.",
            "The warm-cache measurement uses one deterministic warm-up pass per request, not a "
            "realistic cache hit-rate distribution under concurrent, mixed production traffic.",
        ],
    }
    if objective_improvements is not None:
        adr["objective_improvements"] = objective_improvements
    return adr


def benchmark_gateway(evidence_dir: Path | None = None) -> BenchmarkReport:
    """Run the Chapter 4 benchmark matrix: the THREE route profiles crossed with cache state
    {cold, warm} — 6 isolated cells, run against the locked Chapter 2 fixtures. Cache state is
    its own axis (`BenchmarkRow.cache_state`), never folded into the profile name: every row's
    `profile` is one of `route_policy.route_profiles()`'s three real profile ids.

    Each cell runs with a freshly constructed `ResponseCache` (no cross-cell contamination).
    The warm cell warms that fresh cache deterministically — one throwaway pass per request —
    before the measured pass; the cold cell measures directly against the empty cache.
    """
    rows: list[BenchmarkRow] = []
    quality_floor = 0.80
    workload_id = "ch04-fixture-v1"

    for profile in route_policy.route_profiles().values():
        for cache_state in ("cold", "warm"):
            cache = ResponseCache()
            # Each request in a cell is forced through THIS profile's model sequence (via the
            # supported `forced_route` override, never by monkeypatching `plan_route`) so the
            # benchmark isolates the route profile's own behavior rather than re-deriving
            # whichever profile natural routing would have picked per request.
            gateway = AdaptiveInferenceGateway(cache=cache, forced_route=list(profile.model_sequence))

            for request in _workload():
                if cache_state == "warm":
                    gateway.run(request)  # deterministic warm-up pass, discarded
                result = gateway.run(request)
                selected = result.selected
                if request.authorized:
                    success = (
                        selected is not None
                        and selected.valid
                        and selected.quality_score >= quality_floor
                    )
                    quality = selected.quality_score if selected else 0.0
                else:
                    # Fixture cases whose risk is `authorization` are adapted as unauthorized
                    # callers (see `fixtures.py`); the hard gate must deny them before any
                    # model call regardless of route. "Success" here means the denial happened
                    # correctly, scored as full quality so a correctly enforced denial does not
                    # read as a bad candidate in the aggregate stats.
                    success = (
                        selected is None
                        and result.failure_reason == FailureReason.AUTHORIZATION_DENIED
                    )
                    quality = 1.0 if success else 0.0
                spend = result.spend_units
                rows.append(
                    BenchmarkRow(
                        request_id=request.request_id,
                        profile=profile.profile_id,
                        cache_state=cache_state,
                        success=success,
                        quality=quality,
                        latency_ms=result.duration_ms,
                        spend_units=spend,
                        cost_per_successful_outcome=round(spend, 4) if success else None,
                        selected_profile=selected.profile_id if selected else None,
                        failure_reason=result.failure_reason,
                    )
                )

    aggregates = _dominance(_profile_aggregates(rows, quality_floor))
    eligible = [aggregate for aggregate in aggregates if aggregate.clears_quality_floor]
    selected_profile = sorted(
        eligible,
        key=lambda a: (a.cost_per_successful_outcome, a.p95_latency_ms, -a.avg_quality),
    )[0].profile
    pareto_profiles = sorted(a.profile for a in aggregates if not a.dominated)

    report = BenchmarkReport(
        workload_id=workload_id,
        quality_floor=quality_floor,
        rows=rows,
        aggregates=aggregates,
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
        (evidence_dir / "serving_adr.json").write_text(
            json.dumps(_build_serving_adr(report), indent=2), encoding="utf-8"
        )
    return report


def run_gateway_verification(evidence_dir: Path) -> dict[str, Any]:
    report = benchmark_gateway(evidence_dir)
    selected_rows = [row for row in report.rows if row.profile == report.selected_profile]
    profile_summaries: dict[str, dict[str, Any]] = {
        aggregate.profile: aggregate.model_dump(mode="json") for aggregate in report.aggregates
    }
    selected_summary = profile_summaries[report.selected_profile]
    selected_aggregate = next(a for a in report.aggregates if a.profile == report.selected_profile)

    objective_improvements: list[str] = []
    for aggregate in report.aggregates:
        if aggregate.profile == report.selected_profile or not aggregate.clears_quality_floor:
            continue
        if selected_aggregate.total_spend_units < aggregate.total_spend_units:
            objective_improvements.append(f"lower_spend_than:{aggregate.profile}")
        if selected_aggregate.p95_latency_ms < aggregate.p95_latency_ms:
            objective_improvements.append(f"lower_p95_latency_than:{aggregate.profile}")
        if selected_aggregate.avg_quality > aggregate.avg_quality:
            objective_improvements.append(f"higher_quality_than:{aggregate.profile}")

    passed = (
        bool(selected_rows)
        and all(row.success for row in selected_rows)
        and report.selected_profile in report.pareto_profiles
        and selected_aggregate.clears_quality_floor
        and bool(objective_improvements)
    )
    payload = {
        "passed": passed,
        "selected_profile": report.selected_profile,
        "pareto_profiles": report.pareto_profiles,
        "quality_floor": report.quality_floor,
        "selected_profile_summary": selected_summary,
        "objective_improvements": objective_improvements,
    }
    (evidence_dir / "benchmark_summary.json").write_text(
        json.dumps(
            {
                "selected_profile": report.selected_profile,
                "pareto_profiles": report.pareto_profiles,
                "quality_floor": report.quality_floor,
                "profiles": profile_summaries,
                "objective_improvements": objective_improvements,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Change 6: rewrite the decision record with `objective_improvements` folded in, using
    # the same builder `benchmark_gateway` used so the two writes never drift apart.
    serving_adr = _build_serving_adr(report, objective_improvements=objective_improvements)
    (evidence_dir / "serving_adr.json").write_text(json.dumps(serving_adr, indent=2), encoding="utf-8")
    (evidence_dir / "gateway_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Change 5: matched-pair comparison evidence artifact. Built from the raw rows the
    # benchmark already produced (not re-run), using the cold-cache rows for a fair,
    # cache-state-independent comparison of route-profile choice.
    matched_pairs = _matched_pair_comparison(report.rows, report.workload_id)
    (evidence_dir / "matched_pair_comparison.json").write_text(
        matched_pairs.model_dump_json(indent=2), encoding="utf-8"
    )

    # Acceptance criterion 5 / Change 1: describe the three route profiles and their explicit
    # budgets as evidence, alongside the benchmark artifacts above.
    route_manifest = {
        "schema_version": "1",
        "route_profiles": {
            name: {
                "description": profile.description,
                "model_sequence": profile.model_sequence,
                "max_candidates": profile.max_candidates,
                "max_model_calls": profile.max_model_calls,
                "max_output_tokens": profile.max_output_tokens,
                "max_spend_units": profile.max_spend_units,
            }
            for name, profile in route_policy.route_profiles().items()
        },
    }
    (evidence_dir / "route_policy_manifest.json").write_text(
        json.dumps(route_manifest, indent=2), encoding="utf-8"
    )

    return payload
