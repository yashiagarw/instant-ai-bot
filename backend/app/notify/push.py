"""Web push (the browser's own notifications, RFC 8030 / 8291 / 8292) with VAPID keys. PUSH_PROVIDER=console prints;
webpush encrypts the message for each browser (aes128gcm, http-ece) and posts it to the browser's push service.

    uv run python -m app.notify.push keys      # a new VAPID key pair for backend/.env (VAPID_PUBLIC_KEY / _PRIVATE_KEY)

Subscription endpoints come from browsers, so only HTTPS endpoints of the known push services are accepted
(allowed_endpoint): the worker never posts to an address a visitor made up.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.config import Settings

log = logging.getLogger(__name__)

# Push services of Chrome / Edge / Android (FCM), Firefox, Safari (Apple) and Windows.
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com", "notify.windows.com")
TTL_SECONDS = 12 * 3600


def allowed_endpoint(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass
class Target:
    """One browser subscription."""

    id: int
    endpoint: str
    p256dh: str
    auth: str


class PushError(RuntimeError):
    def __init__(self, message: str, retry: bool, gone: bool = False):
        super().__init__(message)
        self.retry = retry
        self.gone = gone  # the subscription no longer exists: stop using it


class ConsolePush:
    name = "console"

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    def send(self, target: Target, payload: dict) -> None:
        self.sent.append((target.endpoint, payload))
        log.warning("PUSH (console provider) to subscription %s: %s", target.id, payload.get("body"))


class WebPush:
    name = "webpush"

    def __init__(self, settings: Settings) -> None:
        from py_vapid import Vapid02

        needed = {"VAPID_PUBLIC_KEY": settings.vapid_public_key, "VAPID_PRIVATE_KEY": settings.vapid_private_key}
        missing = [name for name, value in needed.items() if not value]
        if missing:
            raise PushError(f"PUSH_PROVIDER=webpush needs {', '.join(missing)}", retry=False)
        self.vapid = Vapid02.from_raw(settings.vapid_private_key.encode())
        self.subject = settings.vapid_subject

    def request_for(self, target: Target, payload: dict) -> urllib.request.Request:
        import http_ece
        from cryptography.hazmat.primitives.asymmetric import ec

        if not allowed_endpoint(target.endpoint):
            raise PushError("not a known push service endpoint", retry=False, gone=True)
        body = http_ece.encrypt(
            json.dumps(payload).encode(),
            private_key=ec.generate_private_key(ec.SECP256R1()),
            dh=b64url_decode(target.p256dh),
            auth_secret=b64url_decode(target.auth),
            version="aes128gcm",
        )
        parts = urlsplit(target.endpoint)
        claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(time.time()) + TTL_SECONDS, "sub": self.subject}
        headers = {
            **self.vapid.sign(claims),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(TTL_SECONDS),
            "Urgency": "high",
        }
        return urllib.request.Request(target.endpoint, data=body, method="POST", headers=headers)

    def send(self, target: Target, payload: dict) -> None:
        try:
            with urllib.request.urlopen(self.request_for(target, payload), timeout=10):  # noqa: S310 - allow-listed
                return
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise PushError(f"subscription gone (HTTP {e.code})", retry=False, gone=True) from None
            raise PushError(f"push service answered HTTP {e.code}", retry=e.code == 429 or e.code >= 500) from None
        except OSError as e:
            raise PushError(f"push service not reachable ({type(e).__name__})", retry=True) from None


def generate_keys() -> tuple[str, str]:
    """(public key for browsers: uncompressed P-256 point, private key: raw 32 bytes), both base64url."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    private = key.private_numbers().private_value.to_bytes(32, "big")
    return b64url_encode(public), b64url_encode(private)


if __name__ == "__main__":
    if sys.argv[1:] != ["keys"]:
        sys.exit("usage: python -m app.notify.push keys")
    pub, priv = generate_keys()
    print("# Web push (VAPID) keys: paste into backend/.env (or backend/.env.prod) and set PUSH_PROVIDER=webpush.")
    print("# Keep the private key secret; changing the pair means every browser has to turn alerts on again.")
    print(f"VAPID_PUBLIC_KEY={pub}")
    print(f"VAPID_PRIVATE_KEY={priv}")
