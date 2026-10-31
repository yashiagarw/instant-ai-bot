"""/api/admin: staff login and every staff endpoint. Each route declares its permission (@requires / @public); the
router-level `enforce` dependency refuses anything else (deny by default). Every write goes through the audit log.
The permission map: app/admin/permissions.py and docs/permissions.md."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import audit
from app.admin import service as staff_service
from app.admin.deps import COOKIE_PATH, STAFF_COOKIE, CurrentStaff, enforce, public, requires
from app.admin.models import AuditLog, StaffUser
from app.admin.permissions import Perm
from app.admin.security import WeakPassword, provisioning_uri
from app.db import get_session
from app.llm.models import GeneratedQuestion, GeneratedStatus
from app.ratelimit import RateLimiter, client_ip
from app.requests.models import RequestStatus, ServiceRequest
from app.vision.models import ImageLabel

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(enforce)])
DbSession = Annotated[Session, Depends(get_session)]


def _actor(staff) -> staff_service.Actor:
    return staff_service.Actor(staff.user.id, staff.label, staff.ip)


def _bad(e: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


def _staff_or_404(session: Session, staff_id: uuid.UUID) -> StaffUser:
    user = session.get(StaffUser, staff_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff account not found")
    return user


# ---------------------------------------------------------------- schemas


class LoginIn(BaseModel):
    email: str
    password: str = Field(repr=False)
    code: str = Field(description="The 6-digit code from the authenticator app.", repr=False)


class StaffOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    roles: list[str]
    active: bool
    locked: bool
    last_login_at: datetime | None


class MeOut(StaffOut):
    permissions: list[str]
    session_expires_at: datetime


class TwoFactorSetupOut(BaseModel):
    """Shown once: scan `otpauth_uri` as a QR code or type `secret` into the authenticator app."""

    otpauth_uri: str
    secret: str


class StaffCreateIn(BaseModel):
    email: str
    name: str
    password: str = Field(repr=False, description="At least 12 characters; the person changes it after signing in.")
    roles: list[str]


class StaffCreatedOut(BaseModel):
    staff: StaffOut
    two_factor: TwoFactorSetupOut


class RolesIn(BaseModel):
    roles: list[str]


class PasswordIn(BaseModel):
    current_password: str = Field(repr=False)
    code: str = Field(repr=False)
    new_password: str = Field(repr=False)


class AuditOut(BaseModel):
    id: int
    at: datetime
    actor_id: uuid.UUID | None
    actor_label: str
    action: str
    entity_type: str
    entity_id: str | None
    before: dict | None
    after: dict | None
    ip: str | None


class RequestOut(BaseModel):
    id: uuid.UUID
    reference: str
    created_at: datetime
    status: RequestStatus
    name: str
    phone: str = Field(description="Full number only with requests.contact; otherwise the last 4 digits.")
    area: str
    service_type: str
    urgent: bool
    problem_summary: str
    session_id: uuid.UUID | None


class RequestStatusIn(BaseModel):
    status: RequestStatus


class QuestionOut(BaseModel):
    id: int
    created_at: datetime
    category_code: str | None
    text: str
    options: list
    reason: str
    status: GeneratedStatus
    reviewed_by: str | None


class ReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]


class LabelOut(BaseModel):
    id: int
    mode: str
    code: str
    name: str
    meaning: str
    severity: str | None
    fault_keys: list
    reviewed: bool


def _staff_out(u: StaffUser) -> StaffOut:
    return StaffOut(
        id=u.id,
        email=u.email,
        name=u.name,
        roles=u.role_codes,
        active=u.active,
        locked=bool(u.locked_until and u.locked_until > staff_service.now()),
        last_login_at=u.last_login_at,
    )


def _two_factor(request: Request, secret: str, email: str) -> TwoFactorSetupOut:
    return TwoFactorSetupOut(otpauth_uri=provisioning_uri(request.app.state.settings, secret, email), secret=secret)


# ---------------------------------------------------------------- sign in


def _limit_login(request: Request) -> None:
    state, s = request.app.state, request.app.state.settings
    if getattr(state, "staff_login_limiter", None) is None:
        state.staff_login_limiter = RateLimiter(s.staff_login_ip_limit, s.staff_login_ip_window_seconds)
    wait = state.staff_login_limiter.check(client_ip(request, s.trust_forwarded_for))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many sign-in attempts from this network. Please wait and try again.",
            headers={"Retry-After": str(max(1, round(wait)))},
        )


@router.post(
    "/auth/login",
    response_model=MeOut,
    dependencies=[Depends(_limit_login)],
    responses={401: {"description": "Wrong email, password or code"}, 429: {}},
)
@public
def login(body: LoginIn, request: Request, response: Response, session: DbSession):
    """Staff sign-in: email, password and the authenticator code, all at once. Sets the im_staff cookie
    (HttpOnly, Secure, SameSite=Strict, path /api/admin; STAFF_SESSION_HOURS, ends after STAFF_IDLE_MINUTES idle)."""
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    ip = client_ip(request, settings.trust_forwarded_for)
    try:
        user, token = staff_service.login(session, settings, body.email, body.password, body.code, ip)
    except staff_service.LoginFailed as e:
        session.commit()  # the failure count and its audit row stay
        headers = {"Retry-After": str(max(1, round(e.retry_after)))} if e.retry_after else None
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e), headers=headers) from e
    session.commit()
    response.set_cookie(
        STAFF_COOKIE,
        token,
        max_age=settings.staff_session_hours * 3600,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    return _me(user, session, settings, token)


def _me(user: StaffUser, session: Session, settings, token: str | None = None, row=None) -> MeOut:
    from app.accounts.service import token_hash
    from app.admin.models import StaffSession
    from app.admin.permissions import permissions_for

    if row is None:
        row = session.scalar(select(StaffSession).where(StaffSession.token_hash == token_hash(token)))
    return MeOut(
        **_staff_out(user).model_dump(),
        permissions=sorted(p.value for p in permissions_for(user.role_codes)),
        session_expires_at=row.expires_at,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
@requires(Perm.self_service)
def logout(staff: CurrentStaff, session: DbSession, request: Request):
    staff_service.logout(session, _actor(staff), staff.session_row)
    session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        STAFF_COOKIE,
        path=COOKIE_PATH,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="strict",
    )
    return response


@router.get("/auth/me", response_model=MeOut)
@requires(Perm.self_service)
def me(staff: CurrentStaff, session: DbSession, request: Request):
    return _me(staff.user, session, request.app.state.settings, row=staff.session_row)


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT, responses={422: {}})
@requires(Perm.self_service)
def change_password(body: PasswordIn, staff: CurrentStaff, session: DbSession, request: Request):
    """Change your own password (current password + a fresh authenticator code). Your other sessions end."""
    try:
        staff_service.change_password(
            session, request.app.state.settings, _actor(staff), staff.user, body.current_password, body.code,
            body.new_password,
        )  # fmt: skip
    except (staff_service.StaffError, WeakPassword) as e:
        raise _bad(e) from e
    staff_service.revoke_sessions(session, staff.user)
    staff.session_row.revoked_at = None  # keep this one
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- staff accounts


@router.get("/staff", response_model=list[StaffOut])
@requires(Perm.staff_read)
def list_staff(session: DbSession):
    return [_staff_out(u) for u in session.scalars(select(StaffUser).order_by(StaffUser.email))]


@router.post("/staff", response_model=StaffCreatedOut, status_code=status.HTTP_201_CREATED, responses={422: {}})
@requires(Perm.staff_manage)
def create_staff(body: StaffCreateIn, staff: CurrentStaff, session: DbSession, request: Request, response: Response):
    """A staff account. The two-factor setup is in this response only: give it to the person once."""
    response.headers["Cache-Control"] = "no-store"
    try:
        user, secret = staff_service.create_staff(
            session, request.app.state.settings, _actor(staff), body.email, body.name, body.password, body.roles
        )
    except (staff_service.StaffError, WeakPassword) as e:
        raise _bad(e) from e
    session.commit()
    return StaffCreatedOut(staff=_staff_out(user), two_factor=_two_factor(request, secret, user.email))


@router.put("/staff/{staff_id}/roles", response_model=StaffOut, responses={404: {}, 422: {}})
@requires(Perm.staff_manage)
def set_roles(staff_id: uuid.UUID, body: RolesIn, staff: CurrentStaff, session: DbSession):
    user = _staff_or_404(session, staff_id)
    try:
        staff_service.set_roles(session, _actor(staff), user, body.roles)
    except staff_service.StaffError as e:
        raise _bad(e) from e
    session.commit()
    return _staff_out(user)


@router.post("/staff/{staff_id}/deactivate", response_model=StaffOut, responses={404: {}, 422: {}})
@requires(Perm.staff_manage)
def deactivate(staff_id: uuid.UUID, staff: CurrentStaff, session: DbSession):
    user = _staff_or_404(session, staff_id)
    try:
        staff_service.set_active(session, _actor(staff), user, False)
    except staff_service.StaffError as e:
        raise _bad(e) from e
    session.commit()
    return _staff_out(user)


@router.post("/staff/{staff_id}/activate", response_model=StaffOut, responses={404: {}})
@requires(Perm.staff_manage)
def activate(staff_id: uuid.UUID, staff: CurrentStaff, session: DbSession):
    user = _staff_or_404(session, staff_id)
    staff_service.set_active(session, _actor(staff), user, True)
    session.commit()
    return _staff_out(user)


@router.post("/staff/{staff_id}/unlock", response_model=StaffOut, responses={404: {}})
@requires(Perm.staff_manage)
def unlock(staff_id: uuid.UUID, staff: CurrentStaff, session: DbSession):
    user = _staff_or_404(session, staff_id)
    staff_service.unlock(session, _actor(staff), user)
    session.commit()
    return _staff_out(user)


@router.post("/staff/{staff_id}/reset-two-factor", response_model=TwoFactorSetupOut, responses={404: {}})
@requires(Perm.staff_manage)
def reset_two_factor(
    staff_id: uuid.UUID, staff: CurrentStaff, session: DbSession, request: Request, response: Response
):
    """A new authenticator secret for someone who lost their phone (shown once). Their sessions end."""
    response.headers["Cache-Control"] = "no-store"
    user = _staff_or_404(session, staff_id)
    secret = staff_service.reset_two_factor(session, request.app.state.settings, _actor(staff), user)
    session.commit()
    return _two_factor(request, secret, user.email)


# ---------------------------------------------------------------- audit log


@router.get("/audit", response_model=list[AuditOut])
@requires(Perm.audit_read)
def audit_log(
    session: DbSession,
    action: str | None = None,
    entity_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        q = q.where(AuditLog.action == action)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    return [
        AuditOut(**{k: getattr(r, k) for k in AuditOut.model_fields if k != "ip"}, ip=str(r.ip) if r.ip else None)
        for r in session.scalars(q)
    ]


# ---------------------------------------------------------------- mechanic requests


def _request_out(r: ServiceRequest, contact: bool) -> RequestOut:
    return RequestOut(
        id=r.id,
        reference=r.reference,
        created_at=r.created_at,
        status=r.status,
        name=r.name,
        phone=r.phone if contact else audit.mask_phone(r.phone),
        area=r.area_text or r.pincode,
        service_type=str(r.service_type),
        urgent=r.urgent,
        problem_summary=r.problem_summary,
        session_id=r.session_id,
    )


def _request_or_404(session: Session, request_id: uuid.UUID) -> ServiceRequest:
    row = session.get(ServiceRequest, request_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return row


@router.get("/requests", response_model=list[RequestOut])
@requires(Perm.requests_read)
def list_requests(
    staff: CurrentStaff,
    session: DbSession,
    status_filter: Annotated[RequestStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    q = select(ServiceRequest).order_by(ServiceRequest.created_at.desc()).limit(limit)
    if status_filter:
        q = q.where(ServiceRequest.status == status_filter)
    contact = Perm.requests_contact in staff.perms
    return [_request_out(r, contact) for r in session.scalars(q)]


@router.get("/requests/{request_id}", response_model=RequestOut, responses={404: {}})
@requires(Perm.requests_read)
def get_request(request_id: uuid.UUID, staff: CurrentStaff, session: DbSession):
    return _request_out(_request_or_404(session, request_id), Perm.requests_contact in staff.perms)


@router.patch("/requests/{request_id}", response_model=RequestOut, responses={404: {}})
@requires(Perm.requests_update)
def update_request(request_id: uuid.UUID, body: RequestStatusIn, staff: CurrentStaff, session: DbSession):
    row = _request_or_404(session, request_id)
    before = {"status": str(row.status)}
    row.status = body.status
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="request.set_status",
        entity_type="service_request",
        entity_id=row.id,
        before=before,
        after={"status": str(row.status)},
        ip=staff.ip,
    )
    session.commit()
    return _request_out(row, Perm.requests_contact in staff.perms)


# ---------------------------------------------------------------- content


@router.get("/content/generated-questions", response_model=list[QuestionOut])
@requires(Perm.content_read)
def generated_questions(
    session: DbSession, status_filter: Annotated[GeneratedStatus | None, Query(alias="status")] = None
):
    q = select(GeneratedQuestion).order_by(GeneratedQuestion.id.desc()).limit(200)
    if status_filter:
        q = q.where(GeneratedQuestion.status == status_filter)
    return [
        QuestionOut(
            id=g.id,
            created_at=g.created_at,
            category_code=g.category_code,
            text=g.text,
            options=g.options,
            reason=g.reason,
            status=g.status,
            reviewed_by=g.reviewed_by,
        )  # fmt: skip
        for g in session.scalars(q)
    ]


@router.post("/content/generated-questions/{question_id}/review", response_model=QuestionOut, responses={404: {}})
@requires(Perm.content_review)
def review_question(question_id: int, body: ReviewIn, staff: CurrentStaff, session: DbSession):
    """Approve or reject a question the LLM proposed (approved ones are added to the question files by hand)."""
    g = session.get(GeneratedQuestion, question_id)
    if g is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    before = {"status": str(g.status), "reviewed_by": g.reviewed_by}
    g.status, g.reviewed_by, g.reviewed_at = GeneratedStatus(body.decision), staff.label, staff_service.now()
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="content.review_question",
        entity_type="generated_question",
        entity_id=g.id,
        before=before,
        after={"status": str(g.status), "reviewed_by": g.reviewed_by},
        ip=staff.ip,
    )
    session.commit()
    return QuestionOut(
        id=g.id, created_at=g.created_at, category_code=g.category_code, text=g.text, options=g.options,
        reason=g.reason, status=g.status, reviewed_by=g.reviewed_by,
    )  # fmt: skip


@router.get("/content/image-labels", response_model=list[LabelOut])
@requires(Perm.content_read)
def image_labels(session: DbSession):
    """The photo label list (edited in data/review/image_labels.yaml and seeded; read-only here)."""
    return [
        LabelOut(
            id=lb.id,
            mode=str(lb.mode),
            code=lb.code,
            name=lb.name,
            meaning=lb.meaning,
            severity=str(lb.severity) if lb.severity else None,
            fault_keys=lb.fault_keys,
            reviewed=lb.reviewed,
        )  # fmt: skip
        for lb in session.scalars(select(ImageLabel).order_by(ImageLabel.mode, ImageLabel.id))
    ]
