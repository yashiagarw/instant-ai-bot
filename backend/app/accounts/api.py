"""Login by phone + OTP, the customer's own data (/me) and account deletion. Every /me route only ever reads rows
whose user_id is the logged-in user: another customer's request answers 404, as if it did not exist."""

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts import schemas as S
from app.accounts import service
from app.accounts.models import User, UserVehicle
from app.accounts.service import ANON_COOKIE, SESSION_COOKIE
from app.config import Settings
from app.db import get_session
from app.diagnosis.models import DiagnosisSession, SessionResult
from app.knowledge.models import ProblemGroup
from app.notify.sms import SmsError, SmsSender, make_sms, mask_phone
from app.ratelimit import RateLimiter, client_ip
from app.requests import workflow
from app.requests.models import (
    AssignmentStatus,
    EventKind,
    RequestAssignment,
    RequestEvent,
    RequestStatus,
    ServiceRequest,
)

log = logging.getLogger(__name__)
auth_router = APIRouter(prefix="/auth", tags=["accounts"])
me_router = APIRouter(prefix="/me", tags=["accounts"])
requests_router = APIRouter(prefix="/requests", tags=["accounts"])
DbSession = Annotated[Session, Depends(get_session)]

# Plain words for the customer (app/requests/workflow.py).
STATUS_LABELS = {k.value: v for k, v in workflow.CUSTOMER_LABELS.items()}
TIMELINE_LABELS = {  # the steps of the usual path, as the timeline names them
    RequestStatus.submitted: "Request received",
    RequestStatus.triaged: "Our team is on it",
    RequestStatus.accepted: "Mechanic assigned",
    RequestStatus.en_route: "Mechanic on the way",
    RequestStatus.arrived: "Mechanic has arrived",
    RequestStatus.in_progress: "Repair in progress",
    RequestStatus.completed: "Done",
}
# Where a status sits on the usual path (offered: still with our team; escalated: wherever it was).
STEP_OF = {RequestStatus.offered: RequestStatus.triaged}


# ---------------------------------------------------------------- cookies and dependencies


def _cookie(response: Response, settings: Settings, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name, value, max_age=max_age, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/"
    )


def set_login_cookie(response: Response, settings: Settings, token: str) -> None:
    _cookie(response, settings, SESSION_COOKIE, token, settings.auth_session_days * 86400)


def clear_login_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax")


def optional_user(request: Request, session: DbSession) -> User | None:
    return service.current_user(session, request.cookies.get(SESSION_COOKIE))


def required_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in")
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]
RequiredUser = Annotated[User, Depends(required_user)]


def claim_for_owner(
    request: Request, response: Response, session: Session, row: DiagnosisSession | ServiceRequest
) -> None:
    """Called when a diagnosis session or a service request is created: the logged-in user owns it; otherwise
    this browser's anonymous cookie does (made here if needed), so logging in later can attach it."""
    user = service.current_user(session, request.cookies.get(SESSION_COOKIE))
    anon = request.cookies.get(ANON_COOKIE) or ""
    if user is None and not anon:
        anon = service.new_anon_token()
    service.claim(session, row, user, anon)
    if user is None:
        _cookie(response, request.app.state.settings, ANON_COOKIE, anon, 365 * 86400)


def get_sms(request: Request) -> SmsSender:
    state = request.app.state
    if getattr(state, "sms_sender", None) is None:
        state.sms_sender = make_sms(state.settings)
    return state.sms_sender


def _limit(request: Request, name: str, limit: int, window: int) -> None:
    state = request.app.state
    limiter: RateLimiter | None = getattr(state, name, None)
    if limiter is None:
        limiter = RateLimiter(limit, window)
        setattr(state, name, limiter)
    wait = limiter.check(client_ip(request, state.settings.trust_forwarded_for))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many tries from this network. Please wait and try again.",
            headers={"Retry-After": str(max(1, round(wait)))},
        )


def limit_otp_request(request: Request) -> None:
    s = request.app.state.settings
    _limit(request, "otp_ip_limiter", s.otp_ip_limit, s.otp_ip_window_seconds)


def limit_otp_verify(request: Request) -> None:
    s = request.app.state.settings
    _limit(request, "otp_verify_limiter", s.otp_verify_ip_limit, s.otp_verify_ip_window_seconds)


def _user_out(user: User) -> S.UserOut:
    return S.UserOut(id=user.id, phone_masked=mask_phone(user.phone), name=user.name, created_at=user.created_at)


def _phone(raw: str) -> str:
    try:
        return service.normalize_phone(raw)
    except service.AuthError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e


# ---------------------------------------------------------------- login


@auth_router.get("/config", response_model=S.AuthConfigOut, summary="Consent wording for the login form")
def auth_config(request: Request):
    return S.AuthConfigOut(
        consent_version=service.CONSENT_VERSION,
        consent_text=service.CONSENT_TEXT,
        expires_in=request.app.state.settings.otp_ttl_seconds,
    )


@auth_router.post(
    "/otp/request",
    response_model=S.OtpRequestOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit_otp_request)],
    responses={422: {"description": "Not an Indian mobile number"}, 429: {"description": "Too many codes"}},
)
def otp_request(
    body: S.OtpRequestIn, request: Request, session: DbSession, sms: Annotated[SmsSender, Depends(get_sms)]
):
    """Send a 6-digit login code by SMS. The answer is the same whether or not the number has an account."""
    settings = request.app.state.settings
    phone = _phone(body.phone)
    try:
        code, _ = service.request_otp(session, settings, phone)
    except service.TooMany as e:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, str(e), headers={"Retry-After": str(round(e.retry_after))}
        ) from e
    session.commit()
    try:
        sms.send_otp(phone, code)
    except SmsError as e:
        log.warning("Login code to %s not sent: %s", mask_phone(phone), e)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "We couldn't send the SMS. Please try again.") from e
    return S.OtpRequestOut(phone_masked=mask_phone(phone), expires_in=settings.otp_ttl_seconds)


@auth_router.post(
    "/otp/verify",
    response_model=S.LoginOut,
    dependencies=[Depends(limit_otp_verify)],
    responses={400: {"description": "Wrong, expired or used-up code"}, 429: {"description": "Too many tries"}},
)
def otp_verify(body: S.OtpVerifyIn, request: Request, response: Response, session: DbSession):
    """Check the code; on success set the login cookie and attach this browser's anonymous diagnoses and requests."""
    settings = request.app.state.settings
    phone = _phone(body.phone)
    if not body.consent or body.consent_text_version != service.CONSENT_VERSION:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Please tick the box to agree before logging in")
    try:
        service.verify_otp(session, settings, phone, body.code.strip())
    except service.AuthError as e:
        session.commit()  # the attempt counts even when the code is wrong
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    user, token, attached = service.login(session, settings, phone, request.cookies.get(ANON_COOKIE))
    session.commit()
    set_login_cookie(response, settings, token)
    response.delete_cookie(ANON_COOKIE, path="/")
    return S.LoginOut(user=_user_out(user), attached=attached)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, session: DbSession, im_session: Annotated[str | None, Cookie()] = None):
    service.logout(session, im_session)
    session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_login_cookie(response, request.app.state.settings)
    return response


# ---------------------------------------------------------------- the customer's own data


@me_router.get("", response_model=S.MeOut, responses={401: {"description": "Not logged in"}})
def me(user: RequiredUser, session: DbSession):
    def count(model, col) -> int:
        return session.scalar(select(func.count()).select_from(model).where(col == user.id)) or 0

    return S.MeOut(
        user=_user_out(user),
        vehicles=count(UserVehicle, UserVehicle.user_id),
        sessions=count(DiagnosisSession, DiagnosisSession.user_id),
        requests=count(ServiceRequest, ServiceRequest.user_id),
    )


@me_router.get("/vehicles", response_model=list[S.VehicleOut])
def my_vehicles(user: RequiredUser, session: DbSession):
    return [
        S.VehicleOut(id=v.id, label=v.label, variant_id=v.variant_id, created_at=v.created_at)
        for v in session.scalars(
            select(UserVehicle).where(UserVehicle.user_id == user.id).order_by(UserVehicle.created_at.desc())
        )
    ]


@me_router.delete("/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_vehicle(vehicle_id: int, user: RequiredUser, session: DbSession):
    v = session.get(UserVehicle, vehicle_id)
    if v is None or v.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Car not found")
    session.delete(v)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _vehicle_label(snap: dict) -> str:
    parts = [snap.get("make"), snap.get("model")]
    label = " ".join(str(p) for p in parts if p)
    if snap.get("variant"):
        label += f" · {snap['variant']}"
    elif snap.get("year"):
        label += f" {snap['year']}"
    return label or "Car not given"


@me_router.get("/sessions", response_model=list[S.SessionSummaryOut])
def my_sessions(user: RequiredUser, session: DbSession):
    rows = session.execute(
        select(DiagnosisSession, ProblemGroup.label_en)
        .outerjoin(ProblemGroup, ProblemGroup.code == DiagnosisSession.problem_group_code)
        .where(DiagnosisSession.user_id == user.id)
        .order_by(DiagnosisSession.created_at.desc())
    ).all()
    tops = dict(
        session.execute(
            select(SessionResult.session_id, SessionResult.fault_key).where(
                SessionResult.session_id.in_([ds.id for ds, _ in rows]), SessionResult.rank == 1
            )
        ).all()
    )
    names = _fault_names(session, list(tops.values()))
    return [
        S.SessionSummaryOut(
            session_id=ds.id,
            created_at=ds.created_at,
            status=str(ds.status),
            vehicle=_vehicle_label(ds.vehicle_snapshot or {}),
            topic=topic,
            top_cause=names.get(tops.get(ds.id, ""), None),
        )
        for ds, topic in rows
    ]


def _fault_names(session: Session, keys: list[str]) -> dict[str, str]:
    from app.knowledge.models import Fault

    if not keys:
        return {}
    return dict(session.execute(select(Fault.fault_key, Fault.name).where(Fault.fault_key.in_(keys))).all())


def _request_summary(r: ServiceRequest) -> dict:
    return {
        "id": r.id,
        "reference": r.reference,
        "created_at": r.created_at,
        "status": str(r.status),
        "status_label": STATUS_LABELS.get(str(r.status), str(r.status)),
        "urgent": r.urgent,
        "vehicle": _vehicle_label(r.vehicle_snapshot or {}),
        "problem_summary": r.problem_summary,
    }


@me_router.get("/requests", response_model=list[S.RequestSummaryOut])
def my_requests(user: RequiredUser, session: DbSession):
    return [
        S.RequestSummaryOut(**_request_summary(r))
        for r in session.scalars(
            select(ServiceRequest).where(ServiceRequest.user_id == user.id).order_by(ServiceRequest.created_at.desc())
        )
    ]


def _status_events(session: Session, r: ServiceRequest) -> list[RequestEvent]:
    return list(
        session.scalars(
            select(RequestEvent)
            .where(RequestEvent.request_id == r.id, RequestEvent.kind == EventKind.status)
            .order_by(RequestEvent.at, RequestEvent.id)
        )
    )


def timeline(r: ServiceRequest, events: list[RequestEvent] | None = None) -> list[S.TimelineStep]:
    """The usual path with what's done, the current step (in plain words) and what comes next. Times come from the
    status events (the last time each step was reached)."""
    events = events or []
    reached_at: dict[str, datetime] = {"submitted": r.created_at}
    for e in events:
        if e.to_status:
            reached_at[STEP_OF.get(RequestStatus(e.to_status), RequestStatus(e.to_status)).value] = e.at
    path = workflow.HAPPY_PATH
    current = RequestStatus(r.status)
    if current in (RequestStatus.cancelled, RequestStatus.escalated):
        # The furthest step reached before it was cancelled / escalated.
        last = next(
            (RequestStatus(e.from_status) for e in reversed(events) if e.to_status == current and e.from_status), None
        )
        step = STEP_OF.get(last, last) if last else RequestStatus.submitted
        idx = path.index(step) if step in path else 0
        steps = [
            S.TimelineStep(key=k.value, label=TIMELINE_LABELS[k], state="done", at=reached_at.get(k.value))
            for k in path[: idx + 1]
        ]
        if current == RequestStatus.cancelled:
            steps.append(S.TimelineStep(key="cancelled", label="Cancelled", state="cancelled", at=r.status_changed_at))
            return steps
        steps.append(
            S.TimelineStep(key="escalated", label=STATUS_LABELS["escalated"], state="current", at=r.status_changed_at)
        )
        return steps + [
            S.TimelineStep(key=k.value, label=TIMELINE_LABELS[k], state="upcoming") for k in path[idx + 1 :]
        ]
    step = STEP_OF.get(current, current)
    idx = path.index(step)
    out = []
    for i, k in enumerate(path):
        if i < idx or (i == idx and k == RequestStatus.completed):
            state = "done"
        else:
            state = "current" if i == idx else "upcoming"
        # The current step speaks of where things are now ("Finding a mechanic for you").
        label = STATUS_LABELS[current.value] if state == "current" else TIMELINE_LABELS[k]
        out.append(
            S.TimelineStep(key=k.value, label=label, state=state, at=reached_at.get(k.value) if i <= idx else None)
        )
    return out


def _mechanic_first_name(session: Session, r: ServiceRequest) -> str | None:
    """The first name of the mechanic who took the job (never their phone number or documents)."""
    if r.status in (RequestStatus.submitted, RequestStatus.triaged, RequestStatus.offered, RequestStatus.cancelled):
        return None
    from app.mechanics.models import Mechanic

    name = session.scalar(
        select(Mechanic.name)
        .join(RequestAssignment, RequestAssignment.mechanic_id == Mechanic.id)
        .where(
            RequestAssignment.request_id == r.id,
            RequestAssignment.status.in_((AssignmentStatus.accepted, AssignmentStatus.completed)),
        )
        .order_by(RequestAssignment.id.desc())
        .limit(1)
    )
    return name.split()[0] if name and name.split() else None


@requests_router.get(
    "/{request_id}", response_model=S.RequestDetailOut, responses={401: {"description": "Not logged in"}, 404: {}}
)
def my_request(request_id: uuid.UUID, user: RequiredUser, session: DbSession):
    """One of the customer's own requests with its status timeline. Anyone else's answers 404."""
    r = session.get(ServiceRequest, request_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    events = _status_events(session, r)
    return S.RequestDetailOut(
        **_request_summary(r),
        service_type=str(r.service_type),
        area=r.area_text,
        preferred_time=r.preferred_time,
        session_id=r.session_id,
        timeline=timeline(r, events),
        mechanic_first_name=_mechanic_first_name(session, r),
        updates=[
            S.StatusUpdate(at=e.at, status=e.to_status, label=STATUS_LABELS.get(e.to_status, e.to_status))
            for e in reversed(events)
            if e.to_status
        ],
    )


@me_router.delete("", response_model=S.DeleteAccountOut, responses={401: {"description": "Not logged in"}, 422: {}})
def delete_me(body: S.DeleteAccountIn, request: Request, response: Response, user: RequiredUser, session: DbSession):
    """Delete the account and all personal data linked to it: phone, saved cars, diagnosis history, requests (with
    contact details and consent records) and uploads. Cannot be undone."""
    from app.uploads.api import get_storage
    from app.uploads.storage import StorageError

    try:
        report = service.delete_account(session, request.app.state.settings, user, get_storage(request))
    except StorageError as e:
        session.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "We couldn't delete your photos just now. Nothing was deleted; please try again.",
        ) from e
    session.commit()
    clear_login_cookie(response, request.app.state.settings)
    return S.DeleteAccountOut(
        sessions=report.sessions, requests=report.requests, vehicles=report.vehicles, photos=report.photos
    )
