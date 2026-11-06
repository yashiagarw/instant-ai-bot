"""A customer's own data as JSON (DPDP Act: the right to a summary of their personal data): GET /api/me/export,
from My account. Everything we keep about them, in plain fields: the account and its consent, saved cars, diagnoses
(with what they typed and the results), requests (contact details, place, status history, the confirmed fault),
photos (when and what was found, not the image files), notification choices, WhatsApp opt-ins with their wording,
and the messages we sent them. Internal fields (mechanic tasks and repair steps, staff notes, other people's data)
are not included."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def build(session: Session, user) -> dict:
    from app.accounts.models import UserVehicle
    from app.diagnosis.models import DiagnosisSession, EventType, SessionEvent, SessionResult
    from app.notify.models import Notification, NotificationOptin, NotificationPreference
    from app.requests.models import EventKind, RequestEvent, RequestOutcome, ServiceRequest
    from app.uploads.models import Upload

    sessions = list(
        session.scalars(
            select(DiagnosisSession).where(DiagnosisSession.user_id == user.id).order_by(DiagnosisSession.created_at)
        )
    )
    sids = [s.id for s in sessions]
    typed: dict = {}
    results: dict = {}
    if sids:
        for e in session.scalars(
            select(SessionEvent)
            .where(SessionEvent.session_id.in_(sids), SessionEvent.event_type == EventType.free_text)
            .order_by(SessionEvent.id)
        ):
            typed.setdefault(e.session_id, []).append(e.payload.get("text"))
        for r in session.scalars(
            select(SessionResult).where(SessionResult.session_id.in_(sids)).order_by(SessionResult.rank)
        ):
            results.setdefault(r.session_id, []).append(
                {"rank": r.rank, "fault_key": r.fault_key, "confidence": str(r.confidence)}
            )
    requests = list(
        session.scalars(
            select(ServiceRequest).where(ServiceRequest.user_id == user.id).order_by(ServiceRequest.created_at)
        )
    )
    rids = [r.id for r in requests]
    history: dict = {}
    if rids:
        for e in session.scalars(
            select(RequestEvent)
            .where(RequestEvent.request_id.in_(rids), RequestEvent.kind == EventKind.status)
            .order_by(RequestEvent.at)
        ):
            history.setdefault(e.request_id, []).append({"at": _iso(e.at), "status": e.to_status})
    owned = Upload.user_id == user.id
    if sids:
        owned = or_(owned, Upload.session_id.in_(sids))
    uploads = list(session.scalars(select(Upload).where(owned)))
    subject = NotificationOptin.user_id == user.id
    if rids:
        subject = or_(subject, NotificationOptin.request_id.in_(rids))
    optins = list(session.scalars(select(NotificationOptin).where(subject)))
    notes = list(
        session.scalars(
            select(Notification)
            .where(Notification.user_id == user.id, Notification.recipient_type == "customer")
            .order_by(Notification.id)
        )
    )
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "about": "Your personal data held by Instant Mechanic. Prices, likely causes and advice in it are estimates.",
        "account": {
            "phone": user.phone,
            "name": user.name,
            "created_at": _iso(user.created_at),
            "last_login_at": _iso(user.last_login_at),
            "consent": {"version": user.consent_text_version, "at": _iso(user.consent_at)},
        },
        "saved_cars": [
            {"label": v.label, "saved_at": _iso(v.created_at)}
            for v in session.scalars(select(UserVehicle).where(UserVehicle.user_id == user.id))
        ],
        "diagnoses": [
            {
                "id": str(s.id),
                "started_at": _iso(s.created_at),
                "car": s.vehicle_snapshot,
                "you_typed": [t for t in ([s.entry_text] if s.entry_text else []) + typed.get(s.id, []) if t],
                "results": results.get(s.id, []),
                "status": str(s.status),
            }
            for s in sessions
        ],
        "requests": [
            {
                "reference": r.reference,
                "created_at": _iso(r.created_at),
                "name": r.name,
                "phone": r.phone,
                "area": r.area_text,
                "pincode": r.pincode,
                "address": r.address,
                "notes": r.notes,
                "service_type": str(r.service_type),
                "status": str(r.status),
                "status_history": history.get(r.id, []),
                "consent": {"version": r.consent_text_version, "at": _iso(r.consent_at)},
                "confirmed_fault": _outcome(session.get(RequestOutcome, r.id)),
            }
            for r in requests
        ],
        "photos": [{"id": str(u.id), "uploaded_at": _iso(u.created_at), "status": str(u.status)} for u in uploads],
        "notification_choices": {
            str(p.channel): p.enabled
            for p in session.scalars(select(NotificationPreference).where(NotificationPreference.user_id == user.id))
        },
        "whatsapp_opt_ins": [
            {
                "wording": o.consent_text,
                "version": o.consent_text_version,
                "source": o.source,
                "opted_in_at": _iso(o.opted_in_at),
                "withdrawn_at": _iso(o.withdrawn_at),
            }
            for o in optins
        ],
        "messages_sent": [
            {"at": _iso(n.created_at), "message": n.template, "channel": str(n.channel), "status": str(n.status)}
            for n in notes
        ],
    }


def _outcome(o) -> dict | None:
    if o is None:
        return None
    return {"fault_key": o.confirmed_fault_key, "other": o.other_text or None, "final_cost_inr": o.final_cost_inr}
