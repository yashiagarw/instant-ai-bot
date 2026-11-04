"""Notification endpoints.

Customers (web app):
    GET    /api/notifications/config                 push public key, WhatsApp opt-in wording
    POST   /api/notifications/push-subscriptions     this browser turned alerts on (account or anonymous cookie)
    DELETE /api/notifications/push-subscriptions     ... and off
    GET    /api/me/notifications                     channel choices and the WhatsApp opt-in (logged in)
    PUT    /api/me/notifications                     turn SMS / browser alerts on or off
    PUT    /api/me/notifications/whatsapp            opt in (with the wording version shown) or out
WhatsApp (Meta):
    GET    /api/webhooks/whatsapp                    webhook verification (hub.verify_token)
    POST   /api/webhooks/whatsapp                    signed events: stored, answered 200, handled by the worker
Admin:
    PUT    /api/admin/mechanics/{id}/whatsapp-optin  a mechanic agreed on a call (audited)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts import service as accounts
from app.accounts.api import OptionalUser, RequiredUser, _cookie
from app.accounts.service import ANON_COOKIE
from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.permissions import Perm
from app.db import get_session
from app.notify import inbound, optins
from app.notify import whatsapp as wa
from app.notify.models import Channel, NotificationPreference, PushSubscription
from app.notify.push import allowed_endpoint
from app.ratelimit import RateLimiter, client_ip

log = logging.getLogger(__name__)
DbSession = Annotated[Session, Depends(get_session)]
router = APIRouter(prefix="/notifications", tags=["notifications"])
me_router = APIRouter(prefix="/me/notifications", tags=["notifications"])
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])
admin_router = APIRouter(prefix="/admin/mechanics", tags=["admin"], dependencies=[Depends(enforce)])


# ---------------------------------------------------------------- schemas


class ConfigOut(BaseModel):
    push_public_key: str | None = Field(description="VAPID public key for PushManager.subscribe; null = no alerts")
    whatsapp_consent_version: str
    whatsapp_consent_text: str


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=10, max_length=100)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: PushKeys


class PushEndpointIn(BaseModel):
    endpoint: str = Field(max_length=1000)


class WhatsappOut(BaseModel):
    opted_in: bool
    since: datetime | None
    consent_text_version: str
    consent_text: str


class PreferencesOut(BaseModel):
    sms: bool = Field(description="Updates about my requests by SMS")
    push: bool = Field(description="Alerts in the browsers where I turned them on")
    whatsapp: WhatsappOut


class PreferencesIn(BaseModel):
    sms: bool | None = None
    push: bool | None = None


class WhatsappIn(BaseModel):
    opt_in: bool
    consent_text_version: str | None = Field(default=None, description="Required to opt in: the wording shown")


class MechanicOptinIn(BaseModel):
    opt_in: bool
    note: str = Field(default="", max_length=200, description="e.g. 'agreed on the call of 4 Nov'")


class MechanicOptinOut(BaseModel):
    mechanic_id: int
    opted_in: bool
    since: datetime | None
    source: str | None


# ---------------------------------------------------------------- customers


def _limit(request: Request) -> None:
    state = request.app.state
    limiter = getattr(state, "push_limiter", None)
    if limiter is None:
        limiter = state.push_limiter = RateLimiter(20, 600)
    if limiter.check(client_ip(request, state.settings.trust_forwarded_for)) is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Try again shortly.")


@router.get("/config", response_model=ConfigOut)
def config(request: Request):
    return ConfigOut(
        push_public_key=request.app.state.settings.vapid_public_key or None,
        whatsapp_consent_version=optins.WHATSAPP_CUSTOMER_VERSION,
        whatsapp_consent_text=optins.WHATSAPP_CUSTOMER_TEXT,
    )


@router.post("/push-subscriptions", status_code=201, dependencies=[Depends(_limit)], responses={422: {}})
def subscribe(body: PushSubscriptionIn, request: Request, response: Response, session: DbSession, user: OptionalUser):
    """This browser turned alerts on: alerts about the account's requests, or (not logged in) this browser's."""
    if not allowed_endpoint(body.endpoint):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Not a browser push service address")
    anon = request.cookies.get(ANON_COOKIE) or ""
    if user is None and not anon:
        anon = accounts.new_anon_token()
        _cookie(response, request.app.state.settings, ANON_COOKIE, anon, 365 * 86400)
    sub = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=body.endpoint)
        session.add(sub)
    sub.p256dh, sub.auth, sub.revoked_at = body.keys.p256dh, body.keys.auth, None
    sub.user_id = user.id if user else None
    sub.anon_key_hash = None if user else accounts.token_hash(anon)
    if user is not None:  # alerts turned on here count as "browser alerts on" for the account
        _set_pref(session, user.id, Channel.push, True)
    session.commit()
    return {"ok": True}


@router.delete("/push-subscriptions", responses={404: {}})
def unsubscribe(body: PushEndpointIn, request: Request, session: DbSession, user: OptionalUser):
    sub = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    anon = request.cookies.get(ANON_COOKIE)
    mine = sub is not None and (
        (user is not None and sub.user_id == user.id)
        or (anon and sub.anon_key_hash and sub.anon_key_hash == accounts.token_hash(anon))
    )
    if not mine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    sub.revoked_at = datetime.now(UTC)
    session.commit()
    return {"ok": True}


def _set_pref(session: Session, user_id: uuid.UUID, channel: Channel, enabled: bool) -> None:
    pref = session.get(NotificationPreference, (user_id, channel))
    if pref is None:
        session.add(NotificationPreference(user_id=user_id, channel=channel, enabled=enabled))
    else:
        pref.enabled, pref.updated_at = enabled, datetime.now(UTC)


def _preferences(session: Session, request: Request, user) -> PreferencesOut:
    from app.notify.service import preferences

    prefs = preferences(session, user.id)
    o = optins.active(session, request.app.state.settings, user.phone, user_id=user.id)
    return PreferencesOut(
        sms=prefs.get(Channel.sms, True),
        push=prefs.get(Channel.push, True),
        whatsapp=WhatsappOut(
            opted_in=o is not None,
            since=o.opted_in_at if o else None,
            consent_text_version=optins.WHATSAPP_CUSTOMER_VERSION,
            consent_text=optins.WHATSAPP_CUSTOMER_TEXT,
        ),
    )


@me_router.get("", response_model=PreferencesOut)
def my_preferences(request: Request, user: RequiredUser, session: DbSession):
    return _preferences(session, request, user)


@me_router.put("", response_model=PreferencesOut)
def set_preferences(body: PreferencesIn, request: Request, user: RequiredUser, session: DbSession):
    for channel, value in ((Channel.sms, body.sms), (Channel.push, body.push)):
        if value is not None:
            _set_pref(session, user.id, channel, value)
    session.commit()
    return _preferences(session, request, user)


@me_router.put("/whatsapp", response_model=PreferencesOut, responses={422: {}})
def set_whatsapp(body: WhatsappIn, request: Request, user: RequiredUser, session: DbSession):
    """Opt in to WhatsApp updates (the wording version shown is required) or out. Withdrawn opt-ins are kept."""
    settings = request.app.state.settings
    if body.opt_in:
        try:
            version = body.consent_text_version or ""
            optins.record(session, settings, phone=user.phone, source="account_page", user_id=user.id, version=version)
        except optins.OptinError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    else:
        optins.withdraw(session, user_id=user.id, source="account_page")
    session.commit()
    return _preferences(session, request, user)


# ---------------------------------------------------------------- WhatsApp webhook


@webhook_router.get("/whatsapp", response_class=PlainTextResponse, responses={403: {}})
def whatsapp_verify(
    request: Request,
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
):
    """Meta's check when the webhook URL is saved: echo hub.challenge if the verify token matches."""
    if not wa.verify_challenge(request.app.state.settings, mode, token):
        log.warning("WhatsApp webhook verification refused (wrong or missing WHATSAPP_VERIFY_TOKEN)")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return PlainTextResponse(challenge or "")


@webhook_router.post("/whatsapp", responses={401: {}, 503: {}})
async def whatsapp_events(request: Request, session: DbSession):
    """Signed by Meta (X-Hub-Signature-256 over the raw body with WHATSAPP_APP_SECRET). Stored once per message id
    and answered at once; the worker does the work."""
    settings = request.app.state.settings
    if not settings.whatsapp_app_secret:
        log.error("WhatsApp webhook called but WHATSAPP_APP_SECRET is not set: refusing it")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Not configured")
    raw = await request.body()
    if not wa.signature_ok(settings.whatsapp_app_secret, raw, request.headers.get("x-hub-signature-256")):
        log.warning("WhatsApp webhook with a bad signature refused")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")
    try:
        items = wa.parse_webhook(json.loads(raw or b"{}"))
    except ValueError:
        return {"ok": True}  # signed but not JSON: nothing to do
    if items:

        def keep() -> None:
            inbound.store(session, settings, items)
            session.commit()  # then queued for the worker (after commit)

        await run_in_threadpool(keep)
    return {"ok": True}


# ---------------------------------------------------------------- admin


@admin_router.put("/{mechanic_id}/whatsapp-optin", response_model=MechanicOptinOut, responses={404: {}})
@requires(Perm.mechanics_manage)
def mechanic_optin(mechanic_id: int, body: MechanicOptinIn, request: Request, staff: CurrentStaff, session: DbSession):
    """Record that a mechanic agreed to WhatsApp job offers on a call (the agent read them the wording), or that
    they no longer want them. Audited. Mechanics can also send START / STOP to the WhatsApp number."""
    from app.mechanics.models import Mechanic

    mech = session.get(Mechanic, mechanic_id)
    if mech is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    settings = request.app.state.settings
    if body.opt_in:
        version = optins.WHATSAPP_MECHANIC_VERSION
        optins.record(
            session,
            settings,
            phone=mech.phone,
            source="staff_call",
            mechanic_id=mech.id,
            version=version,
            recorded_by=staff.label,
        )
    else:
        optins.withdraw(session, mechanic_id=mech.id, source="staff_call")
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="mechanic.whatsapp_optin",
        entity_type="mechanic",
        entity_id=mech.id,
        after={"opted_in": body.opt_in, "wording": optins.WHATSAPP_MECHANIC_VERSION, "note": body.note},
        ip=staff.ip,
    )
    session.commit()
    o = optins.active(session, settings, mech.phone, mechanic_id=mech.id)
    return MechanicOptinOut(
        mechanic_id=mech.id, opted_in=o is not None, since=o.opted_in_at if o else None, source=o.source if o else None
    )
