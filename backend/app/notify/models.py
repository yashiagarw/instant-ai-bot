"""Notification tables (Phase 5.2). Privacy: no full phone number is ever stored here. Recipients are user / mechanic
/ request ids with a masked number (+91******3210); opt-ins and WhatsApp senders keep a keyed hash of the number
(HMAC with AUTH_SECRET), which can be compared but not read back. Message text is not stored either: the template,
its language and the non-personal values it was filled with are."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin, str_enum


class Channel(StrEnum):
    whatsapp = "whatsapp"
    sms = "sms"
    push = "push"  # web push (VAPID) to the browsers the customer turned alerts on in
    email = "email"


class RecipientType(StrEnum):
    customer = "customer"  # the person who made the request (account or not)
    mechanic = "mechanic"
    support = "support"  # the support inbox (SUPPORT_EMAIL)


class NotificationStatus(StrEnum):
    queued = "queued"  # waiting for the worker (or its next retry)
    sent = "sent"  # the provider accepted it
    delivered = "delivered"  # the provider says it reached the phone (WhatsApp status webhook)
    read = "read"
    failed = "failed"  # gave up on this channel (the next channel, if any, has its own row)
    skipped = "skipped"  # this channel could not be used (not configured, no template id, no opt-in ...)


class Notification(CreatedAtMixin, Base):
    """One message to one recipient on one channel. A fallback to the next channel is a new row (previous_id)."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_due", "next_attempt_at", postgresql_where="status = 'queued'"),
        Index("uq_notifications_dedupe_key", "dedupe_key", unique=True, postgresql_where="dedupe_key IS NOT NULL"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(Text)  # submitted, offered, accepted, en_route, arrived, completed, escalated
    template: Mapped[str] = mapped_column(Text)  # app/notify/templates.py key
    language: Mapped[str] = mapped_column(String(5), default="en", server_default="en")
    recipient_type: Mapped[RecipientType] = mapped_column(str_enum(RecipientType, "recipient_type"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    mechanic_id: Mapped[int | None] = mapped_column(ForeignKey("mechanics.id", ondelete="SET NULL"))
    recipient_masked: Mapped[str] = mapped_column(Text, default="", server_default="")  # +91******3210 / s***@x.in
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"))
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus, "status"), default=NotificationStatus.queued, server_default="queued"
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str | None] = mapped_column(Text)  # console, msg91, whatsapp_cloud, webpush, smtp, resend
    provider_id: Mapped[str | None] = mapped_column(Text)  # the provider's message id (WhatsApp wamid, MSG91 id)
    error: Mapped[str | None] = mapped_column(Text)
    # Values the template is filled with: reference, first names, area ... never a phone number (masked first).
    params: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    # Channels still to try, in order, if this one is skipped or fails.
    fallback: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    previous_id: Mapped[int | None] = mapped_column(ForeignKey("notifications.id", ondelete="SET NULL"))
    # One notification per event and recipient, however often the event is replayed.
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationOptin(Base):
    """Consent to a channel that needs it (WhatsApp): who, the exact wording and its version, when and how. Withdrawn
    rows are kept (withdrawn_at). Exactly one subject: an account, a request (customers without an account) or a
    mechanic."""

    __tablename__ = "notification_optins"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL)::int + (request_id IS NOT NULL)::int + (mechanic_id IS NOT NULL)::int = 1",
            name="one_subject",
        ),
        CheckConstraint("length(consent_text) > 0 AND length(consent_text_version) > 0", name="wording_recorded"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), index=True
    )
    mechanic_id: Mapped[int | None] = mapped_column(ForeignKey("mechanics.id", ondelete="CASCADE"), index=True)
    # HMAC of the number that agreed: the opt-in only counts for that number, and STOP from it withdraws it.
    phone_hash: Mapped[str] = mapped_column(String(64), index=True)
    consent_text_version: Mapped[str] = mapped_column(Text)
    consent_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)  # request_form, account_page, whatsapp_keyword, staff_call
    recorded_by: Mapped[str] = mapped_column(Text, default="", server_default="")  # staff label for staff_call
    opted_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_source: Mapped[str | None] = mapped_column(Text)


class NotificationPreference(Base):
    """A customer's choice per channel (no row = on). Turning a channel off never touches the opt-in record."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"), primary_key=True)
    enabled: Mapped[bool] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PushSubscription(CreatedAtMixin, Base):
    """A browser that turned alerts on: its account, or its anonymous cookie (hash) until the customer logs in."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "user_id IS NOT NULL OR anon_key_hash IS NOT NULL OR mechanic_id IS NOT NULL", name="has_owner"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    anon_key_hash: Mapped[str | None] = mapped_column(Text, index=True)
    # A mechanic's phone with the app (/m): job offers arrive as alerts (Phase 5.3).
    mechanic_id: Mapped[int | None] = mapped_column(ForeignKey("mechanics.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the push service said it is gone


class InboundStatus(StrEnum):
    pending = "pending"
    done = "done"
    ignored = "ignored"  # nothing to do (repeat press, offer closed, unknown sender ...): `result` says why
    failed = "failed"


class WhatsappInbound(Base):
    """What the WhatsApp webhook received, stored before answering 200 and handled by the worker. message_id is
    unique (Meta retries deliveries): a message is handled once. Status updates use "<wamid>:<status>"."""

    __tablename__ = "whatsapp_inbound"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text)  # button, text, status
    from_hash: Mapped[str | None] = mapped_column(String(64))
    from_masked: Mapped[str] = mapped_column(Text, default="", server_default="")
    # button: {"payload", "context_id"}; text: {"keyword"} (STOP / START only, never the message); status:
    # {"wamid", "status", "error"}
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[InboundStatus] = mapped_column(
        str_enum(InboundStatus, "status"), default=InboundStatus.pending, server_default="pending"
    )
    result: Mapped[str] = mapped_column(Text, default="", server_default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
