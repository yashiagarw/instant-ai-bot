"""The request state machine. Only these moves are allowed; every change of status writes a request_event (the
customer's timeline and the admin timeline are built from them).

    submitted   -> triaged, cancelled, escalated
    triaged     -> offered, cancelled, escalated
    offered     -> accepted, triaged (the mechanic declined, or the offer was taken back), cancelled, escalated
    accepted    -> en_route, triaged (the mechanic dropped out), cancelled, escalated
    en_route    -> arrived, triaged, cancelled, escalated
    arrived     -> in_progress, cancelled, escalated
    in_progress -> completed, escalated
    escalated   -> triaged, cancelled
    completed, cancelled: final

offered and accepted come from the assignment actions (offer a mechanic, record their answer); completed needs the
confirmed fault (record_outcome). Times are stored in UTC and shown in India time.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.requests.models import (
    AssignmentStatus,
    EventKind,
    RequestAssignment,
    RequestEvent,
    RequestStatus,
    ServiceRequest,
)

S = RequestStatus
TRANSITIONS: dict[RequestStatus, frozenset[RequestStatus]] = {
    S.submitted: frozenset({S.triaged, S.cancelled, S.escalated}),
    S.triaged: frozenset({S.offered, S.cancelled, S.escalated}),
    S.offered: frozenset({S.accepted, S.triaged, S.cancelled, S.escalated}),
    S.accepted: frozenset({S.en_route, S.triaged, S.cancelled, S.escalated}),
    S.en_route: frozenset({S.arrived, S.triaged, S.cancelled, S.escalated}),
    S.arrived: frozenset({S.in_progress, S.cancelled, S.escalated}),
    S.in_progress: frozenset({S.completed, S.escalated}),
    S.escalated: frozenset({S.triaged, S.cancelled}),
    S.completed: frozenset(),
    S.cancelled: frozenset(),
}
# Moves that need their own action (and data) instead of a plain status change.
VIA_ACTION = {
    S.offered: "offer a mechanic",
    S.accepted: "record the mechanic's answer",
    S.completed: "record the confirmed fault",
}
OPEN = (AssignmentStatus.offered, AssignmentStatus.accepted)

# What the customer reads (plain words; never the mechanic's phone or documents).
CUSTOMER_LABELS = {
    S.submitted: "Request received",
    S.triaged: "Our team is on it",
    S.offered: "Finding a mechanic for you",
    S.accepted: "Mechanic assigned",
    S.en_route: "Mechanic on the way",
    S.arrived: "Mechanic has arrived",
    S.in_progress: "Repair in progress",
    S.completed: "Done",
    S.cancelled: "Cancelled",
    S.escalated: "A senior team member is looking into it",
}
# The usual path, for the "what comes next" part of the customer's timeline.
HAPPY_PATH = [S.submitted, S.triaged, S.accepted, S.en_route, S.arrived, S.in_progress, S.completed]


class TransitionError(ValueError):
    """Not an allowed move (shown to the agent as it is)."""


@dataclass
class Actor:
    id: uuid.UUID | None
    label: str


def allowed(current: RequestStatus) -> list[str]:
    return sorted(s.value for s in TRANSITIONS[RequestStatus(current)])


def check(req: ServiceRequest, to: RequestStatus) -> None:
    current = RequestStatus(req.status)
    if to not in TRANSITIONS[current]:
        moves = ", ".join(allowed(current)) or "none (it is closed)"
        raise TransitionError(f"A request that is {current} cannot become {to}. Allowed: {moves}.")


def move(
    session: Session,
    req: ServiceRequest,
    to: RequestStatus,
    actor: Actor,
    note: str = "",
    data: dict | None = None,
) -> RequestEvent:
    """Change the status (an allowed move) and record the event. Callers check the move's own rules first."""
    check(req, to)
    event = RequestEvent(
        request_id=req.id,
        at=datetime.now(UTC),
        kind=EventKind.status,
        from_status=str(req.status),
        to_status=str(to),
        actor_id=actor.id,
        actor_label=actor.label,
        note=note,
        data=data or {},
    )
    req.status, req.status_changed_at = to, event.at
    session.add(event)
    if to in (S.cancelled, S.escalated, S.triaged):
        _close_open_assignment(session, req, AssignmentStatus.withdrawn, actor, f"request {to}")
    session.flush()
    # Notifications for this event (offered -> mechanic, accepted ... completed -> customer, escalated -> support),
    # recorded in this transaction and sent by the worker after commit (app/notify/service.py).
    from app.notify import service as notify

    notify.on_status(session, req, to, event)
    return event


def transition(session: Session, req: ServiceRequest, to: RequestStatus, actor: Actor, note: str = "") -> RequestEvent:
    """A plain status change from the admin app. Offers, answers and completion have their own actions."""
    to = RequestStatus(to)
    check(req, to)
    if to in VIA_ACTION:
        raise TransitionError(f"To make it {to}, {VIA_ACTION[to]}.")
    if to in (S.cancelled, S.escalated) and not note.strip():
        raise TransitionError(f"Say why it is {to} (a short note).")
    if req.status == S.submitted and to == S.triaged and req.assigned_agent_id is None:
        req.assigned_agent_id = actor.id  # the agent who triages it owns it
    return move(session, req, to, actor, note)


def event(session: Session, req: ServiceRequest, kind: EventKind, actor: Actor, note: str, data: dict) -> None:
    session.add(
        RequestEvent(
            request_id=req.id,
            at=datetime.now(UTC),
            kind=kind,
            actor_id=actor.id,
            actor_label=actor.label,
            note=note,
            data=data,
        )
    )


def open_assignment(session: Session, req: ServiceRequest) -> RequestAssignment | None:
    return session.scalar(
        select(RequestAssignment).where(RequestAssignment.request_id == req.id, RequestAssignment.status.in_(OPEN))
    )


def _close_open_assignment(session: Session, req: ServiceRequest, status: AssignmentStatus, actor: Actor, why: str):
    a = open_assignment(session, req)
    if a is not None:
        a.status, a.responded_at = status, a.responded_at or datetime.now(UTC)
        a.note = (a.note + f" · {why} ({actor.label})").strip(" ·")
    return a


def offer(session: Session, req: ServiceRequest, mechanic_id: int, actor: Actor, match: dict, note: str = ""):
    """Offer the job to a mechanic (the agent called them): status offered, one open assignment."""
    if req.status != S.triaged:
        raise TransitionError(f"Only a triaged request can be offered to a mechanic (this one is {req.status}).")
    a = RequestAssignment(
        request_id=req.id,
        mechanic_id=mechanic_id,
        offered_by_id=actor.id,
        offered_by=actor.label,
        match=match,
        note=note,
    )
    session.add(a)
    session.flush()
    event(session, req, EventKind.offer, actor, note, {"mechanic_id": mechanic_id, "assignment_id": a.id})
    move(session, req, S.offered, actor, note, {"mechanic_id": mechanic_id})
    return a


def respond(session: Session, req: ServiceRequest, accepted: bool, actor: Actor, note: str = "") -> RequestAssignment:
    """Record the mechanic's answer: accepted (status accepted) or declined (back to triaged, offer someone else)."""
    a = open_assignment(session, req)
    if req.status != S.offered or a is None or a.status != AssignmentStatus.offered:
        raise TransitionError("There is no open offer to answer.")
    a.status = AssignmentStatus.accepted if accepted else AssignmentStatus.declined
    a.responded_at = datetime.now(UTC)
    if note:
        a.note = (a.note + " · " + note).strip(" ·")
    event(session, req, EventKind.response, actor, note, {"mechanic_id": a.mechanic_id, "accepted": accepted})
    session.flush()
    move(session, req, S.accepted if accepted else S.triaged, actor, note, {"mechanic_id": a.mechanic_id})
    return a


def complete(session: Session, req: ServiceRequest, actor: Actor) -> RequestEvent:
    """Mark the job done (called by record_outcome after the confirmed fault is stored)."""
    if req.status != S.in_progress:
        raise TransitionError(f"Only a job in progress can be completed (this one is {req.status}).")
    a = open_assignment(session, req)
    if a is not None:
        a.status = AssignmentStatus.completed
    return move(session, req, S.completed, actor)
