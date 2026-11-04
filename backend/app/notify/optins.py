"""Opt-ins: consent to WhatsApp messages, with the exact wording, its version, the time and the source. An opt-in is
for one number (phone_hash, an HMAC with AUTH_SECRET): it stops counting if the number changes, and STOP sent from
that number withdraws it. Withdrawn rows are kept with withdrawn_at."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.notify.models import Channel, NotificationOptin

# Customers: shown next to an unticked box on the request form and on the account page.
WHATSAPP_CUSTOMER_VERSION = "whatsapp-customer-v1"
WHATSAPP_CUSTOMER_TEXT = (
    "Send me updates about my mechanic request on WhatsApp from Instant Mechanic (mechanic assigned, on the way, "
    "arrived, job done). I can stop them at any time by sending STOP."
)
# Mechanics: read to them by the support agent on a call, or agreed by sending START to our WhatsApp number.
WHATSAPP_MECHANIC_VERSION = "whatsapp-mechanic-v1"
WHATSAPP_MECHANIC_TEXT = (
    "I agree to get job offers from Instant Mechanic on WhatsApp, with Accept and Reject buttons. I can stop them "
    "at any time by sending STOP."
)


class OptinError(ValueError):
    pass


def phone_hash(settings: Settings, phone: str) -> str:
    return hmac.new(settings.auth_secret.encode(), f"notify-phone|{phone}".encode(), hashlib.sha256).hexdigest()


def record(
    session: Session,
    settings: Settings,
    *,
    phone: str,
    source: str,
    user_id: uuid.UUID | None = None,
    request_id: uuid.UUID | None = None,
    mechanic_id: int | None = None,
    version: str,
    recorded_by: str = "",
) -> NotificationOptin:
    """A new WhatsApp opt-in (a previous active one for the same subject is closed: the latest wording counts)."""
    wording = {WHATSAPP_CUSTOMER_VERSION: WHATSAPP_CUSTOMER_TEXT, WHATSAPP_MECHANIC_VERSION: WHATSAPP_MECHANIC_TEXT}
    if version not in wording:
        raise OptinError("the WhatsApp wording has changed; please reload the page and tick the box again")
    withdraw(session, user_id=user_id, request_id=request_id, mechanic_id=mechanic_id, source="replaced")
    row = NotificationOptin(
        channel=Channel.whatsapp,
        user_id=user_id,
        request_id=request_id,
        mechanic_id=mechanic_id,
        phone_hash=phone_hash(settings, phone),
        consent_text_version=version,
        consent_text=wording[version],
        source=source,
        recorded_by=recorded_by,
        opted_in_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def _subject(user_id=None, request_id=None, mechanic_id=None):
    if user_id is not None:
        return NotificationOptin.user_id == user_id
    if request_id is not None:
        return NotificationOptin.request_id == request_id
    if mechanic_id is not None:
        return NotificationOptin.mechanic_id == mechanic_id
    raise OptinError("no subject")


def withdraw(session: Session, *, source: str, user_id=None, request_id=None, mechanic_id=None) -> int:
    return session.execute(
        update(NotificationOptin)
        .where(
            _subject(user_id, request_id, mechanic_id),
            NotificationOptin.channel == Channel.whatsapp,
            NotificationOptin.withdrawn_at.is_(None),
        )
        .values(withdrawn_at=datetime.now(UTC), withdrawn_source=source)
    ).rowcount


def active(session: Session, settings: Settings, phone: str, *, user_id=None, request_id=None, mechanic_id=None):
    """The active WhatsApp opt-in of any of the given subjects for this number, or None."""
    subjects = []
    if user_id is not None:
        subjects.append(NotificationOptin.user_id == user_id)
    if request_id is not None:
        subjects.append(NotificationOptin.request_id == request_id)
    if mechanic_id is not None:
        subjects.append(NotificationOptin.mechanic_id == mechanic_id)
    if not subjects or not phone:
        return None
    return session.scalar(
        select(NotificationOptin)
        .where(
            or_(*subjects),
            NotificationOptin.channel == Channel.whatsapp,
            NotificationOptin.withdrawn_at.is_(None),
            NotificationOptin.phone_hash == phone_hash(settings, phone),
        )
        .order_by(NotificationOptin.opted_in_at.desc())
        .limit(1)
    )
