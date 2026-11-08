"""Staff accounts: login (password + TOTP, lockout), sessions, and account management. Every change is written to
the audit log by the caller's request through app.admin.audit.record (here, so no path forgets it)."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.accounts.service import token_hash
from app.admin import audit, security
from app.admin.models import STAFF_ROLES, RoleCode, StaffSession, StaffSetupTicket, StaffUser, UserRole
from app.config import Settings

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOGIN_FAILED = "Email, password or code is wrong."


class StaffError(ValueError):
    """Shown to the caller as it is."""


class LoginFailed(StaffError):
    def __init__(self, message: str = LOGIN_FAILED, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class Actor:
    id: uuid.UUID | None
    label: str
    ip: str | None = None


CLI = Actor(None, "cli")


def now() -> datetime:
    return datetime.now(UTC)


def normalize_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise StaffError("Enter a valid email address")
    return email


def snapshot(u: StaffUser) -> dict:
    """What the audit log keeps about a staff account (never the password hash or TOTP secret)."""
    return {
        "id": str(u.id),
        "email": u.email,
        "name": u.name,
        "active": u.active,
        "roles": u.role_codes,
        "failed_logins": u.failed_logins,
        "locked_until": u.locked_until.isoformat() if u.locked_until else None,
        "two_factor": u.totp_secret_enc is not None,
        "must_change_password": u.must_change_password,
    }


def _write(session: Session, actor: Actor, action: str, user: StaffUser | None, before=None, after=None, **kw):
    audit.record(
        session,
        actor_id=actor.id,
        actor_label=actor.label,
        action=action,
        entity_type="staff_user",
        entity_id=user.id if user else None,
        before=before,
        after=after,
        ip=actor.ip,
        **kw,
    )


def _roles(roles: list[str]) -> list[str]:
    allowed = {r.value for r in STAFF_ROLES}
    roles = sorted(set(roles))
    if not roles:
        raise StaffError("Give at least one role")
    bad = [r for r in roles if r not in allowed]
    if bad:
        raise StaffError(f"Not a staff role: {', '.join(bad)}")
    return roles


def find(session: Session, email: str) -> StaffUser | None:
    return session.scalar(select(StaffUser).where(StaffUser.email == email.strip().lower()))


def active_super_admins(session: Session) -> int:
    return session.scalar(
        select(func.count())
        .select_from(UserRole)
        .join(StaffUser, StaffUser.id == UserRole.staff_user_id)
        .where(UserRole.role_code == RoleCode.super_admin, StaffUser.active.is_(True))
    )


# ---------------------------------------------------------------- accounts


def create_staff(
    session: Session,
    settings: Settings,
    actor: Actor,
    email: str,
    name: str,
    roles: list[str],
    *,
    password: str | None = None,
    secret: str | None = None,
) -> tuple[StaffUser, str | None]:
    """A new staff account. Without `password` (an invitation) a temporary password is made, returned once, and
    must be changed after the first sign-in. Without `secret` (normal) two-factor is set up at the first sign-in in
    the admin app; the CLI passes one it has already shown and confirmed. Returns (account, temporary password)."""
    email = normalize_email(email)
    if not name.strip():
        raise StaffError("Enter a name")
    roles = _roles(roles)
    temporary = password is None
    password = security.temporary_password() if temporary else password
    security.check_password_policy(password, email)
    if find(session, email):
        raise StaffError("A staff account with this email already exists")
    user = StaffUser(
        email=email,
        name=name.strip(),
        password_hash=security.hash_password(password),
        totp_secret_enc=security.encrypt_secret(settings, secret) if secret else None,
        password_changed_at=now(),
        must_change_password=temporary,
    )
    user.roles = [UserRole(role_code=r, granted_by=actor.id) for r in roles]
    session.add(user)
    session.flush()
    _write(session, actor, "staff.create", user, after=snapshot(user))
    return user, password if temporary else None


def set_roles(session: Session, actor: Actor, user: StaffUser, roles: list[str]) -> StaffUser:
    roles = _roles(roles)
    before = snapshot(user)
    losing_super = RoleCode.super_admin in user.role_codes and RoleCode.super_admin not in roles
    if losing_super and user.active and active_super_admins(session) <= 1:
        raise StaffError("There must always be one active super admin")
    if losing_super and user.id == actor.id:
        raise StaffError("You can't remove your own super admin role")
    keep = {r.role_code: r for r in user.roles}
    user.roles = [keep.get(r) or UserRole(role_code=r, granted_by=actor.id) for r in roles]
    session.flush()
    revoke_sessions(session, user)  # new permissions on the next login
    _write(session, actor, "staff.set_roles", user, before, snapshot(user))
    return user


def set_active(session: Session, actor: Actor, user: StaffUser, active: bool) -> StaffUser:
    if not active:
        if user.id == actor.id:
            raise StaffError("You can't deactivate yourself")
        if RoleCode.super_admin in user.role_codes and user.active and active_super_admins(session) <= 1:
            raise StaffError("There must always be one active super admin")
    before = snapshot(user)
    user.active = active
    if not active:
        revoke_sessions(session, user)
    session.flush()
    _write(session, actor, "staff.activate" if active else "staff.deactivate", user, before, snapshot(user))
    return user


def unlock(session: Session, actor: Actor, user: StaffUser) -> StaffUser:
    before = snapshot(user)
    user.failed_logins, user.locked_until = 0, None
    session.flush()
    _write(session, actor, "staff.unlock", user, before, snapshot(user))
    return user


def reset_two_factor(session: Session, actor: Actor, user: StaffUser) -> None:
    """Remove two-factor (lost phone): the next sign-in shows the setup step with a new QR code. Old codes stop
    working and the account's sessions end."""
    before = snapshot(user)
    user.totp_secret_enc, user.totp_last_step = None, None
    revoke_sessions(session, user)
    session.execute(delete(StaffSetupTicket).where(StaffSetupTicket.staff_user_id == user.id))
    session.flush()
    _write(session, actor, "staff.reset_two_factor", user, before, snapshot(user))


def reset_password(session: Session, actor: Actor, user: StaffUser, new: str) -> None:
    """Set a new password without the old one (the CLI, for a forgotten password). Clears the lockout and wrong
    tries, ends the account's sessions; two-factor stays as it is. The caller checks the password policy."""
    before = snapshot(user)
    user.password_hash = security.hash_password(new)
    user.password_changed_at, user.must_change_password = now(), False
    user.failed_logins, user.locked_until = 0, None
    revoke_sessions(session, user)
    session.flush()
    _write(session, actor, "staff.reset_password", user, before, snapshot(user))


def change_password(
    session: Session, settings: Settings, actor: Actor, user: StaffUser, current: str, code: str, new: str
) -> None:
    """Own password: needs the current password and a fresh TOTP code. Other sessions of the account end."""
    secret = security.decrypt_secret(settings, user.totp_secret_enc) if user.totp_secret_enc else None
    step = security.totp_step(secret, code, user.totp_last_step) if secret else None
    if not security.verify_password(user.password_hash, current) or step is None:
        raise StaffError("Current password or code is wrong")
    security.check_password_policy(new, user.email)
    if security.verify_password(user.password_hash, new):
        raise StaffError("Choose a password you haven't used here")
    before = snapshot(user)
    user.password_hash = security.hash_password(new)
    user.password_changed_at, user.totp_last_step, user.must_change_password = now(), step, False
    session.flush()
    _write(session, actor, "staff.change_password", user, before, snapshot(user))


# ---------------------------------------------------------------- login and sessions

SETUP_MINUTES = 10  # the two-factor setup step must be finished within this
SETUP_TRIES = 5  # wrong codes during setup before it has to start again
SETUP_FAILED = "That code doesn't match. Make sure the phone's time is set automatically and type the newest code."


@dataclass
class LoginResult:
    """next: "done" (signed in: `token` is the session cookie), "code" (password right, ask for the authenticator
    code) or "setup" (password right, no two-factor yet: `token` is the setup ticket, `secret` to show once)."""

    next: str
    user: StaffUser
    token: str | None = None
    secret: str | None = None


def _fail(session: Session, settings: Settings, who: Actor, user: StaffUser, at: datetime, reason: str):
    before = snapshot(user)
    user.failed_logins += 1
    locked = user.failed_logins >= settings.staff_max_failed_logins
    if locked:
        user.locked_until, user.failed_logins = at + timedelta(minutes=settings.staff_lockout_minutes), 0
    session.flush()
    after = {**snapshot(user), "reason": reason}
    _write(session, who, "staff.locked" if locked else "staff.login_failed", user, before, after)
    if locked:
        raise LoginFailed(
            f"Too many failed attempts. Try again in {settings.staff_lockout_minutes} minutes.",
            settings.staff_lockout_minutes * 60,
        )


def _start_session(session: Session, settings: Settings, who: Actor, user: StaffUser, step: int, at: datetime):
    before = snapshot(user)
    user.failed_logins, user.locked_until, user.totp_last_step, user.last_login_at = 0, None, step, at
    token = secrets.token_urlsafe(32)
    session.add(
        StaffSession(
            staff_user_id=user.id,
            token_hash=token_hash(token),
            expires_at=at + timedelta(hours=settings.staff_session_hours),
            last_seen_at=at,
        )
    )
    session.flush()
    _write(session, who, "staff.login", user, before, snapshot(user))
    return token


def login(
    session: Session, settings: Settings, email: str, password: str, code: str | None, ip: str | None
) -> LoginResult:
    """Email + password, then the authenticator code (sent together, or the code in a second call). Any wrong part
    gets the same LoginFailed message; after STAFF_MAX_FAILED_LOGINS failures in a row the account is locked for
    STAFF_LOCKOUT_MINUTES. An account without two-factor gets a setup ticket instead of a session. The caller
    commits (failures are counted and audited even though the login is refused)."""
    at = now()
    clean = (email or "").strip().lower()
    user = find(session, clean) if clean else None
    who = Actor(user.id if user else None, clean or "anonymous", ip)
    if user is None or not user.active:
        security.verify_password(security.DUMMY_HASH, password or "")  # same time as a real check
        _write(session, who, "staff.login_failed", user, after={"email": clean, "reason": "unknown or inactive"})
        raise LoginFailed()
    if user.locked_until and user.locked_until > at:
        _write(session, who, "staff.login_locked", user, after={"locked_until": user.locked_until.isoformat()})
        wait = (user.locked_until - at).total_seconds()
        raise LoginFailed(f"Too many failed attempts. Try again in {max(1, round(wait / 60))} minutes.", wait)

    if not security.verify_password(user.password_hash, password or ""):
        _fail(session, settings, who, user, at, "password")
        raise LoginFailed()
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)

    if user.totp_secret_enc is None:  # no two-factor yet: set it up before any session
        session.execute(delete(StaffSetupTicket).where(StaffSetupTicket.staff_user_id == user.id))
        secret, ticket = security.new_totp_secret(), secrets.token_urlsafe(32)
        session.add(
            StaffSetupTicket(
                staff_user_id=user.id,
                token_hash=token_hash(ticket),
                secret_enc=security.encrypt_secret(settings, secret),
                expires_at=at + timedelta(minutes=SETUP_MINUTES),
            )
        )
        session.flush()
        _write(session, who, "staff.two_factor_setup_started", user, after={"email": user.email})
        return LoginResult("setup", user, ticket, secret)

    if not (code or "").strip():
        return LoginResult("code", user)
    secret = security.decrypt_secret(settings, user.totp_secret_enc)
    step = security.totp_step(secret, code, user.totp_last_step) if secret else None
    if step is None:
        _fail(session, settings, who, user, at, "code")
        raise LoginFailed()
    return LoginResult("done", user, _start_session(session, settings, who, user, step, at))


def confirm_two_factor(
    session: Session, settings: Settings, ticket: str | None, code: str, ip: str | None
) -> tuple[StaffUser, str]:
    """Finish the setup step: the code must come from the secret shown with this ticket. Saves the secret and
    signs in. Raises LoginFailed (expired ticket, wrong code; SETUP_TRIES wrong codes end the ticket)."""
    at = now()
    row = session.scalar(select(StaffSetupTicket).where(StaffSetupTicket.token_hash == token_hash(ticket or "")))
    if row is None or row.expires_at <= at:
        raise LoginFailed("This setup has expired. Please sign in again.")
    user = session.get(StaffUser, row.staff_user_id)
    who = Actor(user.id, user.email, ip)
    if not user.active or (user.locked_until and user.locked_until > at) or user.totp_secret_enc is not None:
        session.delete(row)
        raise LoginFailed("This setup has expired. Please sign in again.")
    secret = security.decrypt_secret(settings, row.secret_enc)
    step = security.totp_step(secret, code, None) if secret else None
    if step is None:
        row.attempts += 1
        _write(session, who, "staff.login_failed", user, after={"reason": "two-factor setup code"})
        if row.attempts >= SETUP_TRIES:
            session.delete(row)
            raise LoginFailed("Too many wrong codes. Please sign in again to get a new QR code.")
        raise LoginFailed(SETUP_FAILED)
    before = snapshot(user)
    user.totp_secret_enc = row.secret_enc
    session.execute(delete(StaffSetupTicket).where(StaffSetupTicket.staff_user_id == user.id))
    session.flush()
    _write(session, who, "staff.two_factor_enrolled", user, before, snapshot(user))
    return user, _start_session(session, settings, who, user, step, at)


def logout(session: Session, actor: Actor, row: StaffSession) -> None:
    row.revoked_at = now()
    session.flush()
    audit.record(
        session,
        actor_id=actor.id,
        actor_label=actor.label,
        action="staff.logout",
        entity_type="staff_session",
        entity_id=row.id,
        ip=actor.ip,
    )


def revoke_sessions(session: Session, user: StaffUser) -> None:
    session.execute(
        update(StaffSession)
        .where(StaffSession.staff_user_id == user.id, StaffSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )
