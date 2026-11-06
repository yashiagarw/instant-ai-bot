"""/api/admin/dispatch: auto-offer switches per zone and job type (super admins: dispatch.manage), audited. Off by
default: no row means off. app/requests/dispatch.py does the offering."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.permissions import Perm
from app.db import get_session
from app.estimates.zones import zones
from app.requests.models import AutoOfferSetting, ServiceType

router = APIRouter(prefix="/admin/dispatch", tags=["admin"], dependencies=[Depends(enforce)])
DbSession = Annotated[Session, Depends(get_session)]
JOB_TYPES = {"at_location": "Mechanic at the car", "tow": "Tow", "workshop": "Workshop visit"}


class Option(BaseModel):
    code: str
    label: str


class Switch(BaseModel):
    zone: str
    service_type: ServiceType
    enabled: bool
    updated_by: str
    updated_at: datetime | None


class AutoOfferOut(BaseModel):
    zones: list[Option]
    job_types: list[Option]
    switches: list[Switch]
    offer_expiry_seconds: int
    escalate_seconds: int


class SwitchIn(BaseModel):
    zone: str
    service_type: ServiceType
    enabled: bool


def _out(session: Session, request: Request) -> AutoOfferOut:
    rows = {(r.zone, str(r.service_type)): r for r in session.scalars(select(AutoOfferSetting))}
    switches = []
    for code in zones():
        for st in ServiceType:
            r = rows.get((code, st.value))
            switches.append(
                Switch(
                    zone=code,
                    service_type=st,
                    enabled=bool(r and r.enabled),
                    updated_by=r.updated_by if r else "",
                    updated_at=r.updated_at if r else None,
                )
            )
    s = request.app.state.settings
    return AutoOfferOut(
        zones=[Option(code=c, label=z.label) for c, z in zones().items()],
        job_types=[Option(code=k, label=v) for k, v in JOB_TYPES.items()],
        switches=switches,
        offer_expiry_seconds=s.offer_expiry_seconds,
        escalate_seconds=s.dispatch_escalate_seconds,
    )


@router.get("/auto-offer", response_model=AutoOfferOut)
@requires(Perm.dispatch_manage)
def get_auto_offer(request: Request, staff: CurrentStaff, session: DbSession):
    return _out(session, request)


@router.put("/auto-offer", response_model=AutoOfferOut, responses={422: {}})
@requires(Perm.dispatch_manage)
def set_auto_offer(body: SwitchIn, request: Request, staff: CurrentStaff, session: DbSession):
    if body.zone not in zones():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown zone")
    row = session.get(AutoOfferSetting, (body.zone, body.service_type))
    before = bool(row and row.enabled)
    if row is None:
        row = AutoOfferSetting(zone=body.zone, service_type=body.service_type)
        session.add(row)
    row.enabled, row.updated_by, row.updated_at = body.enabled, staff.label, datetime.now(UTC)
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="dispatch.auto_offer",
        entity_type="auto_offer_setting",
        entity_id=f"{body.zone}/{body.service_type}",
        before={"enabled": before},
        after={"enabled": body.enabled},
        ip=staff.ip,
    )
    session.commit()
    return _out(session, request)
