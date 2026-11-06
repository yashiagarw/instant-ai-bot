"""/api/admin: staff login and every staff endpoint. Each route declares its permission (@requires / @public); the
router-level `enforce` dependency refuses anything else (deny by default). Every write goes through the audit log.
The permission map: app/admin/permissions.py and docs/permissions.md."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from qrcode.image.svg import SvgPathImage
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.admin import audit
from app.admin import service as staff_service
from app.admin.deps import (
    COOKIE_PATH,
    SETUP_COOKIE,
    SETUP_PATH,
    STAFF_COOKIE,
    CurrentStaff,
    enforce,
    public,
    requires,
)
from app.admin.models import AuditLog, StaffUser
from app.admin.permissions import Perm
from app.admin.security import WeakPassword, provisioning_uri
from app.db import get_session
from app.diagnosis.models import DiagnosisSession
from app.llm.models import GeneratedQuestion, GeneratedStatus
from app.ratelimit import client_ip, make_limiter
from app.requests.models import ServiceRequest
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
    code: str | None = Field(
        default=None, repr=False, description="The 6-digit authenticator code; omit it to be asked (next: code)."
    )


class StaffOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    roles: list[str]
    active: bool
    locked: bool
    two_factor: bool = Field(description="False until the person sets up two-factor at their next sign-in.")
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None


class MeOut(StaffOut):
    permissions: list[str]
    session_expires_at: datetime


class TwoFactorSetupOut(BaseModel):
    """Shown once: scan the QR code (`qr_svg`, or `otpauth_uri` in any QR generator) or type `secret` into the
    authenticator app."""

    otpauth_uri: str
    secret: str
    qr_svg: str


class LoginOut(BaseModel):
    next: Literal["done", "code", "setup"] = Field(
        description="done: signed in (me). code: ask for the authenticator code and send everything again. "
        "setup: show `setup` once, then POST /api/admin/auth/two-factor/confirm with a code."
    )
    me: MeOut | None = None
    setup: TwoFactorSetupOut | None = None


class CodeIn(BaseModel):
    code: str = Field(repr=False)


class StaffCreateIn(BaseModel):
    email: str
    name: str
    roles: list[str]


class StaffCreatedOut(BaseModel):
    staff: StaffOut
    temporary_password: str = Field(
        description="Shown once: give it to the person. They sign in with it, set up two-factor, then choose their own."
    )


class CustomerOut(BaseModel):
    id: uuid.UUID
    name: str | None
    phone_masked: str = Field(description="Always masked; POST .../reveal-phone (customers.contact) for the number.")
    created_at: datetime
    last_login_at: datetime | None
    diagnoses: int
    requests: int


class PhoneOut(BaseModel):
    phone: str


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
        two_factor=u.totp_secret_enc is not None,
        must_change_password=u.must_change_password,
        created_at=u.created_at,
        last_login_at=u.last_login_at,
    )


def _two_factor(request: Request, secret: str, email: str) -> TwoFactorSetupOut:
    uri = provisioning_uri(request.app.state.settings, secret, email)
    svg = qrcode.make(uri, image_factory=SvgPathImage, border=2).to_string(encoding="unicode")
    return TwoFactorSetupOut(otpauth_uri=uri, secret=secret, qr_svg=svg)


def _set_session_cookie(response: Response, settings, token: str) -> None:
    response.set_cookie(
        STAFF_COOKIE,
        token,
        max_age=settings.staff_session_hours * 3600,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _login_failed(session: Session, e: staff_service.LoginFailed) -> HTTPException:
    session.commit()  # the failure count and its audit row stay
    headers = {"Retry-After": str(max(1, round(e.retry_after)))} if e.retry_after else None
    return HTTPException(status.HTTP_401_UNAUTHORIZED, str(e), headers=headers)


# ---------------------------------------------------------------- sign in


def _limit_login(request: Request) -> None:
    state, s = request.app.state, request.app.state.settings
    if getattr(state, "staff_login_limiter", None) is None:
        state.staff_login_limiter = make_limiter(
            s, "staff_login", s.staff_login_ip_limit, s.staff_login_ip_window_seconds
        )
    wait = state.staff_login_limiter.check(client_ip(request, s.trust_forwarded_for))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many sign-in attempts from this network. Please wait and try again.",
            headers={"Retry-After": str(max(1, round(wait)))},
        )


@router.post(
    "/auth/login",
    response_model=LoginOut,
    dependencies=[Depends(_limit_login)],
    responses={401: {"description": "Wrong email, password or code"}, 429: {}},
)
@public
def login(body: LoginIn, request: Request, response: Response, session: DbSession):
    """Staff sign-in: email and password, then the authenticator code (same call with `code`, or again after
    next=code). An account without two-factor gets next=setup: the QR code and key (shown only in this response)
    and a 10-minute setup cookie; finish with POST /auth/two-factor/confirm. Signed in: the im_staff cookie
    (HttpOnly, Secure, SameSite=Strict, path /api/admin; STAFF_SESSION_HOURS, ends after STAFF_IDLE_MINUTES idle)."""
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    ip = client_ip(request, settings.trust_forwarded_for)
    try:
        result = staff_service.login(session, settings, body.email, body.password, body.code, ip)
    except staff_service.LoginFailed as e:
        raise _login_failed(session, e) from e
    session.commit()
    if result.next == "code":
        return LoginOut(next="code")
    if result.next == "setup":
        response.set_cookie(
            SETUP_COOKIE,
            result.token,
            max_age=staff_service.SETUP_MINUTES * 60,
            path=SETUP_PATH,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
        )
        return LoginOut(next="setup", setup=_two_factor(request, result.secret, result.user.email))
    _set_session_cookie(response, settings, result.token)
    return LoginOut(next="done", me=_me(result.user, session, settings, result.token))


@router.post(
    "/auth/two-factor/confirm",
    response_model=MeOut,
    dependencies=[Depends(_limit_login)],
    responses={401: {"description": "Wrong code, or the setup expired"}, 429: {}},
)
@public
def confirm_two_factor(body: CodeIn, request: Request, response: Response, session: DbSession):
    """Finish two-factor setup with a code from the app (needs the setup cookie from /auth/login). Signs in."""
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    ip = client_ip(request, settings.trust_forwarded_for)
    try:
        user, token = staff_service.confirm_two_factor(
            session, settings, request.cookies.get(SETUP_COOKIE), body.code, ip
        )
    except staff_service.LoginFailed as e:
        raise _login_failed(session, e) from e
    session.commit()
    response.delete_cookie(
        SETUP_COOKIE, path=SETUP_PATH, httponly=True, secure=settings.cookie_secure, samesite="strict"
    )
    _set_session_cookie(response, settings, token)
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
    """Invite a staff member: the response holds a temporary password, once. They sign in with it, set up
    two-factor (QR code in the admin app), then must choose their own password."""
    response.headers["Cache-Control"] = "no-store"
    try:
        user, temporary = staff_service.create_staff(
            session, request.app.state.settings, _actor(staff), body.email, body.name, body.roles
        )
    except (staff_service.StaffError, WeakPassword) as e:
        raise _bad(e) from e
    session.commit()
    return StaffCreatedOut(staff=_staff_out(user), temporary_password=temporary)


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


@router.post("/staff/{staff_id}/reset-two-factor", response_model=StaffOut, responses={404: {}})
@requires(Perm.staff_manage)
def reset_two_factor(staff_id: uuid.UUID, staff: CurrentStaff, session: DbSession):
    """Remove someone's two-factor (lost phone): their sessions end and their next sign-in shows a new QR code."""
    user = _staff_or_404(session, staff_id)
    staff_service.reset_two_factor(session, _actor(staff), user)
    session.commit()
    return _staff_out(user)


# ---------------------------------------------------------------- audit log


@router.get("/audit", response_model=list[AuditOut])
@requires(Perm.audit_read)
def audit_log(
    session: DbSession,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor: Annotated[str | None, Query(description="Part of the actor's email (or cli).")] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    """Newest first. All filters are optional and combine."""
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        q = q.where(AuditLog.action == action)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if actor:
        q = q.where(AuditLog.actor_label.ilike(f"%{actor.strip()}%"))
    if since:
        q = q.where(AuditLog.at >= since)
    if until:
        q = q.where(AuditLog.at <= until)
    return [
        AuditOut(**{k: getattr(r, k) for k in AuditOut.model_fields if k != "ip"}, ip=str(r.ip) if r.ip else None)
        for r in session.scalars(q)
    ]


# ---------------------------------------------------------------- customers


@router.get("/customers", response_model=list[CustomerOut])
@requires(Perm.customers_read)
def list_customers(
    session: DbSession,
    q: Annotated[str | None, Query(description="Name, or the last digits of the phone number.")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
):
    """Customer accounts (phone + OTP logins), newest first. Phone numbers are always masked here."""
    diagnoses = (
        select(func.count()).select_from(DiagnosisSession).where(DiagnosisSession.user_id == User.id)
    ).scalar_subquery()
    requests_n = (
        select(func.count()).select_from(ServiceRequest).where(ServiceRequest.user_id == User.id)
    ).scalar_subquery()
    stmt = select(User, diagnoses, requests_n).order_by(User.created_at.desc()).limit(limit)
    term = (q or "").strip()
    if term:
        digits = "".join(ch for ch in term if ch.isdigit())
        if digits and len(digits) == len(term.replace(" ", "")):
            stmt = stmt.where(User.phone.endswith(digits[-10:]))
        else:
            stmt = stmt.where(User.name.ilike(f"%{term}%"))
    return [
        CustomerOut(
            id=u.id,
            name=u.name,
            phone_masked=audit.mask_phone(u.phone),
            created_at=u.created_at,
            last_login_at=u.last_login_at,
            diagnoses=d,
            requests=r,
        )  # fmt: skip
        for u, d, r in session.execute(stmt)
    ]


@router.post("/customers/{customer_id}/reveal-phone", response_model=PhoneOut, responses={404: {}})
@requires(Perm.customers_contact)
def reveal_phone(customer_id: uuid.UUID, staff: CurrentStaff, session: DbSession, response: Response):
    """One customer's full phone number, to call them. Every reveal is written to the audit log."""
    response.headers["Cache-Control"] = "no-store"
    user = session.get(User, customer_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="customer.reveal_phone",
        entity_type="customer",
        entity_id=user.id,
        after={"phone": user.phone},  # masked by the audit helper
        ip=staff.ip,
    )
    session.commit()
    return PhoneOut(phone=user.phone)


# ---------------------------------------------------------------- mechanic requests: app/requests/admin_api.py


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
