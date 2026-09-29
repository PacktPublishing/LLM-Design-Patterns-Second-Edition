"""ModelClient port - provider types must not cross this boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from policyops.contracts import ModelRequest, ModelResult, RunContext


@runtime_checkable
class ModelClient(Protocol):
    async def generate(self, request: ModelRequest, context: RunContext) -> ModelResult:
        """Generate a model result from domain contracts only."""

    async def ready(self) -> bool:
        """Non-generative readiness check."""
