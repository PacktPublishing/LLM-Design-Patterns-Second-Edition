"""Bounded concurrency and backoff helpers for eval scheduling."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass


@dataclass
class PoolBudget:
    concurrency: int = 4
    max_retries: int = 3
    base_delay_ms: float = 10.0
    jitter_ms: float = 5.0


class BoundedPool:
    def __init__(self, budget: PoolBudget) -> None:
        self.budget = budget
        self._sem = asyncio.Semaphore(budget.concurrency)
        self.retry_count = 0

    async def run(self, coro_factory, *, throttle_until: int = 0):
        """Run coroutine with bounded concurrency and capped retries on throttle."""
        attempt = 0
        while True:
            async with self._sem:
                try:
                    if throttle_until and attempt < throttle_until:
                        self.retry_count += 1
                        raise TimeoutError("simulated 429")
                    return await coro_factory()
                except TimeoutError:
                    attempt += 1
                    if attempt > self.budget.max_retries:
                        raise
                    delay = (self.budget.base_delay_ms / 1000) * (2 ** (attempt - 1))
                    delay += random.uniform(0, self.budget.jitter_ms / 1000)
                    await asyncio.sleep(delay)
