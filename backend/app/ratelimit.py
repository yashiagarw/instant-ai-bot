"""In-memory sliding-window rate limiter, keyed by client IP. Per process: with several workers, each has
its own window (use a shared store such as Redis when the API is scaled out). IPs are never persisted."""

import threading
import time
from collections import deque

from fastapi import Request


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, clock=time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """Record a hit. None when allowed, else the seconds to wait before the next allowed hit."""
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(0.0, hits[0] + self.window - now)
            hits.append(now)
            if len(self._hits) > 10_000:  # forget idle clients so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
                    del self._hits[k]
            return None


def client_ip(request: Request, trust_forwarded_for: bool) -> str:
    if trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded.strip():
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
