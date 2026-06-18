"""Adaptive concurrent executor based on system load."""

import asyncio
from typing import Any


class ConcurrentExecutor:
    """Run coroutines concurrently with adaptive concurrency limits."""

    def __init__(self, max_concurrency: str | int = "dynamic") -> None:
        self._max = max_concurrency

    def _optimal(self) -> int:
        if isinstance(self._max, int):
            return self._max
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory().percent
        except Exception:
            return 3
        if cpu < 50 and mem < 70:
            return 10
        if cpu < 75 and mem < 85:
            return 5
        return 2

    async def run_concurrent(self, coroutines: list) -> list[Any]:
        if not coroutines:
            return []
        limit = self._optimal()
        sem = asyncio.Semaphore(limit)

        async def _bounded(coro):
            async with sem:
                return await coro

        results = await asyncio.gather(
            *[_bounded(c) for c in coroutines], return_exceptions=True
        )
        out: list[Any] = []
        for r in results:
            if isinstance(r, BaseException):
                out.append({"ok": False, "error": str(r)})
            else:
                out.append(r)
        return out
