"""Access control for /api/admin: one router-level dependency (enforce) on every admin route.

- Each admin endpoint declares its permission with @requires(Perm.x), or @public (only the staff login). An
  endpoint that declares nothing is refused for everyone: deny by default.
- Staff are recognised only by the im_staff cookie (a staff session). The customer cookie (im_session) is never
  read here, so a customer login never opens /api/admin.
- Sessions end STAFF_SESSION_HOURS after login, or after STAFF_IDLE_MINUTES without a request.
- create_app refuses to start if an admin route declares no permission, or a route under /api/admin is not on
  the admin router (check_admin_routes).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.service import token_hash
from app.admin.models import StaffSession, StaffUser
from app.admin.permissions import PUBLIC, Perm, permissions_for
from app.db import get_session
from app.ratelimit import client_ip

log = logging.getLogger(__name__)
STAFF_COOKIE = "im_staff"
ADMIN_PREFIX = "/api/admin"
COOKIE_PATH = "/api/admin"
ATTR = "__admin_permission__"
SEEN_EVERY = timedelta(seconds=60)  # last_seen_at is written at most this often
NOT_SIGNED_IN = "Please sign in as staff"
NOT_ALLOWED = "You don't have access to this"


def requires(perm: Perm) -> Callable:
    def mark(fn: Callable) -> Callable:
        setattr(fn, ATTR, perm)
        return fn

    return mark


def public(fn: Callable) -> Callable:
    setattr(fn, ATTR, PUBLIC)
    return fn


@dataclass
class Staff:
    user: StaffUser
    session_row: StaffSession
    perms: frozenset[Perm]
    ip: str

    @property
    def label(self) -> str:
        return self.user.email


def _now() -> datetime:
    return datetime.now(UTC)


def authenticate(request: Request, session: Session) -> Staff | None:
    settings = request.app.state.settings
    token = request.cookies.get(STAFF_COOKIE)
    if not token:
        return None
    row = session.scalar(select(StaffSession).where(StaffSession.token_hash == token_hash(token)))
    now = _now()
    if (
        row is None
        or row.revoked_at is not None
        or row.expires_at <= now
        or row.last_seen_at <= now - timedelta(minutes=settings.staff_idle_minutes)
    ):
        return None
    user = session.get(StaffUser, row.staff_user_id)
    if user is None or not user.active:
        return None
    if now - row.last_seen_at >= SEEN_EVERY:
        row.last_seen_at = now
        session.commit()
    return Staff(user, row, permissions_for(user.role_codes), client_ip(request, settings.trust_forwarded_for))


def enforce(request: Request, session: Annotated[Session, Depends(get_session)]) -> None:
    route = request.scope.get("route")
    perm = getattr(getattr(route, "endpoint", None), ATTR, None)
    if perm is None:  # deny by default: the route declared no permission
        log.error("admin route without a permission: %s", getattr(route, "path", "?"))
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_ALLOWED)
    if perm == PUBLIC:
        return
    staff = authenticate(request, session)
    if staff is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    if perm not in staff.perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_ALLOWED)
    request.state.staff = staff


def current_staff(request: Request) -> Staff:
    staff = getattr(request.state, "staff", None)
    if staff is None:  # only reachable if a public route asks for it
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)
    return staff


CurrentStaff = Annotated[Staff, Depends(current_staff)]


def admin_routes(router: APIRouter) -> list[APIRoute]:
    """The admin router's endpoints (paths without the /api prefix)."""
    return [r for r in router.routes if isinstance(r, APIRoute)]


def check_admin_routes(app: FastAPI, router: APIRouter) -> None:
    """The app does not start unless the admin router runs `enforce`, each admin endpoint declares a permission, and
    no other route sits under /api/admin (checked against the app's OpenAPI paths)."""
    if not any(d.dependency is enforce for d in router.dependencies):
        raise RuntimeError("the admin router must depend on app.admin.deps.enforce")
    declared = set()
    for r in admin_routes(router):
        if getattr(r.endpoint, ATTR, None) is None:
            raise RuntimeError(f"{r.path} declares no permission (use @requires or @public)")
        declared.add("/api" + r.path)
    stray = [p for p in app.openapi()["paths"] if p.startswith(ADMIN_PREFIX) and p not in declared]
    if stray:
        raise RuntimeError(f"routes under /api/admin outside the admin router: {stray}")
