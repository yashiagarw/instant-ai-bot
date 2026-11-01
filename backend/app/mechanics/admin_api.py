"""/api/admin/mechanics: mechanics, their skills, zones, shifts and on / off duty (live, audited), and their ID
documents (encrypted, mechanics.documents = super admins only; every view audited)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.permissions import Perm
from app.db import get_session
from app.knowledge.models import Category
from app.mechanics import documents as docs
from app.mechanics.geo import locate
from app.mechanics.matching import acceptance_rates, jobs_today
from app.mechanics.models import (
    DocumentKind,
    Mechanic,
    MechanicAvailability,
    MechanicDocument,
    MechanicSkill,
    MechanicZone,
)
from app.requests.schemas import normalise_mobile

router = APIRouter(prefix="/admin/mechanics", tags=["admin"], dependencies=[Depends(enforce)])
DbSession = Annotated[Session, Depends(get_session)]
PIN = re.compile(r"^\d{6}$")


# ---------------------------------------------------------------- schemas


class ZoneIn(BaseModel):
    pincode: str | None = None
    radius_km: Decimal | None = Field(default=None, ge=Decimal("0.5"), le=100)
    center_lat: Decimal | None = Field(default=None, ge=28, le=29.5)  # Delhi NCR
    center_lon: Decimal | None = Field(default=None, ge=76.5, le=78)

    @model_validator(mode="after")
    def one_kind(self):
        if (self.pincode is None) == (self.radius_km is None):
            raise ValueError("a zone is either a pincode or a radius")
        if self.pincode is not None and not PIN.fullmatch(self.pincode):
            raise ValueError("a pincode has 6 digits")
        if (self.center_lat is None) != (self.center_lon is None):
            raise ValueError("give both centre coordinates, or neither (= the mechanic's base)")
        return self


class ShiftIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def order(self):
        if self.end_time <= self.start_time:
            raise ValueError("a shift ends after it starts (split overnight shifts at midnight)")
        return self


class MechanicIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    phone: str
    base_pincode: str
    base_area: str = Field(default="", max_length=120)
    rating: Decimal | None = Field(default=None, ge=0, le=5)
    max_jobs_per_day: int = Field(default=4, ge=1, le=30)
    staff_user_id: str | None = None
    active: bool = True
    notes: str = Field(default="", max_length=1000)

    @field_validator("phone")
    @classmethod
    def mobile(cls, v: str) -> str:
        return normalise_mobile(v)

    @field_validator("base_pincode")
    @classmethod
    def pincode(cls, v: str) -> str:
        v = v.strip()
        if not PIN.fullmatch(v):
            raise ValueError("a pincode has 6 digits")
        if locate(v) is None:
            raise ValueError("this pincode is outside our Delhi NCR zones")
        return v


class SkillsIn(BaseModel):
    category_codes: list[str]


class ZonesIn(BaseModel):
    zones: list[ZoneIn] = Field(max_length=200)


class AvailabilityIn(BaseModel):
    shifts: list[ShiftIn] = Field(max_length=50)


class DutyIn(BaseModel):
    on_duty: bool


class MechanicOut(BaseModel):
    id: int
    name: str
    phone: str
    base_pincode: str
    base_area: str
    base_point: list[float] | None
    base_precision: str | None = Field(description='"pincode", "rough" (can be 10-20 km off) or "zone" (zone centre)')
    rating: float | None
    max_jobs_per_day: int
    on_duty: bool
    on_duty_changed_at: datetime | None
    active: bool
    staff_user_id: str | None
    notes: str
    dev_seed: bool
    skills: list[str]
    zones: list[dict]
    shifts: list[dict]
    jobs_today: int
    acceptance_rate: float | None
    documents: int | None = Field(description="How many documents (null without mechanics.documents)")


class DocumentOut(BaseModel):
    id: int
    kind: DocumentKind
    filename: str
    content_type: str
    size: int
    uploaded_by: str
    uploaded_at: datetime


# ---------------------------------------------------------------- helpers


def _out(session: Session, m: Mechanic, staff, load: dict | None = None, accept: dict | None = None) -> MechanicOut:
    now = datetime.now(UTC)
    load = jobs_today(session, now) if load is None else load
    accept = acceptance_rates(session, now) if accept is None else accept
    base = locate(m.base_pincode)
    n_docs = None
    if Perm.mechanics_documents in staff.perms:
        n_docs = len(session.scalars(select(MechanicDocument.id).where(MechanicDocument.mechanic_id == m.id)).all())
    return MechanicOut(
        id=m.id,
        name=m.name,
        phone=m.phone,
        base_pincode=m.base_pincode,
        base_area=m.base_area,
        base_point=[base.lat, base.lon] if base else None,
        base_precision=base.precision if base else None,
        rating=float(m.rating) if m.rating is not None else None,
        max_jobs_per_day=m.max_jobs_per_day,
        on_duty=m.on_duty,
        on_duty_changed_at=m.on_duty_changed_at,
        active=m.active,
        staff_user_id=str(m.staff_user_id) if m.staff_user_id else None,
        notes=m.notes,
        dev_seed=m.dev_seed,
        skills=sorted(s.category_code for s in m.skills),
        zones=[_zone_dict(z) for z in m.zones],
        shifts=[_shift(s) for s in m.shifts],
        jobs_today=load.get(m.id, 0),
        acceptance_rate=None if accept.get(m.id) is None else round(accept[m.id], 2),
        documents=n_docs,
    )


def _shift(s: MechanicAvailability | ShiftIn) -> dict:
    return {
        "weekday": s.weekday,
        "start_time": s.start_time.strftime("%H:%M"),
        "end_time": s.end_time.strftime("%H:%M"),
    }


def _zone_dict(z: MechanicZone) -> dict:
    point = locate(z.pincode) if z.pincode else None
    return {
        "pincode": z.pincode,
        "radius_km": float(z.radius_km) if z.radius_km is not None else None,
        "center_lat": float(z.center_lat) if z.center_lat is not None else None,
        "center_lon": float(z.center_lon) if z.center_lon is not None else None,
        "point": [point.lat, point.lon] if point else None,
        "precision": point.precision if point else None,
    }


def _get(session: Session, mechanic_id: int) -> Mechanic:
    m = session.scalar(
        select(Mechanic)
        .where(Mechanic.id == mechanic_id)
        .options(selectinload(Mechanic.skills), selectinload(Mechanic.zones), selectinload(Mechanic.shifts))
    )
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mechanic not found")
    return m


def _record(session: Session, staff, action: str, m: Mechanic, before: dict | None, after: dict | None) -> None:
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action=action,
        entity_type="mechanic",
        entity_id=str(m.id),
        before=before,
        after=after,
        ip=staff.ip,
    )


def _fields(m: Mechanic) -> dict:
    return {
        "name": m.name,
        "phone": m.phone,  # masked by the audit helper
        "base_pincode": m.base_pincode,
        "base_area": m.base_area,
        "rating": None if m.rating is None else str(m.rating),
        "max_jobs_per_day": m.max_jobs_per_day,
        "staff_user_id": str(m.staff_user_id) if m.staff_user_id else None,
        "active": m.active,
        "notes": m.notes,
    }


def _apply(m: Mechanic, body: MechanicIn) -> None:
    m.name, m.phone, m.base_pincode, m.base_area = body.name.strip(), body.phone, body.base_pincode, body.base_area
    m.rating, m.max_jobs_per_day, m.active, m.notes = body.rating, body.max_jobs_per_day, body.active, body.notes
    m.staff_user_id = body.staff_user_id or None


# ---------------------------------------------------------------- mechanics


@router.get("", response_model=list[MechanicOut])
@requires(Perm.mechanics_read)
def list_mechanics(
    staff: CurrentStaff,
    session: DbSession,
    include_inactive: Annotated[bool, Query()] = False,
):
    q = (
        select(Mechanic)
        .options(selectinload(Mechanic.skills), selectinload(Mechanic.zones), selectinload(Mechanic.shifts))
        .order_by(Mechanic.name)
    )
    if not include_inactive:
        q = q.where(Mechanic.active)
    now = datetime.now(UTC)
    load, accept = jobs_today(session, now), acceptance_rates(session, now)
    return [_out(session, m, staff, load, accept) for m in session.scalars(q)]


@router.get("/{mechanic_id}", response_model=MechanicOut, responses={404: {}})
@requires(Perm.mechanics_read)
def get_mechanic(mechanic_id: int, staff: CurrentStaff, session: DbSession):
    return _out(session, _get(session, mechanic_id), staff)


@router.post("", response_model=MechanicOut, status_code=201, responses={422: {}})
@requires(Perm.mechanics_manage)
def create_mechanic(body: MechanicIn, staff: CurrentStaff, session: DbSession):
    m = Mechanic()
    _apply(m, body)
    # A new mechanic works their base pincode until zones are set.
    m.zones = [MechanicZone(pincode=m.base_pincode)]
    session.add(m)
    session.flush()
    _record(session, staff, "mechanic.create", m, None, _fields(m))
    session.commit()
    return _out(session, _get(session, m.id), staff)


@router.put("/{mechanic_id}", response_model=MechanicOut, responses={404: {}, 422: {}})
@requires(Perm.mechanics_manage)
def update_mechanic(mechanic_id: int, body: MechanicIn, staff: CurrentStaff, session: DbSession):
    m = _get(session, mechanic_id)
    before = _fields(m)
    _apply(m, body)
    _record(session, staff, "mechanic.update", m, before, _fields(m))
    session.commit()
    return _out(session, _get(session, m.id), staff)


@router.put("/{mechanic_id}/skills", response_model=MechanicOut, responses={404: {}, 422: {}})
@requires(Perm.mechanics_manage)
def set_skills(mechanic_id: int, body: SkillsIn, staff: CurrentStaff, session: DbSession):
    m = _get(session, mechanic_id)
    codes = sorted(set(body.category_codes))
    known = set(session.scalars(select(Category.code).where(Category.code.in_(codes))))
    if unknown := [c for c in codes if c not in known]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown categories: {', '.join(unknown)}")
    before = sorted(s.category_code for s in m.skills)
    m.skills = [MechanicSkill(category_code=c) for c in codes]
    _record(session, staff, "mechanic.skills", m, {"skills": before}, {"skills": codes})
    session.commit()
    return _out(session, _get(session, m.id), staff)


@router.put("/{mechanic_id}/zones", response_model=MechanicOut, responses={404: {}, 422: {}})
@requires(Perm.mechanics_manage)
def set_zones(mechanic_id: int, body: ZonesIn, staff: CurrentStaff, session: DbSession):
    m = _get(session, mechanic_id)
    pins = [z.pincode for z in body.zones if z.pincode]
    if len(pins) != len(set(pins)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A pincode is listed twice")
    if outside := [p for p in pins if locate(p) is None]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Outside our Delhi NCR zones: {', '.join(outside)}")
    before = [_zone_dict(z) for z in m.zones]
    m.zones.clear()
    session.flush()
    m.zones.extend(MechanicZone(**z.model_dump()) for z in body.zones)
    session.flush()
    after = [_zone_dict(z) for z in m.zones]
    _record(session, staff, "mechanic.zones", m, {"zones": before}, {"zones": after})
    session.commit()
    return _out(session, _get(session, m.id), staff)


@router.put("/{mechanic_id}/availability", response_model=MechanicOut, responses={404: {}, 422: {}})
@requires(Perm.mechanics_manage)
def set_availability(mechanic_id: int, body: AvailabilityIn, staff: CurrentStaff, session: DbSession):
    """Weekly shifts in India time. No shifts = any time while on duty."""
    m = _get(session, mechanic_id)
    by_day: dict[int, list[ShiftIn]] = {}
    for s in sorted(body.shifts, key=lambda s: (s.weekday, s.start_time)):
        prev = by_day.setdefault(s.weekday, [])
        if prev and s.start_time < prev[-1].end_time:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Two shifts on the same day overlap")
        prev.append(s)
    before = [_shift(s) for s in m.shifts]
    m.shifts.clear()
    session.flush()
    m.shifts.extend(MechanicAvailability(**s.model_dump()) for s in body.shifts)
    _record(
        session, staff, "mechanic.availability", m, {"shifts": before}, {"shifts": [_shift(s) for s in body.shifts]}
    )
    session.commit()
    return _out(session, _get(session, m.id), staff)


@router.put("/{mechanic_id}/duty", response_model=MechanicOut, responses={404: {}, 422: {}})
@requires(Perm.mechanics_manage)
def set_duty(mechanic_id: int, body: DutyIn, staff: CurrentStaff, session: DbSession):
    m = _get(session, mechanic_id)
    if body.on_duty and not m.active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This mechanic is inactive")
    before = m.on_duty
    m.on_duty, m.on_duty_changed_at = body.on_duty, datetime.now(UTC)
    _record(session, staff, "mechanic.duty", m, {"on_duty": before}, {"on_duty": m.on_duty})
    session.commit()
    return _out(session, _get(session, m.id), staff)


# ---------------------------------------------------------------- documents (super admins only)


@router.get("/{mechanic_id}/documents", response_model=list[DocumentOut], responses={404: {}})
@requires(Perm.mechanics_documents)
def list_documents(mechanic_id: int, staff: CurrentStaff, session: DbSession):
    _get(session, mechanic_id)
    rows = session.scalars(
        select(MechanicDocument).where(MechanicDocument.mechanic_id == mechanic_id).order_by(MechanicDocument.id)
    )
    return [DocumentOut.model_validate(d, from_attributes=True) for d in rows]


async def _doc_body(request: Request) -> bytes:
    limit = request.app.state.settings.mechanic_doc_max_mb * 2**20
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"The file is larger than {limit // 2**20} MB")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a file")
    return bytes(data)


@router.post(
    "/{mechanic_id}/documents",
    response_model=DocumentOut,
    status_code=201,
    responses={404: {}, 413: {}, 422: {}, 503: {}},
)
@requires(Perm.mechanics_documents)
def upload_document(
    mechanic_id: int,
    request: Request,
    staff: CurrentStaff,
    session: DbSession,
    data: Annotated[bytes, Depends(_doc_body)],
    kind: Annotated[DocumentKind, Query()],
    filename: Annotated[str, Query(min_length=1, max_length=120)],
):
    """Upload a PDF, JPEG, PNG or WebP (the raw file as the body). Stored encrypted with MECHANIC_DOCS_KEY."""
    m = _get(session, mechanic_id)
    real = docs.sniff(data)
    if real is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Upload a PDF, JPEG, PNG or WebP file")
    try:
        ciphertext = docs.encrypt(request.app.state.settings, data)
    except docs.DocumentsKeyMissing as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Documents are switched off: " + str(e)) from e
    safe_name = re.sub(r"[^\w.\- ]", "_", filename).strip() or "document"
    d = MechanicDocument(
        mechanic_id=m.id,
        kind=kind,
        filename=safe_name,
        content_type=real,
        size=len(data),
        ciphertext=ciphertext,
        uploaded_by=staff.label,
    )
    session.add(d)
    session.flush()
    _record(
        session, staff, "mechanic.document_upload", m, None, {"document_id": d.id, "kind": str(kind), "size": d.size}
    )
    session.commit()
    return DocumentOut.model_validate(d, from_attributes=True)


@router.get("/{mechanic_id}/documents/{document_id}", responses={404: {}, 503: {}})
@requires(Perm.mechanics_documents)
def view_document(mechanic_id: int, document_id: int, request: Request, staff: CurrentStaff, session: DbSession):
    """The decrypted file. Every view is written to the audit log."""
    d = session.get(MechanicDocument, document_id)
    if d is None or d.mechanic_id != mechanic_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    try:
        content = docs.decrypt(request.app.state.settings, d.ciphertext)
    except (docs.DocumentsKeyMissing, docs.DocumentUnreadable) as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="mechanic.document_view",
        entity_type="mechanic_document",
        entity_id=str(d.id),
        after={"mechanic_id": mechanic_id, "kind": str(d.kind)},
        ip=staff.ip,
    )
    session.commit()
    return Response(
        content,
        media_type=d.content_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{d.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{mechanic_id}/documents/{document_id}", status_code=204, responses={404: {}})
@requires(Perm.mechanics_documents)
def delete_document(mechanic_id: int, document_id: int, staff: CurrentStaff, session: DbSession):
    d = session.get(MechanicDocument, document_id)
    if d is None or d.mechanic_id != mechanic_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    m = _get(session, mechanic_id)
    _record(session, staff, "mechanic.document_delete", m, {"document_id": d.id, "kind": str(d.kind)}, None)
    session.delete(d)
    session.commit()
