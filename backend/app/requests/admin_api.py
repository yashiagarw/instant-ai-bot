"""/api/admin/requests: the support queue and one request's workflow (app/requests/workflow.py).

The queue puts safety-critical requests first (safety_level high, from the diagnosis), then urgent ones, then the
oldest. Customer phone numbers are always masked; only the agent who owns the request (assigned_agent_id) can reveal
the full number, and every reveal is written to the audit log. Every status change writes a request_event and an
audit entry."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.models import StaffUser
from app.admin.permissions import Perm
from app.datasets.pipeline import live_version
from app.db import get_session
from app.diagnosis.models import DiagnosisSession, SessionResult
from app.knowledge.models import Category, Fault
from app.mechanics import matching
from app.mechanics.geo import locate
from app.mechanics.models import Mechanic
from app.requests import outcomes, workflow
from app.requests.models import (
    EventKind,
    RequestAssignment,
    RequestEvent,
    RequestNote,
    RequestOutcome,
    RequestStatus,
    SafetyLevel,
    ServiceRequest,
)

router = APIRouter(prefix="/admin/requests", tags=["admin"], dependencies=[Depends(enforce)])
DbSession = Annotated[Session, Depends(get_session)]
CLOSED = (RequestStatus.completed, RequestStatus.cancelled)
SAFETY_ORDER = case(
    {SafetyLevel.high: 0, SafetyLevel.medium: 1, SafetyLevel.low: 2},
    value=ServiceRequest.safety_level,
    else_=3,
)


# ---------------------------------------------------------------- schemas


class QueueRow(BaseModel):
    id: uuid.UUID
    reference: str
    created_at: datetime
    age_minutes: int
    status: RequestStatus
    safety_level: SafetyLevel
    urgent: bool
    name: str
    phone: str = Field(description="Always masked (last 4 digits): reveal it from the request's page")
    area: str
    pincode: str
    service_type: str
    category_code: str | None
    category: str | None
    vehicle: str
    problem_summary: str
    agent: str | None
    mechanic: str | None
    session_id: uuid.UUID | None


class Cause(BaseModel):
    rank: int
    fault_key: str
    name: str | None
    confidence: str


class AssignmentOut(BaseModel):
    id: int
    mechanic_id: int
    mechanic: str
    status: str
    offered_at: datetime
    responded_at: datetime | None
    offered_by: str
    match: dict
    note: str


class EventOut(BaseModel):
    id: int
    at: datetime
    kind: EventKind
    from_status: str | None
    to_status: str | None
    actor: str
    note: str
    data: dict


class NoteOut(BaseModel):
    id: int
    created_at: datetime
    author: str
    text: str


class OutcomeOut(BaseModel):
    confirmed_fault_key: str | None
    confirmed_fault: str | None
    other_text: str
    ai_top1: bool | None
    ai_top3: bool | None
    ai_ranked: list
    parts_used: list
    final_cost_inr: int | None
    mechanic_notes: str
    dataset_version_id: int | None
    mechanic_id: int | None
    recorded_by: str
    recorded_at: datetime


class RequestDetail(QueueRow):
    address: str
    preferred_time: str
    notes_from_customer: str
    phone_revealable: bool = Field(description="True for the agent who owns this request (and can call)")
    point: dict | None = Field(description="{lat, lon, precision}: the pincode's centre (approximate)")
    causes: list[Cause]
    allowed: list[str] = Field(description="Statuses it can move to")
    assignments: list[AssignmentOut]
    events: list[EventOut]
    internal_notes: list[NoteOut]
    outcome: OutcomeOut | None


class TransitionIn(BaseModel):
    status: RequestStatus
    note: str = Field(default="", max_length=1000)


class AgentIn(BaseModel):
    staff_user_id: uuid.UUID | None = Field(default=None, description="Empty = me")


class OfferIn(BaseModel):
    mechanic_id: int
    note: str = Field(default="", max_length=500)


class ResponseIn(BaseModel):
    accepted: bool
    note: str = Field(default="", max_length=500)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class PartUsed(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(default=1, ge=1, le=100)
    price_inr: int | None = Field(default=None, ge=0, le=10_000_000)


class OutcomeIn(BaseModel):
    confirmed_fault_key: str = Field(min_length=1, description='A fault key, or "other" with other_text')
    other_text: str = Field(default="", max_length=500)
    parts_used: list[PartUsed] = Field(default_factory=list, max_length=50)
    final_cost_inr: int | None = Field(default=None, ge=0, le=10_000_000)
    mechanic_notes: str = Field(default="", max_length=2000)


class PhoneOut(BaseModel):
    phone: str


class SuggestionOut(BaseModel):
    mechanic_id: int
    name: str
    score: float
    distance_km: float | None
    rating: float | None
    acceptance_rate: float | None
    jobs_today: int
    max_jobs_per_day: int
    reasons: list[str]


class ExcludedOut(BaseModel):
    mechanic_id: int
    name: str
    reasons: list[str]


class FaultOption(BaseModel):
    fault_key: str
    name: str
    category_code: str
    ai_rank: int | None = Field(description="1-3 when the diagnosis ranked it in its top 3")


class SuggestionsOut(BaseModel):
    category_code: str | None
    point: dict | None
    notes: list[str]
    suggestions: list[SuggestionOut]
    excluded: list[ExcludedOut]


# ---------------------------------------------------------------- helpers


def _vehicle(v: dict) -> str:
    return " ".join(str(v.get(k)) for k in ("make", "model", "variant") if v.get(k)) or ""


def _actor(staff) -> workflow.Actor:
    return workflow.Actor(staff.user.id, staff.label)


def _get(session: Session, request_id: uuid.UUID) -> ServiceRequest:
    r = session.get(ServiceRequest, request_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return r


def _row(r: ServiceRequest, now: datetime, agents: dict, mechanics: dict, categories: dict) -> dict:
    return {
        "id": r.id,
        "reference": r.reference,
        "created_at": r.created_at,
        "age_minutes": max(0, int((now - r.created_at).total_seconds() // 60)),
        "status": r.status,
        "safety_level": r.safety_level,
        "urgent": r.urgent,
        "name": r.name,
        "phone": audit.mask_phone(r.phone),
        "area": r.area_text,
        "pincode": r.pincode,
        "service_type": str(r.service_type),
        "category_code": r.category_code,
        "category": categories.get(r.category_code),
        "vehicle": _vehicle(r.vehicle_snapshot or {}),
        "problem_summary": r.problem_summary,
        "agent": agents.get(r.assigned_agent_id),
        "mechanic": mechanics.get(r.id),
        "session_id": r.session_id,
    }


def _lookups(session: Session, rows: list[ServiceRequest]) -> tuple[dict, dict, dict]:
    ids = [r.id for r in rows]
    agent_ids = {r.assigned_agent_id for r in rows if r.assigned_agent_id}
    agents = dict(session.execute(select(StaffUser.id, StaffUser.name).where(StaffUser.id.in_(agent_ids))).all())
    # The mechanic of each request's latest assignment.
    latest = (
        select(RequestAssignment.request_id, func.max(RequestAssignment.id).label("aid"))
        .where(RequestAssignment.request_id.in_(ids))
        .group_by(RequestAssignment.request_id)
        .subquery()
    )
    mechanics = dict(
        session.execute(
            select(latest.c.request_id, Mechanic.name)
            .join(RequestAssignment, RequestAssignment.id == latest.c.aid)
            .join(Mechanic, Mechanic.id == RequestAssignment.mechanic_id)
        ).all()
    )
    categories = dict(session.execute(select(Category.code, Category.name)).all())
    return agents, mechanics, categories


def _audit_status(session: Session, staff, r: ServiceRequest, before: str, note: str = "") -> None:
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="request.set_status",
        entity_type="service_request",
        entity_id=r.id,
        before={"status": before},
        after={"status": str(r.status), **({"note": note} if note else {})},
        ip=staff.ip,
    )


def _detail(session: Session, r: ServiceRequest, staff) -> RequestDetail:
    now = datetime.now(UTC)
    agents, mechanics, categories = _lookups(session, [r])
    causes = []
    if r.session_id:
        res = session.execute(
            select(SessionResult.rank, SessionResult.fault_key, SessionResult.confidence)
            .where(SessionResult.session_id == r.session_id, SessionResult.rank <= 3)
            .order_by(SessionResult.rank)
        ).all()
        names = dict(
            session.execute(select(Fault.fault_key, Fault.name).where(Fault.fault_key.in_([x[1] for x in res]))).all()
        )
        causes = [Cause(rank=rk, fault_key=k, name=names.get(k), confidence=str(c)) for rk, k, c in res]
    m_names = dict(session.execute(select(Mechanic.id, Mechanic.name)).all())
    assignments = [
        AssignmentOut(
            id=a.id,
            mechanic_id=a.mechanic_id,
            mechanic=m_names.get(a.mechanic_id, "?"),
            status=str(a.status),
            offered_at=a.offered_at,
            responded_at=a.responded_at,
            offered_by=a.offered_by,
            match=a.match,
            note=a.note,
        )
        for a in session.scalars(
            select(RequestAssignment).where(RequestAssignment.request_id == r.id).order_by(RequestAssignment.id)
        )
    ]
    events = [
        EventOut(
            id=e.id,
            at=e.at,
            kind=e.kind,
            from_status=e.from_status,
            to_status=e.to_status,
            actor=e.actor_label,
            note=e.note,
            data=e.data,
        )
        for e in session.scalars(
            select(RequestEvent).where(RequestEvent.request_id == r.id).order_by(RequestEvent.at, RequestEvent.id)
        )
    ]
    notes = [
        NoteOut(id=n.id, created_at=n.created_at, author=n.author_label, text=n.text)
        for n in session.scalars(select(RequestNote).where(RequestNote.request_id == r.id).order_by(RequestNote.id))
    ]
    o = session.get(RequestOutcome, r.id)
    outcome = None
    if o is not None:
        fault = session.scalar(select(Fault.name).where(Fault.fault_key == o.confirmed_fault_key).limit(1))
        outcome = OutcomeOut(
            confirmed_fault_key=o.confirmed_fault_key,
            confirmed_fault=fault,
            other_text=o.other_text,
            ai_top1=o.ai_top1,
            ai_top3=o.ai_top3,
            ai_ranked=o.ai_ranked,
            parts_used=o.parts_used,
            final_cost_inr=o.final_cost_inr,
            mechanic_notes=o.mechanic_notes,
            dataset_version_id=o.dataset_version_id,
            mechanic_id=o.mechanic_id,
            recorded_by=o.recorded_by,
            recorded_at=o.recorded_at,
        )
    point = locate(r.pincode)
    return RequestDetail(
        **_row(r, now, agents, mechanics, categories),
        address=r.address,
        preferred_time=r.preferred_time,
        notes_from_customer=r.notes,
        phone_revealable=_can_reveal(r, staff),
        point={"lat": point.lat, "lon": point.lon, "precision": point.precision} if point else None,
        causes=causes,
        allowed=workflow.allowed(r.status),
        assignments=assignments,
        events=events,
        internal_notes=notes,
        outcome=outcome,
    )


def _can_reveal(r: ServiceRequest, staff) -> bool:
    return Perm.requests_contact in staff.perms and r.assigned_agent_id == staff.user.id


def _done(session: Session, r: ServiceRequest, staff) -> RequestDetail:
    session.commit()
    session.refresh(r)
    return _detail(session, r, staff)


def _workflow_error(e: workflow.TransitionError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(e))


# ---------------------------------------------------------------- queue and detail


@router.get("", response_model=list[QueueRow])
@requires(Perm.requests_read)
def queue(
    staff: CurrentStaff,
    session: DbSession,
    status_filter: Annotated[list[RequestStatus] | None, Query(alias="status")] = None,
    view: Annotated[Literal["open", "closed", "all"], Query()] = "open",
    safety: Annotated[SafetyLevel | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    mine: Annotated[bool, Query()] = False,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    """Safety-critical first, then urgent, then the oldest (closed requests: newest first)."""
    stmt = select(ServiceRequest)
    if status_filter:
        stmt = stmt.where(ServiceRequest.status.in_(status_filter))
    elif view == "open":
        stmt = stmt.where(ServiceRequest.status.not_in(CLOSED))
    elif view == "closed":
        stmt = stmt.where(ServiceRequest.status.in_(CLOSED))
    if safety:
        stmt = stmt.where(ServiceRequest.safety_level == safety)
    if category:
        stmt = stmt.where(ServiceRequest.category_code == category)
    if mine:
        stmt = stmt.where(ServiceRequest.assigned_agent_id == staff.user.id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                ServiceRequest.reference.ilike(like),
                ServiceRequest.name.ilike(like),
                ServiceRequest.area_text.ilike(like),
                ServiceRequest.pincode.ilike(like),
            )
        )
    if view == "closed":
        stmt = stmt.order_by(ServiceRequest.created_at.desc())
    else:
        stmt = stmt.order_by(SAFETY_ORDER, ServiceRequest.urgent.desc(), ServiceRequest.created_at)
    rows = list(session.scalars(stmt.limit(limit)))
    now = datetime.now(UTC)
    agents, mechanics, categories = _lookups(session, rows)
    return [QueueRow(**_row(r, now, agents, mechanics, categories)) for r in rows]


@router.get("/{request_id}", response_model=RequestDetail, responses={404: {}})
@requires(Perm.requests_read)
def get_request(request_id: uuid.UUID, staff: CurrentStaff, session: DbSession):
    return _detail(session, _get(session, request_id), staff)


@router.post("/{request_id}/reveal-phone", response_model=PhoneOut, responses={403: {}, 404: {}})
@requires(Perm.requests_contact)
def reveal_phone(request_id: uuid.UUID, staff: CurrentStaff, session: DbSession, response: Response):
    """The customer's full number, for the agent who owns the request. Every reveal is written to the audit log."""
    response.headers["Cache-Control"] = "no-store"
    r = _get(session, request_id)
    if not _can_reveal(r, staff):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the agent assigned to this request can see the number")
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="request.reveal_phone",
        entity_type="service_request",
        entity_id=r.id,
        after={"phone": r.phone},  # masked by the audit helper
        ip=staff.ip,
    )
    session.commit()
    return PhoneOut(phone=r.phone)


# ---------------------------------------------------------------- workflow


@router.patch("/{request_id}", response_model=RequestDetail, responses={404: {}, 409: {}})
@requires(Perm.requests_update)
def change_status(request_id: uuid.UUID, body: TransitionIn, staff: CurrentStaff, session: DbSession):
    """A plain status change (triaged, en_route, arrived, in_progress, cancelled, escalated). Offers, the mechanic's
    answer and completion have their own actions."""
    r = _get(session, request_id)
    before = str(r.status)
    try:
        workflow.transition(session, r, body.status, _actor(staff), body.note)
    except workflow.TransitionError as e:
        raise _workflow_error(e) from e
    _audit_status(session, staff, r, before, body.note)
    return _done(session, r, staff)


@router.put("/{request_id}/agent", response_model=RequestDetail, responses={404: {}, 422: {}})
@requires(Perm.requests_update)
def set_agent(request_id: uuid.UUID, body: AgentIn, staff: CurrentStaff, session: DbSession):
    """Who owns the request (and can see the customer's number). Empty = me."""
    r = _get(session, request_id)
    target = body.staff_user_id or staff.user.id
    if target != staff.user.id and Perm.staff_manage not in staff.perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a super admin can give a request to someone else")
    agent = session.get(StaffUser, target)
    if agent is None or not agent.active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown or inactive staff member")
    before = r.assigned_agent_id
    r.assigned_agent_id = target
    workflow.event(session, r, EventKind.agent, _actor(staff), "", {"agent": agent.name})
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="request.set_agent",
        entity_type="service_request",
        entity_id=r.id,
        before={"agent_id": str(before) if before else None},
        after={"agent_id": str(target)},
        ip=staff.ip,
    )
    return _done(session, r, staff)


@router.get("/{request_id}/suggestions", response_model=SuggestionsOut, responses={404: {}})
@requires(Perm.requests_read)
def suggestions(request_id: uuid.UUID, staff: CurrentStaff, session: DbSession):
    """Mechanics who fit (on duty, zone, skill, capacity), best first, with reasons; and who doesn't, and why."""
    r = _get(session, request_id)
    m = matching.suggest(session, r)
    return SuggestionsOut(
        category_code=m.category_code,
        point={"lat": m.request_point.lat, "lon": m.request_point.lon, "precision": m.request_point.precision}
        if m.request_point
        else None,
        notes=m.notes,
        suggestions=[SuggestionOut(**s.__dict__) for s in m.suggestions],
        excluded=[ExcludedOut(**x.__dict__) for x in m.excluded],
    )


@router.get("/{request_id}/faults", response_model=list[FaultOption], responses={404: {}})
@requires(Perm.requests_read)
def fault_options(request_id: uuid.UUID, staff: CurrentStaff, session: DbSession):
    """What the confirmed fault can be when the job is completed: the diagnosis's top 3 first, then the other faults
    of the request's category (from the diagnosis's dataset version, else the live one). "other" is always allowed."""
    r = _get(session, request_id)
    ds = session.get(DiagnosisSession, r.session_id) if r.session_id else None
    version_id = ds.dataset_version_id if ds and ds.dataset_version_id else getattr(live_version(session), "id", None)
    ranked = (
        dict(
            session.execute(
                select(SessionResult.fault_key, SessionResult.rank).where(
                    SessionResult.session_id == ds.id, SessionResult.rank <= 3
                )
            ).all()
        )
        if ds
        else {}
    )
    if version_id is None:
        return []
    cond = Fault.fault_key.in_(list(ranked))
    if r.category_code:
        cond = or_(cond, Fault.category_code == r.category_code)
    rows = session.execute(
        select(Fault.fault_key, Fault.name, Fault.category_code).where(Fault.dataset_version_id == version_id, cond)
    ).all()
    options = [FaultOption(fault_key=k, name=n, category_code=c, ai_rank=ranked.get(k)) for k, n, c in rows]
    return sorted(options, key=lambda o: (o.ai_rank or 99, o.fault_key))


@router.post("/{request_id}/offer", response_model=RequestDetail, responses={404: {}, 409: {}, 422: {}})
@requires(Perm.requests_update)
def offer(request_id: uuid.UUID, body: OfferIn, staff: CurrentStaff, session: DbSession):
    """Offer the job to a mechanic (after calling them). Usually one of the suggestions; another mechanic is allowed
    with a note saying why."""
    r = _get(session, request_id)
    mech = session.get(Mechanic, body.mechanic_id)
    if mech is None or not mech.active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown or inactive mechanic")
    found = matching.suggest(session, r, limit=1000)
    match = next((s for s in found.suggestions if s.mechanic_id == mech.id), None)
    if match is None:
        why = next((x.reasons for x in found.excluded if x.mechanic_id == mech.id), [])
        if not body.note.strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{mech.name} is not a suggestion ({'; '.join(why)}): add a note saying why you're offering anyway",
            )
        snapshot = {"suggested": False, "reasons": why}
    else:
        snapshot = {"suggested": True, "score": match.score, "distance_km": match.distance_km, "reasons": match.reasons}
    before = str(r.status)
    try:
        workflow.offer(session, r, mech.id, _actor(staff), snapshot, body.note)
    except workflow.TransitionError as e:
        raise _workflow_error(e) from e
    _audit_status(session, staff, r, before, f"offered to mechanic {mech.id}")
    return _done(session, r, staff)


@router.post("/{request_id}/response", response_model=RequestDetail, responses={404: {}, 409: {}})
@requires(Perm.requests_update)
def mechanic_response(request_id: uuid.UUID, body: ResponseIn, staff: CurrentStaff, session: DbSession):
    """Record the mechanic's answer (they told the agent): accepted, or declined (back to triaged)."""
    r = _get(session, request_id)
    before = str(r.status)
    try:
        workflow.respond(session, r, body.accepted, _actor(staff), body.note)
    except workflow.TransitionError as e:
        raise _workflow_error(e) from e
    _audit_status(session, staff, r, before, body.note)
    return _done(session, r, staff)


@router.post("/{request_id}/notes", response_model=RequestDetail, status_code=201, responses={404: {}})
@requires(Perm.requests_update)
def add_note(request_id: uuid.UUID, body: NoteIn, staff: CurrentStaff, session: DbSession):
    """An internal note (never shown to the customer)."""
    r = _get(session, request_id)
    session.add(RequestNote(request_id=r.id, author_id=staff.user.id, author_label=staff.label, text=body.text.strip()))
    return _done(session, r, staff)


@router.post("/{request_id}/outcome", response_model=RequestDetail, responses={404: {}, 409: {}, 422: {}})
@requires(Perm.requests_update)
def record_outcome(request_id: uuid.UUID, body: OutcomeIn, staff: CurrentStaff, session: DbSession):
    """Complete the job with the confirmed fault (training data): fault key or "other", parts, final cost, notes.
    Compared with the diagnosis's top causes and stored with its dataset version."""
    r = _get(session, request_id)
    before = str(r.status)
    try:
        outcomes.record(
            session,
            r,
            outcomes.OutcomeIn(
                confirmed_fault_key=body.confirmed_fault_key,
                other_text=body.other_text,
                parts_used=[p.model_dump() for p in body.parts_used],
                final_cost_inr=body.final_cost_inr,
                mechanic_notes=body.mechanic_notes,
            ),
            _actor(staff),
        )
    except outcomes.OutcomeInvalid as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    except workflow.TransitionError as e:
        raise _workflow_error(e) from e
    _audit_status(session, staff, r, before, f"confirmed fault {body.confirmed_fault_key}")
    return _done(session, r, staff)
