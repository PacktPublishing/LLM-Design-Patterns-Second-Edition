"""Route profiles — named policies OVER model profiles (Chapter 4, Change 1).

`fixture_profiles()` in `gateway.py` describes MODEL profiles: `small-fast`, `standard`,
`reasoned`, `quantized-small`, `draft-reasoned`. Those are per-model quality/latency/cost
characteristics.

A `RouteProfile` is a different, higher layer: a named, reviewable POLICY over those model
profiles. It says which model(s) a request is allowed to try, in what order, and under what
explicit token/call/spend ceilings. `AdaptiveInferenceGateway.plan_route` selects a
`RouteProfile` for a request and returns its `model_sequence`; it never returns an
ad-hoc list of model profile ids.

Exactly three route profiles are defined:
  - direct-baseline           a single model call, no escalation.
  - enhanced-with-candidates  several candidates sampled at one tier, no escalation
                               across tiers.
  - routed-with-escalation    an escalating model sequence with early exit on the first
                               verified candidate.
"""

from __future__ import annotations

from pydantic import Field

from policyops.inference.schemas import StrictModel


class RouteProfile(StrictModel):
    """A named routing policy: which models to try, in what order, under what budgets."""

    profile_id: str
    description: str
    model_sequence: list[str] = Field(min_length=1)
    max_candidates: int = Field(ge=1, le=8)
    max_model_calls: int = Field(ge=1, le=8)
    max_output_tokens: int = Field(ge=1)
    max_spend_units: float = Field(ge=0.0)


DIRECT_BASELINE = RouteProfile(
    profile_id="direct-baseline",
    description="Single model call, no escalation. Cheapest and fastest route.",
    model_sequence=["small-fast"],
    max_candidates=1,
    max_model_calls=1,
    max_output_tokens=256,
    max_spend_units=1.0,
)

ENHANCED_WITH_CANDIDATES = RouteProfile(
    profile_id="enhanced-with-candidates",
    description=(
        "Several candidates sampled at one (stronger) tier, no escalation across tiers."
    ),
    model_sequence=["standard", "standard", "standard"],
    max_candidates=3,
    max_model_calls=3,
    max_output_tokens=512,
    max_spend_units=5.0,
)

ROUTED_WITH_ESCALATION = RouteProfile(
    profile_id="routed-with-escalation",
    description="Escalating model sequence with early exit on the first verified candidate.",
    model_sequence=["small-fast", "standard", "reasoned"],
    max_candidates=3,
    max_model_calls=3,
    max_output_tokens=1024,
    max_spend_units=10.0,
)

_ROUTE_PROFILES: dict[str, RouteProfile] = {
    profile.profile_id: profile
    for profile in (DIRECT_BASELINE, ENHANCED_WITH_CANDIDATES, ROUTED_WITH_ESCALATION)
}


def route_profiles() -> dict[str, RouteProfile]:
    """Return a fresh copy of the three named route profiles, keyed by profile_id."""
    return dict(_ROUTE_PROFILES)
