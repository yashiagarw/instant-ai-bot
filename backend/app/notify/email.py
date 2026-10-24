"""Email alerts behind one small interface. Providers: console (development), SMTP and Resend.

Personal details go only to the support address, under the customer's consent to share them with the team.
"""

import json
import logging
import smtplib
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import Protocol

from app.config import Settings

log = logging.getLogger(__name__)


@dataclass
class Email:
    to: str
    subject: str
    text: str


class EmailError(RuntimeError):
    pass


class EmailSender(Protocol):
    def send(self, email: Email) -> None: ...


class ConsoleSender:
    """Prints the email to the API log. The default for development: nothing leaves the machine."""

    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, email: Email) -> None:
        self.sent.append(email)
        log.warning("EMAIL (console provider) to=%s subject=%s\n%s", email.to, email.subject, email.text)


class SmtpSender:
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host:
            raise EmailError("EMAIL_PROVIDER=smtp needs SMTP_HOST")
        self.s = settings

    def send(self, email: Email) -> None:
        msg = MimeMessage()
        msg["From"], msg["To"], msg["Subject"] = self.s.email_from, email.to, email.subject
        msg.set_content(email.text)
        try:
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=10) as smtp:
                if self.s.smtp_starttls:
                    smtp.starttls()
                if self.s.smtp_username:
                    smtp.login(self.s.smtp_username, self.s.smtp_password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            raise EmailError(f"SMTP send failed: {e}") from e


class ResendSender:
    URL = "https://api.resend.com/emails"

    def __init__(self, settings: Settings) -> None:
        if not settings.resend_api_key:
            raise EmailError("EMAIL_PROVIDER=resend needs RESEND_API_KEY")
        self.s = settings

    def send(self, email: Email) -> None:
        body = json.dumps({"from": self.s.email_from, "to": [email.to], "subject": email.subject, "text": email.text})
        req = urllib.request.Request(
            self.URL,
            data=body.encode(),
            method="POST",
            headers={"Authorization": f"Bearer {self.s.resend_api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:  # noqa: S310 - fixed https URL
                if res.status >= 300:
                    raise EmailError(f"Resend answered {res.status}")
        except OSError as e:
            raise EmailError(f"Resend send failed: {e}") from e


def make_sender(settings: Settings) -> EmailSender:
    if settings.email_provider == "smtp":
        return SmtpSender(settings)
    if settings.email_provider == "resend":
        return ResendSender(settings)
    return ConsoleSender()
