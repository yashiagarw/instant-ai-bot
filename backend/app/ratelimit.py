"""Rate limits by client IP: a sliding window per limit name.

make_limiter() is the one way to get a limiter. With RATE_LIMIT_BACKEND=redis (the default) the window lives in Redis
(REDIS_URL), so a limit holds across all API processes and restarts; one atomic script per check. If Redis cannot be
reached, that check falls back to an in-memory window (per process) and the API logs it: a Redis outage never
fails a request. RATE_LIMIT_BACKEND=memory (tests) keeps everything in memory.

Keys hold a hash of the IP, never the IP itself; Redis keeps nothing on disk (docker-compose: --save "").
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from collections import deque

from fastapi import Request

log = logging.getLogger(__name__)


class RateLimiter:
    """In-memory sliding window (per process)."""

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


# Sliding window in a sorted set: drop old hits, count, add this one (or say how long to wait). Atomic in Redis.
_SCRIPT = """
local key, now, window, limit, member = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
if redis.call('ZCARD', key) >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return tostring(tonumber(oldest[2]) + window - now)
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, math.ceil(window * 1000))
return '-1'
"""

_clients: dict[str, object] = {}
_clients_lock = threading.Lock()


def _redis(url: str):
    with _clients_lock:
        client = _clients.get(url)
        if client is None:
            import redis

            client = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
            _clients[url] = client
        return client


class RedisRateLimiter:
    def __init__(self, url: str, name: str, limit: int, window_seconds: float, prefix: str = "rl"):
        self.url, self.name, self.limit, self.window = url, name, limit, window_seconds
        self.prefix = prefix
        self.fallback = RateLimiter(limit, window_seconds)
        self._script = None
        self._warned_at = 0.0

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{self.name}:{hashlib.sha256(key.encode()).hexdigest()[:24]}"

    def check(self, key: str) -> float | None:
        try:
            client = _redis(self.url)
            if self._script is None:
                self._script = client.register_script(_SCRIPT)
            out = self._script(
                keys=[self._key(key)], args=[time.time(), self.window, self.limit, uuid.uuid4().hex], client=client
            )
            wait = float(out.decode() if isinstance(out, bytes) else out)
            return None if wait < 0 else max(0.0, wait)
        except Exception as e:  # Redis down or slow: count in this process instead
            now = time.monotonic()
            if now - self._warned_at > 60:
                self._warned_at = now
                log.warning(
                    "Rate limit %s: Redis unavailable (%s), counting in this process", self.name, type(e).__name__
                )
            return self.fallback.check(key)


def make_limiter(settings, name: str, limit: int, window_seconds: float):
    """The limiter for one named limit: Redis-backed unless RATE_LIMIT_BACKEND=memory."""
    if settings.rate_limit_backend == "redis" and settings.redis_url:
        return RedisRateLimiter(settings.redis_url, name, limit, window_seconds)
    return RateLimiter(limit, window_seconds)


def app_limiter(app_state, name: str, limit: int, window_seconds: float):
    """The app's limiter of this name, made once (endpoints call this per request)."""
    key = f"limiter_{name}"
    limiter = getattr(app_state, key, None)
    if limiter is None:
        limiter = make_limiter(app_state.settings, name, limit, window_seconds)
        setattr(app_state, key, limiter)
    return limiter


def client_ip(request: Request, trust_forwarded_for: bool) -> str:
    if trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded.strip():
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def client_ip_from_scope(scope, headers: dict, trust_forwarded_for: bool) -> str:
    if trust_forwarded_for and headers.get("x-forwarded-for", "").strip():
        return headers["x-forwarded-for"].split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"
