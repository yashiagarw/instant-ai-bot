"""The notification service. One entry point, notify(): it records the notification (queued) in the caller's
transaction, and after commit the arq worker sends it (send()), with retries and channel fallback.

Triggers (request events, app/requests/workflow.py and app/requests/service.py):
    submitted  -> support    request_submitted   (email: the existing support alert)
    offered    -> mechanic   job_offer           (WhatsApp with Accept / Reject buttons, else SMS)
    accepted   -> customer   mechanic_assigned
    en_route   -> customer   mechanic_en_route
    arrived    -> customer   mechanic_arrived
    completed  -> customer   job_completed
    escalated  -> support    request_escalated   (email)

Channels per recipient come from NOTIFY_*_CHANNELS (in order), keeping only those the recipient can get: WhatsApp
needs an active opt-in for the number, push a browser with alerts on, and a customer can turn SMS or push off. If
a channel is not configured (missing credentials or template id) the row is marked skipped with the reason, logged,
and the next channel gets a row of its own; temporary errors are retried (NOTIFY_MAX_ATTEMPTS, backoff from
NOTIFY_RETRY_BASE_SECONDS), permanent ones fail over at once.

Privacy: rows keep ids and masked numbers only; the number is read from the request / mechanic / account at send
time. Logs name notifications by id and masked number.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.notify import optins
from app.notify import templates as T
from app.notify.channels import ChannelProvider, Message, SendFailed
from app.notify.email import Email
from app.notify.models import (
    Channel,
    Notification,
    NotificationPreference,
    NotificationStatus,
    PushSubscription,
    RecipientType,
)
from app.notify.push import Target
from app.notify.queue import after_commit_enqueue, send_job
from app.notify.sms import mask_phone

log = logging.getLogger(__name__)
ST = NotificationStatus
SUPPORT_TEMPLATES = {"request_submitted", "request_escalated"}  # email only (English), built from the request
STATUS_EVENTS = {  # request status -> (template, recipient)
    "offered": ("job_offer", RecipientType.mechanic),
    "accepted": ("mechanic_assigned", RecipientType.customer),
    "en_route": ("mechanic_en_route", RecipientType.customer),
    "arrived": ("mechanic_arrived", RecipientType.customer),
    "completed": ("job_completed", RecipientType.customer),
    "escalated": ("request_escalated", RecipientType.support),
}

_settings: Settings | None = None


def use_settings(settings: Settings | None) -> None:
    """The API (create_app) and the worker set their settings here; request events read them."""
    global _settings
    _settings = settings


def current_settings() -> Settings:
    return _settings or get_settings()


def mask_email(address: str) -> str:
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}" if domain else "***"


def configured(settings: Settings, recipient: RecipientType) -> list[Channel]:
    raw = {
        RecipientType.customer: settings.notify_customer_channels,
        RecipientType.mechanic: settings.notify_mechanic_channels,
        RecipientType.support: settings.notify_support_channels,
    }[recipient]
    known = {c.value for c in Channel}
    return [Channel(c) for c in dict.fromkeys(x.strip() for x in raw.split(",")) if c in known]


# ---------------------------------------------------------------- who can get what


def _push_targets(session: Session, user_id, anon_key_hash, mechanic_id=None) -> list[PushSubscription]:
    owners = []
    if mechanic_id is not None:
        owners.append(PushSubscription.mechanic_id == mechanic_id)
    if user_id is not None:
        owners.append(PushSubscription.user_id == user_id)
    if anon_key_hash:
        owners.append(PushSubscription.anon_key_hash == anon_key_hash)
    if not owners:
        return []
    return list(session.scalars(select(PushSubscription).where(or_(*owners), PushSubscription.revoked_at.is_(None))))


def preferences(session: Session, user_id) -> dict[Channel, bool]:
    if user_id is None:
        return {}
    rows = session.scalars(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    return {Channel(p.channel): p.enabled for p in rows}


def plan(session: Session, settings: Settings, recipient: RecipientType, req, mechanic=None) -> tuple[list, list]:
    """(channels to try in order, [why each other configured channel is left out])."""
    ok, why = [], []
    prefs = preferences(session, req.user_id) if recipient == RecipientType.customer and req is not None else {}
    for ch in configured(settings, recipient):
        reason = None
        if prefs.get(ch) is False:
            reason = "turned off by the customer"
        elif recipient == RecipientType.support:
            reason = None if ch == Channel.email else "support gets email only"
        elif ch == Channel.email:
            reason = "no email address"
        elif recipient == RecipientType.mechanic:
            if ch == Channel.push and not _push_targets(session, None, None, mechanic.id):
                reason = "no phone with the mechanic app's alerts on"
            elif ch == Channel.whatsapp and not optins.active(
                session, settings, mechanic.phone, mechanic_id=mechanic.id
            ):
                reason = "no WhatsApp opt-in"
        elif ch == Channel.whatsapp and not optins.active(
            session, settings, req.phone, user_id=req.user_id, request_id=req.id
        ):
            reason = "no WhatsApp opt-in"
        elif ch == Channel.push and not _push_targets(session, req.user_id, req.anon_key_hash):
            reason = "no browser with alerts on"
        if reason:
            why.append(f"{ch}: {reason}")
        else:
            ok.append(ch)
    return ok, why


# ---------------------------------------------------------------- notify()


def notify(
    session: Session,
    *,
    event: str,
    template: str,
    recipient: RecipientType,
    request=None,
    mechanic=None,
    user_id: uuid.UUID | None = None,
    params: dict | None = None,
    language: str = "en",
    channels: list[Channel] | None = None,
    dedupe_key: str | None = None,
    settings: Settings | None = None,
) -> Notification:
    """Record a notification and send it through the worker after the caller commits. `channels` overrides the
    plan (WhatsApp replies). Returns the first row (status skipped when no channel can be used)."""
    settings = settings or current_settings()
    if dedupe_key:
        existing = session.scalar(select(Notification).where(Notification.dedupe_key == dedupe_key))
        if existing is not None:
            return existing
    if channels is None:
        channels, why = plan(session, settings, recipient, request, mechanic)
    else:
        why = []
    clean = {k: (T.clean_value(v) if isinstance(v, str) else v) for k, v in (params or {}).items()}
    if recipient == RecipientType.support:
        masked = mask_email(settings.support_email) if settings.support_email else ""
    elif recipient == RecipientType.mechanic:
        masked = mask_phone(mechanic.phone)
    else:
        phone = request.phone if request is not None else _user_phone(session, user_id)
        masked = mask_phone(phone) if phone else ""
    row = Notification(
        request_id=getattr(request, "id", None),
        event=event,
        template=template,
        language=language if language in T.LANGUAGES else "en",
        recipient_type=recipient,
        user_id=user_id if user_id is not None else getattr(request, "user_id", None),
        mechanic_id=getattr(mechanic, "id", None),
        recipient_masked=masked,
        channel=channels[0] if channels else (configured(settings, recipient) or [Channel.sms])[0],
        params=clean,
        fallback=[c.value for c in channels[1:]],
        dedupe_key=dedupe_key,
        next_attempt_at=datetime.now(UTC),
    )
    if not channels:
        row.status, row.error = ST.skipped, "no channel: " + ("; ".join(why) or "none configured")
        log.warning("Notification %s for %s %s not sent: %s", template, recipient, masked, row.error)
    session.add(row)
    session.flush()
    if channels:
        after_commit_enqueue(session, send_job(row.id, 0))
    return row


def _user_phone(session: Session, user_id) -> str | None:
    if user_id is None:
        return None
    from app.accounts.models import User

    user = session.get(User, user_id)
    return user.phone if user else None


# ---------------------------------------------------------------- request events


def customer_language(session: Session, req) -> str:
    """The language the customer picked on the site (Phase 5.5) when the request has one; else from the diagnosis:
    what the customer typed (Hindi / Hinglish -> hi), else English."""
    picked = getattr(req, "language", None)
    if picked in T.LANGUAGES:
        return picked
    if req.session_id is None:
        return "en"
    from app.diagnosis.models import EventType, SessionEvent
    from app.llm.phrasing import detect_language

    texts = session.scalars(
        select(SessionEvent.payload)
        .where(SessionEvent.session_id == req.session_id, SessionEvent.event_type == EventType.free_text)
        .order_by(SessionEvent.id.desc())
        .limit(1)
    ).all()
    text = str((texts[0] or {}).get("text", "")) if texts else ""
    return T.language_of(detect_language(text))


def _car(req) -> str:
    v = req.vehicle_snapshot or {}
    return " ".join(str(x) for x in (v.get("make"), v.get("model"), v.get("fuel")) if x) or "not given"


def _problem(req) -> str:
    return (req.problem_summary or "").split(" · ")[0] or "see details from support"


def on_submitted(session: Session, req) -> Notification:
    return notify(
        session,
        event="submitted",
        template="request_submitted",
        recipient=RecipientType.support,
        request=req,
        params={"reference": req.reference, "urgent": req.urgent},
        dedupe_key=f"request:{req.id}:submitted:support",
    )


def on_status(session: Session, req, to: str, request_event) -> Notification | None:
    """Called by workflow.move() for every status change, in the same transaction."""
    found = STATUS_EVENTS.get(str(to))
    if found is None:
        return None
    template, recipient = found
    from app.mechanics.models import Mechanic
    from app.requests.models import AssignmentStatus, RequestAssignment

    settings = current_settings()
    key = f"request:{req.id}:event:{request_event.id}:{recipient}"
    if recipient == RecipientType.support:
        return notify(
            session,
            event=str(to),
            template=template,
            recipient=recipient,
            request=req,
            params={"reference": req.reference, "note": request_event.note or ""},
            dedupe_key=key,
        )
    assignment = session.scalar(
        select(RequestAssignment)
        .where(
            RequestAssignment.request_id == req.id,
            RequestAssignment.status.in_(
                [AssignmentStatus.offered, AssignmentStatus.accepted, AssignmentStatus.completed]
            ),
        )
        .order_by(RequestAssignment.id.desc())
        .limit(1)
    )
    mechanic = session.get(Mechanic, assignment.mechanic_id) if assignment else None
    if recipient == RecipientType.mechanic:
        if mechanic is None:
            return None
        area = ", ".join(x for x in (req.area_text, req.pincode) if x)
        return notify(
            session,
            event=str(to),
            template=template,
            recipient=recipient,
            request=req,
            mechanic=mechanic,
            params={
                "reference": req.reference,
                "problem": _problem(req),
                "area": area,
                "car": _car(req),
                "assignment_id": assignment.id,
            },
            language=settings.notify_mechanic_language,
            dedupe_key=key,
        )
    first_name = (mechanic.name.split() or ["Your mechanic"])[0] if mechanic else "Your mechanic"
    return notify(
        session,
        event=str(to),
        template=template,
        recipient=recipient,
        request=req,
        params={"reference": req.reference, "mechanic": first_name},
        language=customer_language(session, req),
        dedupe_key=key,
    )


# ---------------------------------------------------------------- sending (the worker)


def escalation_email(req, settings: Settings, note: str) -> Email:
    lines = [
        f"Request {req.reference} was escalated.",
        "",
        f"Reason: {note or 'not given'}",
        f"Status before: see the timeline. Diagnosis: {req.problem_summary or 'none'}",
        "",
        f"Open it: {settings.admin_origin}/requests/{req.id}",
    ]
    return Email(to=settings.support_email, subject=f"[ESCALATED] Request {req.reference}", text="\n".join(lines))


def build_message(session: Session, settings: Settings, row: Notification) -> tuple[Message | None, str | None]:
    """The message with its address, read now (numbers are never stored with the notification)."""
    from app.mechanics.models import Mechanic
    from app.requests.models import ServiceRequest
    from app.requests.service import alert_email

    req = session.get(ServiceRequest, row.request_id) if row.request_id else None
    msg = Message(template=row.template, language=row.language, params=dict(row.params or {}))
    if row.recipient_type == RecipientType.support:
        if req is None:
            return None, "the request no longer exists"
        if row.template == "request_submitted":
            msg.email = alert_email(req, settings) if settings.support_email else None
        else:
            msg.email = escalation_email(req, settings, msg.params.get("note", "")) if settings.support_email else None
        return msg, None
    if row.recipient_type == RecipientType.mechanic:
        mech = session.get(Mechanic, row.mechanic_id) if row.mechanic_id else None
        if mech is None:
            return None, "the mechanic no longer exists"
        msg.phone = mech.phone
        msg.push_targets = _targets(session, None, None, mech.id)
        msg.url = f"{settings.web_origin}/m/offers" if row.template == "job_offer" else f"{settings.web_origin}/m"
        if row.template == "job_offer" and msg.params.get("assignment_id"):
            aid = msg.params["assignment_id"]
            msg.button_payloads = [f"offer:{aid}:accept", f"offer:{aid}:reject"]
        return msg, None
    # customer
    if req is not None:
        msg.phone = req.phone
        msg.push_targets = _targets(session, req.user_id, req.anon_key_hash)
        msg.url = f"{settings.web_origin}/requests/{req.id}" if req.user_id else f"{settings.web_origin}/"
    elif row.user_id is not None:
        msg.phone = _user_phone(session, row.user_id)
        msg.push_targets = _targets(session, row.user_id, None)
        msg.url = f"{settings.web_origin}/account"
    else:
        return None, "no customer to send to"
    return msg, None


def _targets(session: Session, user_id, anon_key_hash, mechanic_id=None) -> list[Target]:
    subs = _push_targets(session, user_id, anon_key_hash, mechanic_id)
    return [Target(s.id, s.endpoint, s.p256dh, s.auth) for s in subs]


def _next_channel(session: Session, row: Notification) -> Notification | None:
    rest = list(row.fallback or [])
    if not rest:
        return None
    nxt = Notification(
        request_id=row.request_id,
        event=row.event,
        template=row.template,
        language=row.language,
        recipient_type=row.recipient_type,
        user_id=row.user_id,
        mechanic_id=row.mechanic_id,
        recipient_masked=row.recipient_masked,
        channel=Channel(rest[0]),
        params=row.params,
        fallback=rest[1:],
        previous_id=row.id,
        next_attempt_at=datetime.now(UTC),
    )
    session.add(nxt)
    session.flush()
    after_commit_enqueue(session, send_job(nxt.id, 0))
    return nxt


def _give_up(session: Session, row: Notification, status: NotificationStatus, error: str) -> Notification | None:
    """Mark this channel skipped / failed and move on to the next channel (if any)."""
    row.status, row.error, row.updated_at = status, error[:500], datetime.now(UTC)
    nxt = _next_channel(session, row)
    then = f"Trying {nxt.channel} (notification {nxt.id})." if nxt else "No channel left."
    who = f"{row.template} to {row.recipient_type} {row.recipient_masked or '-'}"
    log.warning("Notification %s (%s) %s on %s: %s. %s", row.id, who, status, row.channel, error, then)
    if nxt is None:
        _support_alert_result(session, row, error)
    return nxt


def _support_alert_result(session: Session, row: Notification, error: str | None) -> None:
    """The submitted alert keeps filling service_requests.alert_sent_at / alert_error (support queue, README)."""
    if row.template != "request_submitted" or row.request_id is None:
        return
    from app.requests.models import ServiceRequest

    req = session.get(ServiceRequest, row.request_id)
    if req is None:
        return
    if error is None:
        req.alert_sent_at, req.alert_error = datetime.now(UTC), None
    else:
        req.alert_error = error[:500]


def retry_delay(settings: Settings, attempts: int) -> timedelta:
    return timedelta(seconds=settings.notify_retry_base_seconds * 4 ** max(0, attempts - 1))


def send(session: Session, channels: dict[Channel, ChannelProvider], settings: Settings, notification_id: int) -> str:
    """Send one queued notification (the worker; also callable inline). Locks the row, so a row is sent once."""
    row = session.scalar(
        select(Notification).where(Notification.id == notification_id).with_for_update(skip_locked=True)
    )
    if row is None or row.status != ST.queued:
        return "not queued"
    now = datetime.now(UTC)
    if row.next_attempt_at > now + timedelta(seconds=5):
        after_commit_enqueue(session, send_job(row.id, row.attempts, row.next_attempt_at))
        return "not due yet"
    msg, problem = build_message(session, settings, row)
    if problem:
        _give_up(session, row, ST.skipped, problem)
        return "skipped"
    provider = channels[Channel(row.channel)]
    row.provider = provider.name
    reason = provider.unavailable(msg)
    if reason:
        _give_up(session, row, ST.skipped, reason)
        return "skipped"
    row.attempts += 1
    try:
        provider_id = provider.send(msg)
    except SendFailed as e:
        if e.retry and row.attempts < settings.notify_max_attempts:
            row.error, row.updated_at = str(e)[:500], now
            row.next_attempt_at = now + retry_delay(settings, row.attempts)
            after_commit_enqueue(session, send_job(row.id, row.attempts, row.next_attempt_at))
            when = row.next_attempt_at.isoformat()
            who = f"{row.channel}, {row.recipient_masked or '-'}"
            log.warning(
                "Notification %s (%s) attempt %s failed: %s; retrying at %s", row.id, who, row.attempts, e, when
            )
            return "retry"
        _give_up(session, row, ST.failed, str(e) + (f" (after {row.attempts} attempts)" if e.retry else ""))
        return "failed"
    finally:
        _revoke_gone(session, msg.gone)
    row.status, row.provider_id, row.error = ST.sent, provider_id, None
    row.sent_at = row.updated_at = datetime.now(UTC)
    if msg.sent_language:
        row.language = msg.sent_language
    _support_alert_result(session, row, None)
    return "sent"


def _revoke_gone(session: Session, ids: list[int]) -> None:
    if ids:
        for sub in session.scalars(select(PushSubscription).where(PushSubscription.id.in_(ids))):
            sub.revoked_at = datetime.now(UTC)


def delivery_status(session: Session, wamid: str, status: str, error: str) -> str:
    """A WhatsApp status update for a message we sent: delivered / read, or failed (then the next channel)."""
    row = session.scalar(
        select(Notification)
        .where(Notification.provider_id == wamid, Notification.channel == Channel.whatsapp)
        .with_for_update()
    )
    if row is None:
        return "unknown message"
    now = datetime.now(UTC)
    if status == "delivered" and row.status == ST.sent:
        row.status, row.delivered_at, row.updated_at = ST.delivered, now, now
    elif status == "read" and row.status in (ST.sent, ST.delivered):
        row.status, row.updated_at = ST.read, now
        row.delivered_at = row.delivered_at or now
    elif status == "failed" and row.status in (ST.sent, ST.delivered):
        _give_up(session, row, ST.failed, f"WhatsApp could not deliver it: {error or 'no reason given'}")
    else:
        return f"no change ({row.status} -> {status})"
    return f"notification {row.id} {status}"


def due(session: Session, limit: int = 200) -> list[Notification]:
    """Queued rows whose time has come and that were not queued in the last 5 minutes (the worker's sweep)."""
    now = datetime.now(UTC)
    rows = list(
        session.scalars(
            select(Notification)
            .where(
                Notification.status == ST.queued,
                Notification.next_attempt_at <= now - timedelta(seconds=60),
                or_(Notification.enqueued_at.is_(None), Notification.enqueued_at <= now - timedelta(minutes=5)),
            )
            .order_by(Notification.next_attempt_at)
            .limit(limit)
        )
    )
    for r in rows:
        r.enqueued_at = now
    return rows
