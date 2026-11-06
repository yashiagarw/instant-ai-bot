"""Cloudflare Turnstile on public forms: the request form and the sign-in code requests (customers and mechanics).

The browser solves the widget and sends its token in the X-Turnstile-Token header; the API checks it with Cloudflare
(siteverify) before doing anything. TURNSTILE_SECRET_KEY empty = off (every request passes, logged once at start-up),
like the other providers. Development and tests use Cloudflare's test keys (README "Phase 5.4"). If Cloudflare
cannot be reached the request is refused with a "try again" message (a bot check that fails open would not be one).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from fastapi import HTTPException, Request, status

from app.ratelimit import client_ip

log = logging.getLogger(__name__)
HEADER = "x-turnstile-token"


class Verifier(Protocol):
    def verify(self, token: str, ip: str | None) -> bool: ...


class CloudflareVerifier:
    def __init__(self, secret: str, url: str):
        self.secret, self.url = secret, url

    def verify(self, token: str, ip: str | None) -> bool:
        form = {"secret": self.secret, "response": token}
        if ip:
            form["remoteip"] = ip
        req = urllib.request.Request(self.url, data=urllib.parse.urlencode(form).encode(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as res:  # noqa: S310 - fixed https URL
                body = json.loads(res.read() or b"{}")
        except (OSError, ValueError) as e:
            log.warning("Turnstile check could not reach Cloudflare: %s", type(e).__name__)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "We couldn't check that you're human. Please try again."
            ) from None
        if not body.get("success"):
            log.info("Turnstile refused a request: %s", ",".join(body.get("error-codes") or []) or "no reason")
        return bool(body.get("success"))


def verifier(request: Request) -> Verifier | None:
    state = request.app.state
    if not hasattr(state, "turnstile"):
        s = state.settings
        state.turnstile = (
            CloudflareVerifier(s.turnstile_secret_key, s.turnstile_verify_url) if s.turnstile_secret_key else None
        )
    return state.turnstile


def require_human(request: Request) -> None:
    """FastAPI dependency for the public forms."""
    check = verifier(request)
    if check is None:
        return
    token = request.headers.get(HEADER, "")
    if not token or len(token) > 2048:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Please complete the 'I'm human' check and try again.")
    if not check.verify(token, client_ip(request, request.app.state.settings.trust_forwarded_for)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The 'I'm human' check failed. Please try it again.")
