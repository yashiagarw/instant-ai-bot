"""Sentry for the API and the worker. SENTRY_DSN empty = off (nothing is imported or sent).

Before anything leaves, scrub() removes or masks personal data: cookies, request headers and bodies, query strings,
user details and local variables are dropped; every remaining text (messages, exception values, breadcrumbs) has
phone numbers, emails and number plates masked and 6-digit codes and long tokens replaced. No session replay,
no default PII, no request bodies. Each event carries the request id as a tag, to find its log lines.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import Settings
from app.llm.mask import mask
from app.observability.logs import current_request_id

log = logging.getLogger(__name__)
CODE = re.compile(r"(?<!\d)\d{6}(?!\d)")  # OTP and two-factor codes
TOKEN = re.compile(r"\b[A-Za-z0-9_\-]{24,}\b")  # session tokens, keys, signed-link signatures
DROP_KEYS = ("cookies", "headers", "data", "query_string", "env")


def scrub_text(text: str) -> str:
    return TOKEN.sub("[token]", CODE.sub("[code]", mask(text).text))


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return value


def scrub(event: dict, hint: dict | None = None) -> dict:
    request = event.get("request")
    if isinstance(request, dict):
        for key in DROP_KEYS:
            request.pop(key, None)
        if isinstance(request.get("url"), str):
            request["url"] = request["url"].split("?", 1)[0]
    event.pop("user", None)
    event.pop("server_name", None)
    for exc in (event.get("exception") or {}).get("values") or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = scrub_text(exc["value"])
        for frame in (exc.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    if isinstance(event.get("message"), str):
        event["message"] = scrub_text(event["message"])
    if isinstance(event.get("logentry"), dict):
        event["logentry"] = {"message": scrub_text(str(event["logentry"].get("message", ""))), "params": []}
    crumbs = event.get("breadcrumbs")
    values = crumbs.get("values") if isinstance(crumbs, dict) else crumbs
    for crumb in values or []:
        if isinstance(crumb.get("message"), str):
            crumb["message"] = scrub_text(crumb["message"])
        if isinstance(crumb.get("data"), dict):
            crumb["data"] = _scrub({k: v for k, v in crumb["data"].items() if k not in ("url", "query")})
    if isinstance(event.get("extra"), dict):
        event["extra"] = _scrub(event["extra"])
    tags = event.setdefault("tags", {})
    if isinstance(tags, dict) and current_request_id():
        tags["request_id"] = current_request_id()
    return event


def scrub_breadcrumb(crumb: dict, hint: dict | None = None) -> dict:
    if isinstance(crumb.get("message"), str):
        crumb["message"] = scrub_text(crumb["message"])
    if isinstance(crumb.get("data"), dict):
        crumb["data"] = _scrub({k: v for k, v in crumb["data"].items() if k not in ("url", "query")})
    return crumb


def init_sentry(settings: Settings, service: str) -> bool:
    """Start Sentry for this process when SENTRY_DSN is set. Returns whether it is on."""
    if not settings.sentry_dsn:
        log.info("Sentry off for %s (no SENTRY_DSN)", service)
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        release=settings.sentry_release or None,
        server_name=service,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=scrub,
        before_breadcrumb=scrub_breadcrumb,
    )
    sentry_sdk.set_tag("service", service)
    log.info("Sentry on for %s", service)
    return True
