"""Customer tracking (Phase 5.3): the request's live status for its owner (the logged-in customer, or the browser that
made it, by its anonymous cookie), with the mechanic's first name and photo, the arrival estimate the mechanic
entered, and a masked call to the mechanic. The page polls GET every 10 seconds (no server-sent events: plain
requests work through Caddy and on flaky mobile data without held-open connections).

    GET  /api/requests/{id}/tracking
    POST /api/requests/{id}/call         the customer is rung first, then connected (neither sees the other's number)

Locations are pincode centres, rough for many pincodes: no distance is ever claimed to the customer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts import service as accounts
from app.accounts.api import STATUS_LABELS, OptionalUser, _mechanic_first_name, _status_events, timeline
from app.accounts.schemas import TimelineStep
from app.accounts.service import ANON_COOKIE
from app.calls import service as calls
from app.db import get_session
from app.mechanics.app_api import CallOut, _place_call
from app.requests.models import ServiceRequest

router = APIRouter(prefix="/requests", tags=["service requests"])
DbSession = Annotated[Session, Depends(get_session)]


class MechanicCard(BaseModel):
    first_name: str
    photo_url: str | None = Field(description="Signed link, valid a few minutes")


class TrackingOut(BaseModel):
    id: uuid.UUID
    reference: str
    status: str
    status_label: str
    timeline: list[TimelineStep]
    mechanic: MechanicCard | None
    eta_at: datetime | None = Field(description="The mechanic's own estimate (shown as 'about N minutes')")
    eta_minutes: int | None
    can_call: bool
    poll_seconds: int = 10
    updated_at: datetime


def _owned(session: Session, request_id: uuid.UUID, user, anon: str | None) -> ServiceRequest:
    r = session.get(ServiceRequest, request_id)
    if r is None or not accounts.owns(r, user, anon):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return r


@router.get("/{request_id}/tracking", response_model=TrackingOut, responses={404: {}})
def tracking(
    request_id: uuid.UUID,
    request: Request,
    user: OptionalUser,
    session: DbSession,
    im_anon: Annotated[str | None, Cookie(alias=ANON_COOKIE)] = None,
):
    r = _owned(session, request_id, user, im_anon)
    first = _mechanic_first_name(session, r)
    card = None
    if first:
        mech = calls.job_mechanic(session, r)
        photo = None
        if mech is not None and mech.photo_key:
            from app.uploads.api import get_storage

            try:
                photo = get_storage(request).presign_view(
                    mech.photo_key, request.app.state.settings.upload_view_ttl_seconds
                )
            except Exception:  # storage down: the page works without the photo
                photo = None
        card = MechanicCard(first_name=first, photo_url=photo)
    now = datetime.now(UTC)
    on_the_way = str(r.status) in ("accepted", "en_route")
    eta = r.eta_at if on_the_way and r.eta_at else None
    return TrackingOut(
        id=r.id,
        reference=r.reference,
        status=str(r.status),
        status_label=STATUS_LABELS[str(r.status)],
        timeline=timeline(r, _status_events(session, r)),
        mechanic=card,
        eta_at=eta,
        eta_minutes=max(0, round((eta - now).total_seconds() / 60)) if eta else None,
        can_call=calls.can_call(r) and card is not None,
        updated_at=r.status_changed_at or r.created_at,
    )


@router.post("/{request_id}/call", response_model=CallOut, responses={404: {}, 409: {}, 429: {}, 503: {}})
def call_mechanic(
    request_id: uuid.UUID,
    request: Request,
    user: OptionalUser,
    session: DbSession,
    im_anon: Annotated[str | None, Cookie(alias=ANON_COOKIE)] = None,
):
    r = _owned(session, request_id, user, im_anon)
    return _place_call(request, session, r, "customer_to_mechanic")
