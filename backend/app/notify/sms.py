"""SMS for login codes and notifications. SMS_PROVIDER=console (default) prints the code or message for local
development and tests; msg91 sends through MSG91 with DLT-registered templates (the OTP template for codes, the
transactional templates of app.notify.templates for notifications) and is built only when its keys are set.

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


class SmsSendError(SmsError):
    """A notification SMS that did not go out. retry: a temporary problem (network, MSG91 down): try again later."""

    def __init__(self, message: str, retry: bool):
        super().__init__(message)
        self.retry = retry


class SmsSender(Protocol):
    def send_otp(self, phone: str, code: str) -> None: ...

    def send_template(self, phone: str, template_id: str, values: list[str], text: str) -> str:
        """Send a DLT template with its values (in order); `text` is what it reads (for the console). Returns the
        provider's id. Raises SmsSendError."""
        ...


class ConsoleSms:
    """Development and the free demo: prints the code so you can log in without an SMS account. The phone number is
    masked to its last 4 digits (the demo's logs are on a hosted service)."""

    name = "console"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []  # login codes: (phone, code)
        self.messages: list[tuple[str, str]] = []  # notifications: (phone, text)

    def send_otp(self, phone: str, code: str) -> None:
        self.sent.append((phone, code))
        to = mask_phone(phone)
        print(f"\n[console SMS] to {to}: Your Instant Mechanic login code is {code}. It expires in 5 minutes.\n")

    def send_template(self, phone: str, template_id: str, values: list[str], text: str) -> str:
        self.messages.append((phone, text))
        log.warning("SMS (console provider) to %s, template %s: %s", mask_phone(phone), template_id or "-", text)
        return f"console-sms-{len(self.messages)}"


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

    FLOW_URL = "https://control.msg91.com/api/v5/flow"

    def flow_request(self, phone: str, template_id: str, values: list[str]) -> urllib.request.Request:
        """MSG91 Flow API: the template (MSG91's id of a DLT-approved template) and its values VAR1, VAR2 ..."""
        recipient = {"mobiles": phone.lstrip("+"), **{f"VAR{i}": v for i, v in enumerate(values, start=1)}}
        body = {"template_id": template_id, "short_url": "0", "recipients": [recipient]}
        return urllib.request.Request(
            self.FLOW_URL,
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "authkey": self.s.msg91_auth_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def send_template(self, phone: str, template_id: str, values: list[str], text: str) -> str:
        try:
            with urllib.request.urlopen(self.flow_request(phone, template_id, values), timeout=10) as res:  # noqa: S310
                body = json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            retry = e.code == 429 or e.code >= 500
            log.warning("MSG91 flow send to %s failed: HTTP %s", mask_phone(phone), e.code)
            raise SmsSendError(f"MSG91 answered HTTP {e.code}", retry=retry) from None
        except (OSError, ValueError) as e:
            log.warning("MSG91 flow send to %s failed: %s", mask_phone(phone), type(e).__name__)
            raise SmsSendError(f"MSG91 not reachable ({type(e).__name__})", retry=True) from None
        if body.get("type") != "success":
            reason = str(body.get("message", "no message"))[:200]
            log.warning("MSG91 refused an SMS to %s: %s", mask_phone(phone), reason)
            raise SmsSendError(f"MSG91 refused the message: {reason}", retry=False)
        return str(body.get("message") or "")


def make_sms(settings: Settings) -> SmsSender:
    if settings.sms_provider == "msg91":
        return Msg91Sms(settings)
    if settings.environment == "production":
        raise SmsError("SMS_PROVIDER=console prints login codes: not allowed in production")
    return ConsoleSms()
