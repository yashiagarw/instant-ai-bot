"""SMS for login codes. SMS_PROVIDER=console (default) prints the code for local development and tests; msg91 sends
through MSG91 with a DLT-registered OTP template and is built only when its keys are set.

Nothing outside the console provider ever logs a full phone number or a code: use mask_phone() in logs.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from app.config import Settings

log = logging.getLogger(__name__)


class SmsError(RuntimeError):
    pass


def mask_phone(phone: str) -> str:
    """+919876543210 -> +91******3210 (for logs)."""
    digits = phone[-4:] if len(phone) >= 4 else ""
    return f"+91******{digits}"


class SmsSender(Protocol):
    def send_otp(self, phone: str, code: str) -> None: ...


class ConsoleSms:
    """Development only: prints the full code so you can log in without an SMS account."""

    name = "console"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_otp(self, phone: str, code: str) -> None:
        self.sent.append((phone, code))
        print(f"\n[console SMS] to {phone}: Your Instant Mechanic login code is {code}. It expires in 5 minutes.\n")


class Msg91Sms:
    """MSG91 OTP API (https://control.msg91.com/api/v5/otp): MSG91 sends our code with the DLT template."""

    name = "msg91"
    URL = "https://control.msg91.com/api/v5/otp"

    def __init__(self, settings: Settings) -> None:
        missing = [
            name
            for name, value in (
                ("MSG91_AUTH_KEY", settings.msg91_auth_key),
                ("MSG91_TEMPLATE_ID", settings.msg91_template_id),
                ("MSG91_SENDER_ID", settings.msg91_sender_id),
            )
            if not value
        ]
        if missing:
            raise SmsError(f"SMS_PROVIDER=msg91 needs {', '.join(missing)}")
        self.s = settings

    def request_for(self, phone: str, code: str) -> urllib.request.Request:
        query = urllib.parse.urlencode(
            {
                "template_id": self.s.msg91_template_id,
                "mobile": phone.lstrip("+"),
                "otp": code,
                "sender": self.s.msg91_sender_id,
            }
        )
        return urllib.request.Request(
            f"{self.URL}?{query}",
            data=json.dumps({"OTP": code}).encode(),
            method="POST",
            headers={
                "authkey": self.s.msg91_auth_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def send_otp(self, phone: str, code: str) -> None:
        try:
            with urllib.request.urlopen(self.request_for(phone, code), timeout=10) as res:  # noqa: S310 - fixed https URL
                body = json.loads(res.read() or b"{}")
        except (OSError, ValueError) as e:
            log.warning("MSG91 send to %s failed: %s", mask_phone(phone), type(e).__name__)
            raise SmsError("MSG91 send failed") from None  # the error holds the URL, which carries the code
        if body.get("type") != "success":
            log.warning("MSG91 refused a send to %s: %s", mask_phone(phone), body.get("message", "no message"))
            raise SmsError("MSG91 refused the message")


def make_sms(settings: Settings) -> SmsSender:
    if settings.sms_provider == "msg91":
        return Msg91Sms(settings)
    if settings.environment == "production":
        raise SmsError("SMS_PROVIDER=console prints login codes: not allowed in production")
    return ConsoleSms()
