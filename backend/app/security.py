"""HTTP hardening for the API (Phase 5.4), as plain ASGI middleware (cheap, and it sees streamed bodies):

- **Request id and access log**: every request gets an id (X-Request-ID from the web / admin app if it is a sane
  value, else a new one), set for the logs, returned in the response, passed on to the worker's jobs. One access
  line per request: method, path (no query string), status, duration. No client IP.
- **Security headers** on every API response: a CSP that allows nothing (JSON only), frame-ancestors none,
  nosniff, no referrer, no caching of personal answers by shared caches.
- **Body size**: bodies over API_MAX_BODY_BYTES (256 KB) are refused with 413 before they are read, except the
  upload endpoints, which enforce their own limits. Ordinary bodies are read here, bounded, so a missing or lying
  Content-Length does not help.
- **CSRF**: the logins are cookies (SameSite Lax / Strict) and CORS allows only the two apps. On top of that, a
  state-changing request (POST, PUT, PATCH, DELETE) that says where it comes from must come from WEB_ORIGIN or
  ADMIN_ORIGIN: an Origin (or, without one, a Referer) from anywhere else, including "null", is refused with 403.
  Browsers always send Origin on these requests; a request with neither header is not from a browser page, so it
  cannot carry a victim's cookies against their will. The WhatsApp webhook is exempt (Meta posts it; it keeps its
  signature check).
- **Rate limit backstop**: GLOBAL_RATE_LIMIT requests per client IP per window across all of /api (the endpoints keep
  their own, tighter limits), counted in Redis like the others.
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlsplit

from app.config import Settings
from app.observability.logs import clean_request_id, new_request_id, request_id_var
from app.ratelimit import client_ip_from_scope, make_limiter

log = logging.getLogger("app.access")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT = ("/api/webhooks/whatsapp",)
API_HEADERS = [
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-site"),
]


def upload_limits(settings: Settings) -> list[tuple[re.Pattern, int]]:
    """(method + path pattern, bytes) for the endpoints that take files. A little room for the multipart overhead."""
    slack = 64 * 1024
    mb = 1024 * 1024
    return [
        (re.compile(r"^POST /api/admin/datasets/uploads$"), settings.dataset_upload_max_mb * mb + slack),
        (re.compile(r"^POST /api/admin/media/pictures$"), settings.upload_max_bytes + slack),
        (re.compile(r"^POST /api/admin/mechanics/\d+/(documents|photo)$"), settings.mechanic_doc_max_mb * mb + slack),
        (re.compile(r"^POST /api/admin/parts/versions/\d+/import$"), 2 * mb + slack),
    ]


def origin_of(value: str | None) -> str | None:
    if not value:
        return None
    if value == "null":
        return "null"
    parts = urlsplit(value)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else "invalid"


async def _send_json(send, status: int, body: bytes, extra: list[tuple[bytes, bytes]] | None = None) -> None:
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *API_HEADERS]
    await send({"type": "http.response.start", "status": status, "headers": headers + (extra or [])})
    await send({"type": "http.response.body", "body": body})


class HardeningMiddleware:
    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings
        self.allowed = {o.rstrip("/") for o in (settings.web_origin, settings.admin_origin) if o}
        self.uploads = upload_limits(settings)
        self.limiter = make_limiter(settings, "global", settings.global_rate_limit, settings.global_rate_window_seconds)

    def _max_body(self, method: str, path: str) -> int:
        key = f"{method} {path}"
        for pattern, size in self.uploads:
            if pattern.match(key):
                return size
        return self.settings.api_max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        rid = clean_request_id(headers.get("x-request-id")) or new_request_id()
        token = request_id_var.set(rid)
        method, path = scope["method"], scope["path"]
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                extra = [(b"x-request-id", rid.encode())]
                if path.startswith("/api"):
                    have = {k.lower() for k, _ in message.get("headers", [])}
                    extra += [(k, v) for k, v in API_HEADERS if k not in have]
                    if b"cache-control" not in have:
                        extra.append((b"cache-control", b"no-store"))
                message = {**message, "headers": list(message.get("headers", [])) + extra}
            await send(message)

        try:
            refusal = self._refuse(scope, headers, method, path)
            if refusal is not None:
                status, body, extra = refusal
                status_holder["status"] = status
                await _send_json(send, status, body, [(b"x-request-id", rid.encode()), *extra])
                return
            limit = self._max_body(method, path)
            if path.startswith("/api") and limit == self.settings.api_max_body_bytes and method in UNSAFE:
                # Ordinary endpoints: read the (small) body here, bounded, so a stream without Content-Length is
                # cut off at the limit; then hand it to the app unchanged. Upload endpoints stream into their own
                # limits (they read the body themselves and answer 413).
                chunks, size, more = [], 0, True
                while more:
                    message = await receive()
                    if message["type"] != "http.request":
                        break
                    chunks.append(message.get("body", b""))
                    size += len(chunks[-1])
                    more = message.get("more_body", False)
                    if size > limit:
                        status_holder["status"] = 413
                        await _send_json(
                            send, 413, b'{"detail":"The request is too large"}', [(b"x-request-id", rid.encode())]
                        )
                        return
                body, sent = b"".join(chunks), {"done": False}

                async def replay():
                    if not sent["done"]:
                        sent["done"] = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await receive()

                await self.app(scope, replay, send_with_headers)
            else:
                await self.app(scope, receive, send_with_headers)
        finally:
            ms = round((time.perf_counter() - started) * 1000)
            if path.startswith("/api") and path not in ("/api/health/live",):
                extra = {"method": method, "path": path, "status": status_holder["status"], "duration_ms": ms}
                log.info("%s %s %s %sms", method, path, status_holder["status"], ms, extra=extra)
            request_id_var.reset(token)

    def _refuse(self, scope, headers: dict, method: str, path: str):
        if not path.startswith("/api"):
            return None
        # Size: a declared length over the limit is refused before anything is read.
        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self._max_body(method, path):
            return 413, b'{"detail":"The request is too large"}', []
        # CSRF: where a state-changing request says it comes from.
        if method in UNSAFE and not path.startswith(CSRF_EXEMPT):
            origin = origin_of(headers.get("origin")) or origin_of(headers.get("referer"))
            if origin is not None and origin not in self.allowed:
                return 403, b'{"detail":"Cross-site request refused"}', []
        # The backstop limit (not for health checks: the uptime monitor and Docker call them often).
        if not path.startswith("/api/health"):
            wait = self.limiter.check(client_ip_from_scope(scope, headers, self.settings.trust_forwarded_for))
            if wait is not None:
                retry = str(max(1, round(wait))).encode()
                return 429, b'{"detail":"Too many requests. Please wait a moment."}', [(b"retry-after", retry)]
        return None
