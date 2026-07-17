"""Optional local-model adapter stub — same ModelClient contract as replay."""

from __future__ import annotations

from policyops.adapters.replay import ReplayModelClient
from policyops.contracts import ModelRequest, ModelResult, RunContext


class LocalModelClient:
    """Thin stub that delegates to replay fixtures so contract tests stay offline.

    A real local process adapter can replace this later without changing app code.
    """

    def __init__(self, fixture_pack, *, fault_scenario: str | None = None) -> None:
        self._inner = ReplayModelClient(fixture_pack, fault_scenario=fault_scenario)

    async def ready(self) -> bool:
        return await self._inner.ready()

    async def generate(self, request: ModelRequest, context: RunContext) -> ModelResult:
        result = await self._inner.generate(request, context)
        if result.kind == "success":
            result.usage.adapter = "local"
        return result
