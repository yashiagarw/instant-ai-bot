"""/api/mechanic: the mechanic app (/m in apps/web). A mechanic sees only their own offers and jobs; anything else is
404. Before accepting, an offer shows the job type, car, diagnosis summary and the approximate area (zone and
pincode) only; the full address, a map link and the customer's masked number (calls go through the masked call
provider) appear once they accept.

    POST /auth/otp/request, /auth/otp/verify, /auth/logout     sign in with a phone code (active, verified only)
    GET  /me                                                   profile, on duty, photo, today's numbers
    PUT  /availability                                         on / off duty (audited)
    GET  /offers                                               my open offers (with the seconds left)
    POST /offers/{id}/accept, /offers/{id}/reject              the same path as WhatsApp (dispatch.answer)
    GET  /jobs, /jobs/{id}                                     my accepted jobs (today's and open ones)
    POST /jobs/{id}/status                                     en_route, arrived, in_progress, completed (+ fault)
    POST /jobs/{id}/eta                                        "I'll be there in N minutes" (shown to the customer)
    GET  /jobs/{id}/faults?q=                                  the confirmed-fault picker (Hindi names)
    POST /jobs/{id}/call                                       call the customer (masked)
    POST/DELETE /push-subscriptions                            job offers as alerts on this phone
"""

from __future__ import annotations

import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.accounts import service as accounts
from app.accounts.api import get_sms
from app.admin import audit
from app.calls import service as calls
from app.calls.providers import CallError, make_bridge
from app.db import get_session
from app.estimates.zones import zone_for_pincode
from app.mechanics import auth
from app.mechanics.models import Mechanic
from app.notify.models import PushSubscription
from app.notify.push import allowed_endpoint
from app.notify.sms import SmsSender, mask_phone
from app.notify.templates import clean_value
from app.ratelimit import client_ip, make_limiter
from app.requests import dispatch, outcomes, workflow
from app.requests.models import AssignmentStatus, RequestAssignment, RequestStatus, ServiceRequest
from app.turnstile import require_human

router = APIRouter(prefix="/mechanic", tags=["mechanic app"])
DbSession = Annotated[Session, Depends(get_session)]
S = RequestStatus
JOB_TYPES = {"at_location": "At the car's location", "tow": "Tow", "workshop": "Workshop visit"}
# What a mechanic may move a job to, from where (the rest is support's).
NEXT = {S.accepted: S.en_route, S.en_route: S.arrived, S.arrived: S.in_progress, S.in_progress: S.completed}


def current_mechanic(request: Request, session: DbSession, im_mech: Annotated[str | None, Cookie()] = None):
    mech = auth.current(session, im_mech)
    if mech is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in")
    return mech


Me = Annotated[Mechanic, Depends(current_mechanic)]


def _limit(request: Request, name: str, limit: int, window: int) -> None:
    state = request.app.state
    key = f"mech_limiter_{name}"
    limiter = getattr(state, key, None)
    if limiter is None:
        limiter = make_limiter(state.settings, f"mechanic_{name}", limit, window)
        setattr(state, key, limiter)
    wait = limiter.check(client_ip(request, state.settings.trust_forwarded_for))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many tries. Please wait.", headers={"Retry-After": str(round(wait))}
        )


# ---------------------------------------------------------------- schemas


class PhoneIn(BaseModel):
    phone: str = Field(max_length=20)


class CodeIn(BaseModel):
    phone: str = Field(max_length=20)
    code: str = Field(max_length=6)


class MeOut(BaseModel):
    id: int
    name: str
    first_name: str
    phone_masked: str
    on_duty: bool
    photo_url: str | None
    jobs_today: int
    open_offers: int


class AvailabilityIn(BaseModel):
    on_duty: bool


class OfferOut(BaseModel):
    id: int
    reference: str
    job_type: str
    job_type_label: str
    car: str
    problem: str = Field(description="The diagnosis summary (likely cause, safety alerts)")
    area: str = Field(description="Approximate only: zone and pincode (no address before accepting)")
    distance_km: int | None = Field(description="Approximate straight-line distance from the mechanic's base")
    urgent: bool
    safety_critical: bool
    offered_at: datetime
    expires_at: datetime | None
    seconds_left: int | None


class JobOut(BaseModel):
    id: int
    request_id: uuid.UUID
    reference: str
    status: str
    job_type: str
    job_type_label: str
    car: str
    problem: str
    area: str
    address: str
    map_url: str
    customer_name: str = Field(description="First name only")
    customer_phone: str = Field(description="Masked: call through the app")
    notes: str
    urgent: bool
    safety_critical: bool
    eta_at: datetime | None
    can_call: bool
    next_status: str | None
    accepted_at: datetime | None


class StatusIn(BaseModel):
    status: Literal["en_route", "arrived", "in_progress", "completed"]
    eta_minutes: int | None = Field(default=None, ge=1, le=240, description="With en_route: the arrival estimate")
    confirmed_fault_key: str | None = Field(default=None, max_length=40, description='A fault key, or "other"')
    other_text: str = Field(default="", max_length=300, description='What it was, with "other / not sure"')
    notes: str = Field(default="", max_length=1000)


class EtaIn(BaseModel):
    minutes: int = Field(ge=1, le=240)


class FaultChoice(BaseModel):
    fault_key: str
    name: str
    name_hi: str | None = Field(description="A Hindi (Devanagari, else Hinglish) name from reviewed customer phrases")
    category: str
    ai_rank: int | None


class CallOut(BaseModel):
    status: str
    message: str


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=10, max_length=100)


class PushIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: PushKeys


class EndpointIn(BaseModel):
    endpoint: str = Field(max_length=1000)


# ---------------------------------------------------------------- helpers


def _first(name: str) -> str:
    return (name.split() or [""])[0]


def _car(req: ServiceRequest) -> str:
    v = req.vehicle_snapshot or {}
    return " ".join(str(x) for x in (v.get("make"), v.get("model"), v.get("fuel"), v.get("transmission")) if x) or (
        "Car details not given"
    )


def _area(req: ServiceRequest) -> str:
    zone = zone_for_pincode(req.pincode)
    parts = [zone.label if zone else None, f"pincode {req.pincode}" if req.pincode else None]
    return ", ".join(p for p in parts if p) or "Area to be confirmed by support"


def _offer(a: RequestAssignment, req: ServiceRequest, now: datetime) -> OfferOut:
    km = a.match.get("distance_km") if a.match else None
    left = int((a.expires_at - now).total_seconds()) if a.expires_at else None
    return OfferOut(
        id=a.id,
        reference=req.reference,
        job_type=str(req.service_type),
        job_type_label=JOB_TYPES.get(str(req.service_type), str(req.service_type)),
        car=_car(req),
        problem=clean_value(req.problem_summary or "Not diagnosed: support will tell you", 300),
        area=_area(req),
        distance_km=round(km) if isinstance(km, int | float) else None,
        urgent=req.urgent,
        safety_critical=str(req.safety_level) == "high",
        offered_at=a.offered_at,
        expires_at=a.expires_at,
        seconds_left=max(0, left) if left is not None else None,
    )


def _job(a: RequestAssignment, req: ServiceRequest) -> JobOut:
    address = ", ".join(x for x in (req.address, req.area_text, req.pincode) if x)
    nxt = NEXT.get(RequestStatus(req.status)) if a.status == AssignmentStatus.accepted else None
    return JobOut(
        id=a.id,
        request_id=req.id,
        reference=req.reference,
        status=str(req.status),
        job_type=str(req.service_type),
        job_type_label=JOB_TYPES.get(str(req.service_type), str(req.service_type)),
        car=_car(req),
        problem=clean_value(req.problem_summary or "Not diagnosed", 300),
        area=_area(req),
        address=address,
        map_url="https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(address + ", India"),
        customer_name=_first(req.name) or "Customer",
        customer_phone=mask_phone(req.phone),
        notes=clean_value(req.notes, 500) if req.notes else "",
        urgent=req.urgent,
        safety_critical=str(req.safety_level) == "high",
        eta_at=req.eta_at,
        can_call=calls.can_call(req),
        next_status=str(nxt) if nxt else None,
        accepted_at=a.responded_at,
    )


def _my_offer(session: Session, me: Mechanic, offer_id: int) -> RequestAssignment:
    a = session.get(RequestAssignment, offer_id)
    if a is None or a.mechanic_id != me.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return a


def _my_job(session: Session, me: Mechanic, job_id: int) -> tuple[RequestAssignment, ServiceRequest]:
    a = session.get(RequestAssignment, job_id)
    if a is None or a.mechanic_id != me.id or a.status not in (AssignmentStatus.accepted, AssignmentStatus.completed):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return a, session.get(ServiceRequest, a.request_id)


def _actor(me: Mechanic) -> workflow.Actor:
    return workflow.Actor(None, f"{_first(me.name) or 'Mechanic'} (mechanic, app)")


def _audit(session: Session, me: Mechanic, action: str, entity_type: str, entity_id, before, after) -> None:
    audit.record(
        session,
        actor_id=None,
        actor_label=_actor(me).label,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
    )


def _today_start(now: datetime) -> datetime:
    from app.mechanics.matching import today_start_utc

    return today_start_utc(now)


# ---------------------------------------------------------------- sign in


@router.post(
    "/auth/otp/request", status_code=202, responses={403: {}, 422: {}, 429: {}}, dependencies=[Depends(require_human)]
)
def otp_request(body: PhoneIn, request: Request, session: DbSession, sms: Annotated[SmsSender, Depends(get_sms)]):
    """Send a sign-in code. The same answer whether or not the number is a mechanic's (no guessing who works here)."""
    _limit(request, "otp", request.app.state.settings.otp_ip_limit, request.app.state.settings.otp_ip_window_seconds)
    try:
        masked = auth.request_code(session, request.app.state.settings, sms, body.phone)
    except accounts.TooMany as e:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, str(e), headers={"Retry-After": str(round(e.retry_after))}
        ) from e
    except accounts.AuthError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    session.commit()
    return {"sent": True, "phone_masked": masked}


@router.post("/auth/otp/verify", responses={400: {}, 403: {}, 429: {}})
def otp_verify(body: CodeIn, request: Request, response: Response, session: DbSession):
    settings = request.app.state.settings
    _limit(request, "verify", settings.otp_verify_ip_limit, settings.otp_verify_ip_window_seconds)
    try:
        mech, token = auth.verify(session, settings, body.phone, body.code)
    except auth.MechanicAuthError as e:
        session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from e
    except accounts.AuthError as e:
        session.commit()  # count the wrong try
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    session.commit()
    response.set_cookie(
        auth.COOKIE,
        token,
        max_age=settings.mechanic_session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=auth.COOKIE_PATH,
    )
    return {"ok": True, "first_name": _first(mech.name)}


@router.post("/auth/logout")
def logout(request: Request, response: Response, session: DbSession, im_mech: Annotated[str | None, Cookie()] = None):
    auth.logout(session, im_mech)
    session.commit()
    response.delete_cookie(
        auth.COOKIE,
        path=auth.COOKIE_PATH,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
    )
    return {"ok": True}


# ---------------------------------------------------------------- profile and availability


def _me_out(session: Session, request: Request, me: Mechanic) -> MeOut:
    now = datetime.now(UTC)
    photo = None
    if me.photo_key:
        from app.uploads.api import get_storage

        try:
            photo = get_storage(request).presign_view(me.photo_key, request.app.state.settings.upload_view_ttl_seconds)
        except Exception:  # storage down: no photo, the rest works
            photo = None
    jobs = session.scalar(
        select(func.count())
        .select_from(RequestAssignment)
        .where(
            RequestAssignment.mechanic_id == me.id,
            RequestAssignment.status.in_([AssignmentStatus.accepted, AssignmentStatus.completed]),
            RequestAssignment.responded_at >= _today_start(now),
        )
    )
    offers = session.scalar(
        select(func.count())
        .select_from(RequestAssignment)
        .where(
            RequestAssignment.mechanic_id == me.id,
            RequestAssignment.status == AssignmentStatus.offered,
            or_(RequestAssignment.expires_at.is_(None), RequestAssignment.expires_at > now),
        )
    )
    return MeOut(
        id=me.id,
        name=me.name,
        first_name=_first(me.name),
        phone_masked=mask_phone(me.phone),
        on_duty=me.on_duty,
        photo_url=photo,
        jobs_today=jobs or 0,
        open_offers=offers or 0,
    )


@router.get("/me", response_model=MeOut)
def me_(request: Request, me: Me, session: DbSession):
    session.commit()  # last_seen_at
    return _me_out(session, request, me)


@router.put("/availability", response_model=MeOut)
def availability(body: AvailabilityIn, request: Request, me: Me, session: DbSession):
    before = me.on_duty
    me.on_duty, me.on_duty_changed_at = body.on_duty, datetime.now(UTC)
    _audit(session, me, "mechanic.duty", "mechanic", me.id, {"on_duty": before}, {"on_duty": body.on_duty})
    session.commit()
    return _me_out(session, request, me)


# ---------------------------------------------------------------- offers


@router.get("/offers", response_model=list[OfferOut])
def offers(me: Me, session: DbSession):
    now = datetime.now(UTC)
    rows = session.execute(
        select(RequestAssignment, ServiceRequest)
        .join(ServiceRequest, ServiceRequest.id == RequestAssignment.request_id)
        .where(
            RequestAssignment.mechanic_id == me.id,
            RequestAssignment.status == AssignmentStatus.offered,
            ServiceRequest.status == S.offered,
            or_(RequestAssignment.expires_at.is_(None), RequestAssignment.expires_at > now),
        )
        .order_by(RequestAssignment.offered_at.desc())
    ).all()
    return [_offer(a, r, now) for a, r in rows]


def _answer(session: Session, me: Mechanic, offer_id: int, accept: bool):
    a = _my_offer(session, me, offer_id)
    try:
        dispatch.answer(session, a, me, accept, "app")
    except dispatch.AnswerRefused as e:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"This offer can't be answered: {e.reason}.") from e
    session.commit()
    return a


@router.post("/offers/{offer_id}/accept", response_model=JobOut, responses={404: {}, 409: {}})
def accept(offer_id: int, me: Me, session: DbSession):
    a = _answer(session, me, offer_id, True)
    return _job(a, session.get(ServiceRequest, a.request_id))


@router.post("/offers/{offer_id}/reject", responses={404: {}, 409: {}})
def reject(offer_id: int, me: Me, session: DbSession):
    _answer(session, me, offer_id, False)
    return {"ok": True}


# ---------------------------------------------------------------- jobs


@router.get("/jobs", response_model=list[JobOut])
def jobs(me: Me, session: DbSession):
    """Open jobs, and jobs finished today."""
    since = _today_start(datetime.now(UTC))
    rows = session.execute(
        select(RequestAssignment, ServiceRequest)
        .join(ServiceRequest, ServiceRequest.id == RequestAssignment.request_id)
        .where(
            RequestAssignment.mechanic_id == me.id,
            or_(
                RequestAssignment.status == AssignmentStatus.accepted,
                (RequestAssignment.status == AssignmentStatus.completed) & (ServiceRequest.status_changed_at >= since),
            ),
        )
        .order_by(RequestAssignment.status, RequestAssignment.responded_at.desc())
    ).all()
    return [_job(a, r) for a, r in rows]


@router.get("/jobs/{job_id}", response_model=JobOut, responses={404: {}})
def job(job_id: int, me: Me, session: DbSession):
    return _job(*_my_job(session, me, job_id))


@router.post("/jobs/{job_id}/status", response_model=JobOut, responses={404: {}, 409: {}, 422: {}})
def set_status(job_id: int, body: StatusIn, me: Me, session: DbSession):
    a, req = _my_job(session, me, job_id)
    req = session.get(ServiceRequest, req.id, with_for_update=True)
    to = RequestStatus(body.status)
    if a.status != AssignmentStatus.accepted or NEXT.get(RequestStatus(req.status)) != to:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This job is {req.status}: it can't become {to} now.")
    before = str(req.status)
    try:
        if to == S.completed:
            if not body.confirmed_fault_key:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, 'Pick the fault you found, or "other".')
            outcomes.record(
                session,
                req,
                outcomes.OutcomeIn(
                    confirmed_fault_key=body.confirmed_fault_key, other_text=body.other_text, mechanic_notes=body.notes
                ),
                _actor(me),
            )
        else:
            workflow.transition(session, req, to, _actor(me))
            if to == S.en_route and body.eta_minutes:
                _set_eta(req, body.eta_minutes)
    except outcomes.OutcomeInvalid as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    except workflow.TransitionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    _audit(session, me, "request.set_status", "service_request", req.id, {"status": before}, {"status": str(to)})
    session.commit()
    return _job(session.get(RequestAssignment, a.id), req)


def _set_eta(req: ServiceRequest, minutes: int) -> None:
    now = datetime.now(UTC)
    req.eta_at, req.eta_set_at = now + timedelta(minutes=minutes), now


@router.post("/jobs/{job_id}/eta", response_model=JobOut, responses={404: {}, 409: {}})
def set_eta(job_id: int, body: EtaIn, me: Me, session: DbSession):
    a, req = _my_job(session, me, job_id)
    if req.status not in (S.accepted, S.en_route):
        raise HTTPException(status.HTTP_409_CONFLICT, "An arrival time is only for the way there.")
    _set_eta(req, body.minutes)
    session.commit()
    return _job(a, req)


@router.get("/jobs/{job_id}/faults", response_model=list[FaultChoice], responses={404: {}})
def faults(job_id: int, me: Me, session: DbSession, q: Annotated[str, Query(max_length=60)] = ""):
    _, req = _my_job(session, me, job_id)
    return [FaultChoice(**c) for c in outcomes.fault_choices(session, req, q)]


@router.post("/jobs/{job_id}/call", response_model=CallOut, responses={404: {}, 409: {}, 429: {}, 503: {}})
def call_customer(job_id: int, request: Request, me: Me, session: DbSession):
    a, req = _my_job(session, me, job_id)
    if a.status != AssignmentStatus.accepted:
        raise HTTPException(status.HTTP_409_CONFLICT, "This job is finished.")
    return _place_call(request, session, req, "mechanic_to_customer")


def _place_call(request: Request, session: Session, req: ServiceRequest, direction: str) -> CallOut:
    state = request.app.state
    if getattr(state, "call_bridge", None) is None:
        try:
            state.call_bridge = make_bridge(state.settings)
        except CallError as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Calls are not set up yet: call support.") from e
    try:
        call = calls.place(session, state.settings, state.call_bridge, req, direction)
    except calls.CallRefused as e:
        raise HTTPException(e.status, str(e)) from e
    session.commit()
    if call.status == "failed":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The call could not be started. Please try again.")
    return CallOut(status="ringing", message="We are calling your phone now. Pick up to be connected.")


# ---------------------------------------------------------------- alerts on this phone


@router.post("/push-subscriptions", status_code=201, responses={422: {}})
def subscribe(body: PushIn, me: Me, session: DbSession):
    if not allowed_endpoint(body.endpoint):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Not a browser push service address")
    sub = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=body.endpoint)
        session.add(sub)
    sub.p256dh, sub.auth, sub.revoked_at = body.keys.p256dh, body.keys.auth, None
    sub.user_id, sub.anon_key_hash, sub.mechanic_id = None, None, me.id
    session.commit()
    return {"ok": True}


@router.delete("/push-subscriptions", responses={404: {}})
def unsubscribe(body: EndpointIn, me: Me, session: DbSession):
    sub = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None or sub.mechanic_id != me.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    sub.revoked_at = datetime.now(UTC)
    session.commit()
    return {"ok": True}
