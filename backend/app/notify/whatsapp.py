"""WhatsApp: WHATSAPP_PROVIDER=console prints; cloud sends through Meta's WhatsApp Cloud API.

Business-initiated messages are approved templates (names in WHATSAPP_TPL_*, each with "en" and "hi" translations).
The job offer template has two quick-reply buttons whose payloads we set per message ("offer:<assignment>:accept" /
"...:reject"); a press comes back on the webhook. Replies right after someone writes to us are plain text (allowed
for 24 hours after their message).

Webhook (/api/webhooks/whatsapp): GET answers Meta's verification with hub.challenge when hub.verify_token matches
WHATSAPP_VERIFY_TOKEN; POST bodies are signed by Meta with the app secret (X-Hub-Signature-256: sha256=<hex HMAC of
the raw body>), checked before anything is read. parse_webhook() turns a body into the few facts we keep.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from app.config import Settings
from app.notify.sms import mask_phone

log = logging.getLogger(__name__)
KEYWORDS = {"STOP": "stop", "UNSUBSCRIBE": "stop", "START": "start", "SUBSCRIBE": "start"}
# WhatsApp error codes worth retrying: rate limits and temporary errors (the rest are permanent for this message).
RETRY_CODES = {4, 80007, 130429, 131000, 131016, 131048, 131056, 133004}


class WhatsappError(RuntimeError):
    def __init__(self, message: str, retry: bool):
        super().__init__(message)
        self.retry = retry


@dataclass
class Outgoing:
    phone: str  # +91XXXXXXXXXX
    text: str  # what it reads (console; plain-text replies)
    template_name: str | None = None  # approved template (business-initiated), else a plain-text reply
    language: str = "en"
    values: list[str] = field(default_factory=list)  # body {{1}}, {{2}} ...
    buttons: list[tuple[str, str]] = field(default_factory=list)  # (payload, label) quick replies, in order


class ConsoleWhatsapp:
    name = "console"

    def __init__(self) -> None:
        self.sent: list[Outgoing] = []

    def send(self, msg: Outgoing) -> str:
        self.sent.append(msg)
        buttons = " ".join(f"[{label}]" for _, label in msg.buttons)
        log.warning("WHATSAPP (console provider) to %s: %s %s", mask_phone(msg.phone), msg.text, buttons)
        return f"console-wa-{len(self.sent)}"


class CloudWhatsapp:
    name = "whatsapp_cloud"

    def __init__(self, settings: Settings) -> None:
        needed = {
            "WHATSAPP_TOKEN": settings.whatsapp_token,
            "WHATSAPP_PHONE_NUMBER_ID": settings.whatsapp_phone_number_id,
        }
        missing = [name for name, value in needed.items() if not value]
        if missing:
            raise WhatsappError(f"WHATSAPP_PROVIDER=cloud needs {', '.join(missing)}", retry=False)
        self.s = settings
        self.url = (
            f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
        )

    @staticmethod
    def body_for(msg: Outgoing) -> dict:
        to = msg.phone.lstrip("+")
        if not msg.template_name:
            return {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": msg.text}}
        components: list[dict] = []
        if msg.values:
            components.append({"type": "body", "parameters": [{"type": "text", "text": v} for v in msg.values]})
        for i, (payload, _label) in enumerate(msg.buttons):
            components.append(
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(i),
                    "parameters": [{"type": "payload", "payload": payload}],
                }
            )
        return {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {"name": msg.template_name, "language": {"code": msg.language}, "components": components},
        }

    def send(self, msg: Outgoing) -> str:
        req = urllib.request.Request(
            self.url,
            data=json.dumps(self.body_for(msg)).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {self.s.whatsapp_token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:  # noqa: S310 - fixed https URL
                body = json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            code, title = _graph_error(e)
            retry = e.code == 429 or e.code >= 500 or code in RETRY_CODES
            log.warning("WhatsApp send to %s failed: HTTP %s, error %s %s", mask_phone(msg.phone), e.code, code, title)
            raise WhatsappError(f"WhatsApp error {code or e.code}: {title}", retry=retry) from None
        except (OSError, ValueError) as e:
            raise WhatsappError(f"WhatsApp not reachable ({type(e).__name__})", retry=True) from None
        messages = body.get("messages") or []
        if not messages:
            raise WhatsappError("WhatsApp answered without a message id", retry=False)
        return str(messages[0].get("id", ""))


def _graph_error(e: urllib.error.HTTPError) -> tuple[int | None, str]:
    try:
        err = json.loads(e.read() or b"{}").get("error", {})
        return err.get("code"), str(err.get("error_user_title") or err.get("message") or "")[:200]
    except (ValueError, OSError):
        return None, ""


# ---------------------------------------------------------------- webhook


def signature_ok(app_secret: str, body: bytes, header: str | None) -> bool:
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def verify_challenge(settings: Settings, mode: str | None, token: str | None) -> bool:
    return (
        mode == "subscribe"
        and bool(settings.whatsapp_verify_token)
        and token is not None
        and hmac.compare_digest(token, settings.whatsapp_verify_token)
    )


@dataclass
class Inbound:
    """One fact from a webhook body. `phone` is the sender's number (+91...), used only to hash and mask it."""

    message_id: str
    kind: str  # button, text, status
    phone: str | None
    data: dict


def parse_webhook(body: dict) -> list[Inbound]:
    """Button presses, STOP / START messages and delivery statuses. Anything else (other text, media) is dropped:
    we never keep what people write to us."""
    out: list[Inbound] = []
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for m in value.get("messages") or []:
                phone = "+" + str(m.get("from", "")).lstrip("+") if m.get("from") else None
                mid = str(m.get("id") or "")
                if not mid:
                    continue
                if m.get("type") == "button":
                    btn = m.get("button") or {}
                    context = (m.get("context") or {}).get("id")
                    out.append(
                        Inbound(mid, "button", phone, {"payload": btn.get("payload", ""), "context_id": context})
                    )
                elif m.get("type") == "interactive" and (m.get("interactive") or {}).get("type") == "button_reply":
                    reply = m["interactive"]["button_reply"]
                    out.append(Inbound(mid, "button", phone, {"payload": reply.get("id", ""), "context_id": None}))
                elif m.get("type") == "text":
                    word = str((m.get("text") or {}).get("body", "")).strip().upper()
                    if word in KEYWORDS:
                        out.append(Inbound(mid, "text", phone, {"keyword": KEYWORDS[word]}))
            for st in value.get("statuses") or []:
                wamid, status = str(st.get("id") or ""), str(st.get("status") or "")
                if wamid and status:
                    errors = st.get("errors") or []
                    error = f"{errors[0].get('code')}: {errors[0].get('title', '')}" if errors else ""
                    data = {"wamid": wamid, "status": status, "error": error[:200]}
                    out.append(Inbound(f"{wamid}:{status}", "status", None, data))
    return out
