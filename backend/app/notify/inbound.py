"""What comes back from WhatsApp, handled by the worker (the webhook only stores it and answers 200).

- A press on Accept / Reject of a job offer ("offer:<assignment id>:accept|reject") goes through the same state
  machine as the admin app (workflow.respond): the offer must still be open, the sender's number must be that
  mechanic's, and the request must still be waiting for this answer. A repeat press changes nothing (the same
  message is stored once; a second press finds the offer answered). The answer is in the request timeline and the
  audit log ("<first name> (mechanic, WhatsApp)"), and the mechanic gets a short reply.
- STOP withdraws every WhatsApp opt-in of that number; START opts a mechanic in (or a customer back in).
- Delivery statuses update the notification (delivered / read), or fail it over to the next channel.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.notify import optins
from app.notify import service as notify
from app.notify.models import Channel, InboundStatus, NotificationOptin, RecipientType, WhatsappInbound
from app.notify.queue import after_commit_enqueue, inbound_job
from app.notify.sms import mask_phone
from app.notify.whatsapp import Inbound

log = logging.getLogger(__name__)


def store(session: Session, settings: Settings, items: list[Inbound]) -> int:
    """Keep each new message once (Meta retries deliveries) and queue it for the worker. Returns how many were new."""
    new = 0
    for it in items:
        row_id = session.scalar(
            insert(WhatsappInbound)
            .values(
                message_id=it.message_id,
                kind=it.kind,
                from_hash=optins.phone_hash(settings, it.phone) if it.phone else None,
                from_masked=mask_phone(it.phone) if it.phone else "",
                data=it.data,
            )
            .on_conflict_do_nothing(index_elements=["message_id"])
            .returning(WhatsappInbound.id)
        )
        if row_id is not None:
            new += 1
            after_commit_enqueue(session, inbound_job(row_id))
    return new


def pending(session: Session, limit: int = 200) -> list[int]:
    return list(
        session.scalars(
            select(WhatsappInbound.id)
            .where(WhatsappInbound.status == InboundStatus.pending)
            .order_by(WhatsappInbound.id)
            .limit(limit)
        )
    )


def handle(session: Session, settings: Settings, inbound_id: int) -> str:
    row = session.scalar(
        select(WhatsappInbound).where(WhatsappInbound.id == inbound_id).with_for_update(skip_locked=True)
    )
    if row is None or row.status != InboundStatus.pending:
        return "already handled"
    try:
        if row.kind == "status":
            d = row.data
            done, result = True, notify.delivery_status(session, d["wamid"], d["status"], d.get("error", ""))
        elif row.kind == "button":
            done, result = _button(session, settings, row)
        elif row.kind == "text":
            done, result = _keyword(session, settings, row)
        else:
            done, result = False, f"unknown kind {row.kind}"
    except Exception as e:  # recorded and visible; the next message is unaffected
        log.exception("WhatsApp message %s could not be handled", row.id)
        row.status, row.result = InboundStatus.failed, f"{type(e).__name__}: {e}"[:300]
        row.processed_at = datetime.now(UTC)
        return row.result
    row.status = InboundStatus.done if done else InboundStatus.ignored
    row.result, row.processed_at = result[:300], datetime.now(UTC)
    log.info("WhatsApp %s from %s: %s", row.kind, row.from_masked or "-", row.result)
    return row.result


def _reply(session: Session, row: WhatsappInbound, template: str, *, mechanic=None, optin=None, params=None) -> None:
    """A plain-text WhatsApp reply (inside the 24-hour window the sender's message opened)."""
    recipient = RecipientType.mechanic if mechanic is not None else RecipientType.customer
    request = None
    if optin is not None and optin.request_id is not None:
        from app.requests.models import ServiceRequest

        request = session.get(ServiceRequest, optin.request_id)
    notify.notify(
        session,
        event="whatsapp_reply",
        template=template,
        recipient=recipient,
        mechanic=mechanic,
        request=request,
        user_id=getattr(optin, "user_id", None),
        params=params or {},
        language=_language(mechanic),
        channels=[Channel.whatsapp],
        dedupe_key=f"whatsapp:{row.message_id}:reply",
    )


def _language(mechanic) -> str:
    return notify.current_settings().notify_mechanic_language if mechanic is not None else "en"


def _mechanic_by_hash(session: Session, settings: Settings, from_hash: str | None):
    if not from_hash:
        return None
    from app.mechanics.models import Mechanic

    for m in session.scalars(select(Mechanic).where(Mechanic.active.is_(True))):
        if optins.phone_hash(settings, m.phone) == from_hash:
            return m
    return None


def _button(session: Session, settings: Settings, row: WhatsappInbound) -> tuple[bool, str]:
    from app.admin import audit
    from app.mechanics.models import Mechanic
    from app.requests import workflow
    from app.requests.models import AssignmentStatus, RequestAssignment, ServiceRequest

    parts = str(row.data.get("payload", "")).split(":")
    if len(parts) != 3 or parts[0] != "offer" or parts[2] not in ("accept", "reject") or not parts[1].isdigit():
        return False, "not a job offer button"
    accept = parts[2] == "accept"
    a = session.get(RequestAssignment, int(parts[1]))
    if a is None:
        return False, "unknown offer"
    mech = session.get(Mechanic, a.mechanic_id)
    if mech is None or optins.phone_hash(settings, mech.phone) != row.from_hash:
        return False, "the sender is not the mechanic this job was offered to"
    req = session.get(ServiceRequest, a.request_id, with_for_update=True)  # one answer at a time (admin or button)
    session.refresh(a)
    if a.status != AssignmentStatus.offered:
        same = (a.status == AssignmentStatus.accepted and accept) or (
            a.status == AssignmentStatus.declined and not accept
        )
        if same:
            return False, f"repeat press: the offer is already {a.status}"
        _reply(session, row, "offer_closed", mechanic=mech, params={"reference": req.reference})
        return False, f"the offer is {a.status}"
    first = (mech.name.split() or ["Mechanic"])[0]
    verb = "accepted" if accept else "declined"
    actor = workflow.Actor(None, f"{first} (mechanic, WhatsApp)")
    before = str(req.status)
    try:
        workflow.respond(session, req, accept, actor, "answered on WhatsApp")
    except workflow.TransitionError as e:
        _reply(session, row, "offer_closed", mechanic=mech, params={"reference": req.reference})
        return False, f"not allowed: {e}"
    audit.record(
        session,
        actor_id=None,
        actor_label=actor.label,
        action="request.set_status",
        entity_type="service_request",
        entity_id=req.id,
        before={"status": before},
        after={
            "status": str(req.status),
            "note": f"mechanic {mech.id} {'accepted' if accept else 'declined'} on WhatsApp",
        },
    )
    template = "offer_accepted_ack" if accept else "offer_declined_ack"
    _reply(session, row, template, mechanic=mech, params={"reference": req.reference})
    return True, f"mechanic {mech.id} {verb} {req.reference}"


def _keyword(session: Session, settings: Settings, row: WhatsappInbound) -> tuple[bool, str]:
    keyword = row.data.get("keyword")
    mech = _mechanic_by_hash(session, settings, row.from_hash)
    if keyword == "stop":
        active = list(
            session.scalars(
                select(NotificationOptin).where(
                    NotificationOptin.phone_hash == row.from_hash,
                    NotificationOptin.channel == Channel.whatsapp,
                    NotificationOptin.withdrawn_at.is_(None),
                )
            )
        )
        for o in active:
            o.withdrawn_at, o.withdrawn_source = datetime.now(UTC), "whatsapp_keyword"
        if not active:
            return False, "STOP from a number with no opt-in"
        _reply(session, row, "whatsapp_stopped", mechanic=mech, optin=None if mech else active[0])
        return True, f"STOP: {len(active)} opt-in(s) withdrawn"
    if keyword == "start":
        if mech is not None:
            optins.record(
                session,
                settings,
                phone=mech.phone,
                source="whatsapp_keyword",
                mechanic_id=mech.id,
                version=optins.WHATSAPP_MECHANIC_VERSION,
            )
            _reply(session, row, "whatsapp_started", mechanic=mech)
            return True, f"START: mechanic {mech.id} opted in"
        last = session.scalar(
            select(NotificationOptin)
            .where(NotificationOptin.phone_hash == row.from_hash, NotificationOptin.channel == Channel.whatsapp)
            .order_by(NotificationOptin.opted_in_at.desc())
            .limit(1)
        )
        if last is None or last.mechanic_id is not None:
            return False, "START from a number we do not know (customers opt in on the website)"
        if last.withdrawn_at is None:
            return False, "START: already opted in"
        new = NotificationOptin(
            channel=Channel.whatsapp,
            user_id=last.user_id,
            request_id=last.request_id,
            phone_hash=last.phone_hash,
            consent_text_version=last.consent_text_version,
            consent_text=last.consent_text,
            source="whatsapp_keyword",
            opted_in_at=datetime.now(UTC),
        )
        session.add(new)
        session.flush()
        _reply(session, row, "whatsapp_started", optin=new)
        return True, "START: customer opted back in"
    return False, "no keyword"
