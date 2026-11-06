"""Dispatch (Phase 5.3): offers that expire, auto-offer, escalation, and the one way a mechanic answers an offer.

Runs in the arq worker every 20 seconds (sweep()):

1. **Auto-offer start.** A new (submitted) request whose zone and job type (service type) have auto-offer switched
   on (auto_offer_settings, super admins, off by default) is triaged by the system and offered to the best
   suggestion (app/mechanics/matching.py: distance 45 / rating 25 / acceptance 20 / jobs today 10). Safety-critical
   requests (a red safety alert) are left to support, who call the customer first.
2. **Expiry.** An offer not answered within OFFER_EXPIRY_SECONDS is closed as "expired" and the request goes back to
   triaged. If the system is dispatching it (auto-offer) the next suggestion gets it (mechanics already offered this
   request are skipped); if nobody is left, it is escalated. Offers made by an agent go back to the agent.
3. **Escalation.** A request still not accepted DISPATCH_ESCALATE_SECONDS after the first offer of its round is
   escalated to support (status escalated: notify() emails the support inbox).

Support can always take over: auto-offer only acts while no agent owns the request. Taking the request (owner = me),
offering it by hand or any status change by an agent stops it for that request.

answer() is the single path for a mechanic's Accept / Reject, from the mechanic app and from WhatsApp alike: it locks
the request, checks the offer is still open, not expired and theirs, then calls workflow.respond() and writes the
audit log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.estimates.zones import zone_for_pincode
from app.mechanics import matching
from app.requests import workflow
from app.requests.models import (
    AssignmentStatus,
    AutoOfferSetting,
    EventKind,
    RequestAssignment,
    RequestStatus,
    SafetyLevel,
    ServiceRequest,
)

log = logging.getLogger(__name__)
S = RequestStatus
SYSTEM = workflow.Actor(None, "auto-offer")
DISPATCH = workflow.Actor(None, "dispatch")


def zone_code(req: ServiceRequest) -> str | None:
    zone = zone_for_pincode(req.pincode)
    return zone.code if zone else None


def auto_enabled(session: Session, req: ServiceRequest) -> bool:
    zone = zone_code(req)
    if zone is None:
        return False
    row = session.get(AutoOfferSetting, (zone, req.service_type))
    return bool(row and row.enabled)


def expiry(settings: Settings, now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + timedelta(seconds=settings.offer_expiry_seconds)


def _tried(session: Session, req: ServiceRequest) -> set[int]:
    return set(session.scalars(select(RequestAssignment.mechanic_id).where(RequestAssignment.request_id == req.id)))


def escalate(session: Session, req: ServiceRequest, why: str) -> None:
    """To support (status escalated, which closes an open offer and emails support through notify())."""
    workflow.move(session, req, S.escalated, DISPATCH, why)
    req.dispatch_started_at, req.auto_dispatch = None, False
    log.info("Request %s escalated: %s", req.reference, why)


def offer_next(session: Session, settings: Settings, req: ServiceRequest, now: datetime) -> RequestAssignment | None:
    """Auto-offer to the best suggestion not offered this request yet; escalate when nobody is left."""
    tried = _tried(session, req)
    found = matching.suggest(session, req, now=now, limit=1000)
    for s in found.suggestions:
        if s.mechanic_id in tried:
            continue
        snapshot = {"suggested": True, "score": s.score, "distance_km": s.distance_km, "reasons": s.reasons}
        return workflow.offer(
            session, req, s.mechanic_id, SYSTEM, snapshot, "auto-offer", expires_at=expiry(settings, now), auto=True
        )
    escalate(session, req, "Auto-offer: no available mechanic left to offer it to")
    return None


def start_auto(session: Session, settings: Settings, req: ServiceRequest, now: datetime) -> RequestAssignment | None:
    workflow.move(session, req, S.triaged, SYSTEM, "auto-offer is on for this area and job type")
    req.auto_dispatch = True
    return offer_next(session, settings, req, now)


def _system_dispatching(req: ServiceRequest) -> bool:
    return req.auto_dispatch and req.assigned_agent_id is None


def expire_offers(session: Session, settings: Settings, now: datetime) -> int:
    rows = list(
        session.scalars(
            select(RequestAssignment)
            .where(
                RequestAssignment.status == AssignmentStatus.offered,
                RequestAssignment.expires_at.is_not(None),
                RequestAssignment.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for a in rows:
        req = session.get(ServiceRequest, a.request_id, with_for_update=True)
        a.status, a.responded_at = AssignmentStatus.expired, now
        a.note = (a.note + " · expired (not answered in time)").strip(" ·")
        data = {"mechanic_id": a.mechanic_id, "expired": True}
        workflow.event(session, req, EventKind.response, DISPATCH, "offer expired", data)
        if req.status == S.offered:
            workflow.move(session, req, S.triaged, DISPATCH, "offer expired", {"mechanic_id": a.mechanic_id})
            if _system_dispatching(req):
                offer_next(session, settings, req, now)
    return len(rows)


def escalate_stale(session: Session, settings: Settings, now: datetime) -> int:
    limit = now - timedelta(seconds=settings.dispatch_escalate_seconds)
    rows = list(
        session.scalars(
            select(ServiceRequest)
            .where(
                ServiceRequest.status.in_([S.triaged, S.offered]),
                ServiceRequest.dispatch_started_at.is_not(None),
                ServiceRequest.dispatch_started_at <= limit,
            )
            .with_for_update(skip_locked=True)
        )
    )
    minutes = round(settings.dispatch_escalate_seconds / 60)
    for req in rows:
        escalate(session, req, f"No mechanic accepted within {minutes} minutes")
    return len(rows)


def start_new(session: Session, settings: Settings, now: datetime) -> int:
    rows = list(
        session.scalars(
            select(ServiceRequest)
            .where(
                ServiceRequest.status == S.submitted,
                ServiceRequest.assigned_agent_id.is_(None),
                ServiceRequest.safety_level != SafetyLevel.high,
            )
            .order_by(ServiceRequest.created_at)
            .with_for_update(skip_locked=True)
        )
    )
    started = 0
    for req in rows:
        if auto_enabled(session, req):
            start_auto(session, settings, req, now)
            started += 1
    return started


@dataclass
class SweepResult:
    started: int
    expired: int
    escalated: int


def sweep(session: Session, settings: Settings, now: datetime | None = None) -> SweepResult:
    now = now or datetime.now(UTC)
    started = start_new(session, settings, now)
    expired = expire_offers(session, settings, now)
    escalated = escalate_stale(session, settings, now)
    return SweepResult(started, expired, escalated)


# ---------------------------------------------------------------- a mechanic's answer (app and WhatsApp)


class AnswerRefused(Exception):
    """The answer changes nothing: `reason` says why (repeat press, offer closed, expired, not theirs)."""

    def __init__(self, reason: str, closed: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.closed = closed  # the offer exists but is no longer open (tell the mechanic)


def answer(session: Session, a: RequestAssignment, mechanic, accept: bool, via: str) -> ServiceRequest:
    """Accept or reject an offer as the mechanic it was offered to. `via`: "app" or "WhatsApp"."""
    from app.admin import audit

    if a.mechanic_id != mechanic.id:
        raise AnswerRefused("this offer is not yours")
    req = session.get(ServiceRequest, a.request_id, with_for_update=True)  # one answer at a time (admin, app, button)
    session.refresh(a)
    if a.status != AssignmentStatus.offered:
        answered = AssignmentStatus.accepted if accept else AssignmentStatus.declined
        if a.status == answered:
            raise AnswerRefused(f"repeat press: the offer is already {a.status}")
        raise AnswerRefused(f"the offer is {a.status}", closed=True)
    if a.expires_at is not None and a.expires_at <= datetime.now(UTC):
        raise AnswerRefused("the offer has expired", closed=True)
    first = (mechanic.name.split() or ["Mechanic"])[0]
    actor = workflow.Actor(None, f"{first} (mechanic, {via})")
    where = "in the app" if via == "app" else f"on {via}"
    verb = "accepted" if accept else "declined"
    before = str(req.status)
    try:
        workflow.respond(session, req, accept, actor, f"answered {where}")
    except workflow.TransitionError as e:
        raise AnswerRefused(f"not allowed: {e}", closed=True) from e
    if not accept and _system_dispatching(req):
        offer_next(session, _settings(), req, datetime.now(UTC))  # auto-offer moves on at once
    audit.record(
        session,
        actor_id=None,
        actor_label=actor.label,
        action="request.set_status",
        entity_type="service_request",
        entity_id=req.id,
        before={"status": before},
        after={"status": str(req.status), "note": f"mechanic {mechanic.id} {verb} {where}"},
    )
    return req


def _settings() -> Settings:
    from app.notify.service import current_settings

    return current_settings()
