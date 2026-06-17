import time
from collections import defaultdict


class RateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    def _clean(self, key: str, window_sec: float) -> None:
        now = time.monotonic()
        entries = self._windows.get(key)
        if entries is None:
            return
        cutoff = now - window_sec
        while entries and entries[0] < cutoff:
            entries.pop(0)
        if not entries:
            del self._windows[key]

    def allow(self, key: str, max_requests: int, window_sec: float) -> bool:
        self._clean(key, window_sec)
        if len(self._windows.get(key, [])) >= max_requests:
            return False
        self._windows[key].append(time.monotonic())
        return True

    def remaining(self, key: str, max_requests: int, window_sec: float) -> int:
        self._clean(key, window_sec)
        return max(len(self._windows.get(key, [])), max_requests) - len(
            self._windows.get(key, [])
        )


_limiter = RateLimiter()


def check_rate_limit(key: str, max_requests: int, window_sec: float) -> bool:
    return _limiter.allow(key, max_requests, window_sec)
