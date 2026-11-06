"""Masked calls: the provider rings the person who asked first, then connects them to the other person; both see only
the provider's number (Exotel's ExoPhone), never each other's.

CALL_PROVIDER=console (development) prints the call with masked numbers; exotel uses Exotel's "connect two numbers"
API: POST https://<key>:<token>@<subdomain>/v1/Accounts/<sid>/Calls/connect with From (rung first), To and CallerId
(the ExoPhone). docs/notifications-setup.md has the account steps.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from app.config import Settings
from app.notify.sms import mask_phone

log = logging.getLogger(__name__)


class CallError(RuntimeError):
    pass


class CallBridge(Protocol):
    name: str

    def connect(self, first: str, second: str, reference: str) -> str:
        """Ring `first`, then connect `second`. Returns the provider's call id. Raises CallError."""
        ...


class ConsoleBridge:
    name = "console"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def connect(self, first: str, second: str, reference: str) -> str:
        self.calls.append((first, second, reference))
        log.warning("CALL (console provider) %s: ringing %s, then %s", reference, mask_phone(first), mask_phone(second))
        return f"console-call-{len(self.calls)}"


class ExotelBridge:
    name = "exotel"

    def __init__(self, settings: Settings) -> None:
        needed = {
            "EXOTEL_SID": settings.exotel_sid,
            "EXOTEL_API_KEY": settings.exotel_api_key,
            "EXOTEL_API_TOKEN": settings.exotel_api_token,
            "EXOTEL_CALLER_ID": settings.exotel_caller_id,
        }
        missing = [k for k, v in needed.items() if not v]
        if missing:
            raise CallError(f"CALL_PROVIDER=exotel needs {', '.join(missing)}")
        self.s = settings

    def request_for(self, first: str, second: str) -> urllib.request.Request:
        s = self.s
        url = f"https://{s.exotel_subdomain}/v1/Accounts/{s.exotel_sid}/Calls/connect.json"
        form = urllib.parse.urlencode(
            {
                "From": "0" + first[-10:],
                "To": "0" + second[-10:],
                "CallerId": s.exotel_caller_id,
                "TimeLimit": str(s.call_time_limit_seconds),
                "CallType": "trans",
            }
        ).encode()
        auth = base64.b64encode(f"{s.exotel_api_key}:{s.exotel_api_token}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}
        return urllib.request.Request(url, data=form, method="POST", headers=headers)

    def connect(self, first: str, second: str, reference: str) -> str:
        try:
            with urllib.request.urlopen(self.request_for(first, second), timeout=10) as res:  # noqa: S310
                body = json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            log.warning("Exotel call for %s failed: HTTP %s", reference, e.code)
            raise CallError(f"Exotel answered HTTP {e.code}") from None
        except (OSError, ValueError) as e:
            raise CallError(f"Exotel not reachable ({type(e).__name__})") from None
        sid = (body.get("Call") or {}).get("Sid")
        if not sid:
            raise CallError("Exotel answered without a call id")
        return str(sid)


def make_bridge(settings: Settings) -> CallBridge:
    if settings.call_provider == "exotel":
        return ExotelBridge(settings)
    if settings.environment == "production":
        raise CallError("CALL_PROVIDER=console only prints calls: set up Exotel (docs/notifications-setup.md)")
    return ConsoleBridge()
