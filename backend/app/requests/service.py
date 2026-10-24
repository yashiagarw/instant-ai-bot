"""Store a service request with its consent record and alert the support team by email."""

import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine as eng
from app.config import Settings
from app.diagnosis import service as diagnosis
from app.diagnosis.models import DiagnosisSession
from app.knowledge.models import ProblemGroup
from app.notify.email import Email, EmailError, EmailSender
from app.requests.models import RequestStatus, ServiceRequest, ServiceType
from app.requests.schemas import PREFERRED_TIMES, ServiceRequestIn

log = logging.getLogger(__name__)

CONSENT_VERSION = "request-v1"
CONSENT_TEXT = (
    "I agree that Instant Mechanic's team may use my name, mobile number, location and the car and diagnosis "
    "details above to contact me and arrange help for this request."
)
REFERENCE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O or 1/I, easy to read out on the phone
SERVICE_LABELS = {
    ServiceType.at_location: "Mechanic at my location",
    ServiceType.tow: "Tow the car",
    ServiceType.workshop: "Workshop visit",
}


class RequestInputError(ValueError):
    pass


def new_reference(session: Session) -> str:
    while True:
        ref = "IM-" + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(6))
        if session.scalar(select(ServiceRequest.id).where(ServiceRequest.reference == ref)) is None:
            return ref


def summarise(session: Session, engine: eng.Engine, ds: DiagnosisSession) -> tuple[bool, str]:
    """(urgent, problem summary) from the diagnosis. Urgent: a fast-track topic (towing, lockout, ...) or a red
    safety alert. Built on the server so the team sees what the engine found, not what the browser sent."""
    result = diagnosis.current_result(session, engine, ds)
    banner, _ = diagnosis.banner_alerts(result)
    topic = session.get(ProblemGroup, ds.problem_group_code) if ds.problem_group_code else None
    parts = [topic.label_en if topic else (ds.entry_text or "Problem described in free text")]
    if result.ranked:
        top = result.ranked[0]
        parts.append(f"likely cause: {top.name} ({top.confidence} confidence)")
    if banner:
        parts.append("SAFETY: " + "; ".join(a.reason for a in banner))
    return result.mode == "fast_track" or bool(banner), " · ".join(parts)


def create(session: Session, engine: eng.Engine, body: ServiceRequestIn) -> ServiceRequest:
    if body.consent_text_version != CONSENT_VERSION:
        raise RequestInputError("the consent wording has changed; please reload the page and tick the box again")
    ds = session.get(DiagnosisSession, body.session_id) if body.session_id else None
    if body.session_id and ds is None:
        raise RequestInputError("unknown session_id")
    urgent, summary = summarise(session, engine, ds) if ds else (False, "")
    if not urgent and not body.pincode:
        raise RequestInputError("enter a 6-digit pincode")
    now = datetime.now(UTC)
    req = ServiceRequest(
        reference=new_reference(session),
        session_id=ds.id if ds else None,
        name=body.name,
        phone=body.phone,
        area_text=body.area,
        pincode=body.pincode,
        address=body.address,
        service_type=body.service_type,
        preferred_time=body.preferred_time,
        notes=body.notes,
        urgent=urgent,
        vehicle_snapshot=dict(ds.vehicle_snapshot) if ds else {},
        problem_summary=summary,
        status=RequestStatus.submitted,
        consent_given=True,
        consent_text_version=body.consent_text_version,
        consent_at=now,
    )
    session.add(req)
    session.flush()
    return req


def alert_email(req: ServiceRequest, settings: Settings) -> Email:
    v = req.vehicle_snapshot or {}
    car = (
        " ".join(str(x) for x in (v.get("make"), v.get("model"), v.get("variant") or v.get("year")) if x) or "not given"
    )
    lines = [
        f"{'URGENT ' if req.urgent else ''}Request {req.reference}",
        "",
        f"Name: {req.name}",
        f"Mobile: {req.phone}",
        f"Service: {SERVICE_LABELS[req.service_type]}",
        f"Area: {req.area_text}" + (f", {req.pincode}" if req.pincode else ""),
    ]
    if req.address:
        lines.append(f"Address: {req.address}")
    if req.preferred_time:
        lines.append(f"Preferred time: {PREFERRED_TIMES[req.preferred_time]}")
    lines += [f"Car: {car}", f"Diagnosis: {req.problem_summary or 'none'}"]
    if req.notes:
        lines.append(f"Notes: {req.notes}")
    if req.session_id:
        lines.append(f"Result: {settings.web_origin}/diagnose/{req.session_id}/result")
    lines += ["", f"Consent: {req.consent_text_version} at {req.consent_at.isoformat()}"]
    subject = f"{'[URGENT] ' if req.urgent else ''}New mechanic request {req.reference}"
    return Email(to=settings.support_email, subject=subject, text="\n".join(lines))


def send_alert(session: Session, req: ServiceRequest, sender: EmailSender, settings: Settings) -> None:
    """Email the support team. A failed alert is recorded on the request and logged; the request stays."""
    if not settings.support_email:
        req.alert_error = "SUPPORT_EMAIL is not set"
        log.error("Request %s stored but no alert sent: SUPPORT_EMAIL is not set", req.reference)
        return
    try:
        sender.send(alert_email(req, settings))
        req.alert_sent_at = datetime.now(UTC)
        req.alert_error = None
    except EmailError as e:
        req.alert_error = str(e)[:500]
        log.error("Request %s stored but the alert email failed: %s", req.reference, e)


def next_steps(req: ServiceRequest, helpline: str) -> list[str]:
    call = f" If you can't wait, call {helpline}." if helpline else ""
    if req.urgent:
        return [
            "We've marked your request urgent. Our team will call you on your mobile as soon as possible.",
            "Stay in a safe place away from traffic, with the hazard lights on." + call,
            f"Keep your reference {req.reference} ready when we call.",
        ]
    return [
        "Our team will call you on your mobile to confirm the details and a time.",
        "We'll tell you the price before any work starts.",
        f"Keep your reference {req.reference} ready." + call,
    ]
