"""/api/admin/vehicles: the unlisted-vehicles review queue (cars customers typed because they were not listed). The
car catalogue is not part of the dataset versions: adding a car is live at once (and audited). `python -m
app.vehicles.seed` never deletes it unless run with --prune."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.permissions import Perm
from app.db import get_session
from app.enums import Fuel, PriceSegment, Transmission
from app.vehicles.models import Make, Model, UnlistedVehicle, Variant
from app.vehicles.seed import MakeSpec, ModelSpec, VariantSpec, normalise, search_text, variant_name

router = APIRouter(prefix="/admin/vehicles", tags=["admin"], dependencies=[Depends(enforce)])
DbSession = Annotated[Session, Depends(get_session)]


class UnlistedOut(BaseModel):
    id: int
    created_at: str
    raw_text: str
    typed_make: str | None
    typed_model: str | None
    typed_year: int | None
    fuel: str | None
    transmission: str | None
    price_segment: str | None
    reviewed: bool
    sessions: int


class AddIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    make: str = Field(min_length=2, max_length=60)
    model: str = Field(min_length=1, max_length=60)
    body: str | None = Field(None, max_length=40)
    year_from: int = Field(ge=1990, le=date.today().year + 1)
    year_to: int | None = Field(None, ge=1990, le=date.today().year + 1)
    fuel: Fuel
    transmissions: list[Transmission] = Field(min_length=1)
    price_segment: PriceSegment
    engine: str = Field("", max_length=40)

    @model_validator(mode="after")
    def years_in_order(self):
        if self.year_to is not None and self.year_to < self.year_from:
            raise ValueError("the last year is before the first")
        return self


@router.get("/unlisted", response_model=list[UnlistedOut])
@requires(Perm.content_read)
def unlisted(session: DbSession, reviewed: Annotated[bool, Query()] = False):
    """Cars typed by customers, newest first (not reviewed yet by default)."""
    from app.diagnosis.models import DiagnosisSession

    used = dict(
        session.execute(
            select(DiagnosisSession.unlisted_vehicle_id, func.count())
            .where(DiagnosisSession.unlisted_vehicle_id.is_not(None))
            .group_by(DiagnosisSession.unlisted_vehicle_id)
        ).all()
    )
    rows = session.scalars(
        select(UnlistedVehicle)
        .where(UnlistedVehicle.reviewed.is_(reviewed))
        .order_by(UnlistedVehicle.id.desc())
        .limit(500)
    )
    return [
        UnlistedOut(
            id=u.id,
            created_at=u.created_at.isoformat(),
            raw_text=u.raw_text,
            typed_make=u.typed_make,
            typed_model=u.typed_model,
            typed_year=u.typed_year,
            fuel=str(u.fuel) if u.fuel else None,
            transmission=str(u.transmission) if u.transmission else None,
            price_segment=str(u.price_segment) if u.price_segment else None,
            reviewed=u.reviewed,
            sessions=used.get(u.id, 0),
        )
        for u in rows
    ]


@router.get("/makes")
@requires(Perm.content_read)
def makes(session: DbSession):
    """Makes and their models (for the 'add to catalogue' form)."""
    return [
        {"name": m.name, "models": [x.name for x in m.models]}
        for m in session.scalars(select(Make).order_by(Make.name))
    ]


def _unlisted_or_404(session: Session, unlisted_id: int) -> UnlistedVehicle:
    u = session.get(UnlistedVehicle, unlisted_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if u.reviewed:
        raise HTTPException(status.HTTP_409_CONFLICT, "This car was already reviewed")
    return u


@router.post("/unlisted/{unlisted_id}/add", responses={404: {}, 409: {}, 422: {}})
@requires(Perm.vehicles_manage)
def add_to_catalogue(unlisted_id: int, body: AddIn, staff: CurrentStaff, session: DbSession):
    """Add the car to the catalogue (make, model and one variant per gearbox; existing ones are reused), live."""
    u = _unlisted_or_404(session, unlisted_id)
    make = session.scalar(select(Make).where(func.lower(Make.name) == body.make.lower()))
    created = []
    if make is None:
        make = Make(name=body.make)
        session.add(make)
        session.flush()
        created.append(f"make {make.name}")
    model = session.scalar(select(Model).where(Model.make_id == make.id, func.lower(Model.name) == body.model.lower()))
    spec = VariantSpec(
        years=(body.year_from, body.year_to),
        fuel=body.fuel,
        transmissions=body.transmissions,
        segment=body.price_segment,
        engine=body.engine,
    )
    if model is None:
        model_spec = ModelSpec(name=body.model, body=body.body, variants=[spec])
        model = Model(
            make_id=make.id,
            name=body.model,
            body_type=body.body,
            search_text=search_text(MakeSpec(name=make.name, models=[model_spec]), model_spec),
        )
        session.add(model)
        session.flush()
        created.append(f"model {make.name} {model.name}")
    for t in body.transmissions:
        exists = session.scalar(
            select(Variant).where(
                Variant.model_id == model.id,
                Variant.fuel == body.fuel,
                Variant.transmission == t,
                Variant.year_from == body.year_from,
                Variant.engine == body.engine,
            )
        )
        if exists is None:
            v = Variant(
                model_id=model.id,
                name=variant_name(spec, t),
                fuel=body.fuel,
                transmission=t,
                engine=body.engine,
                year_from=body.year_from,
                year_to=body.year_to,
                price_segment=body.price_segment,
                features={},
            )
            session.add(v)
            created.append(f"variant {v.name}")
    u.reviewed = True
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="vehicle.add_from_unlisted",
        entity_type="unlisted_vehicle",
        entity_id=u.id,
        before={"typed": u.raw_text or f"{u.typed_make} {u.typed_model} {u.typed_year or ''}".strip()},
        after={**body.model_dump(mode="json"), "created": created},
        ip=staff.ip,
    )
    session.commit()
    return {"created": created, "search": normalise(f"{make.name} {model.name}")}


@router.post("/unlisted/{unlisted_id}/dismiss", responses={404: {}, 409: {}})
@requires(Perm.vehicles_manage)
def dismiss(unlisted_id: int, staff: CurrentStaff, session: DbSession):
    """Not a car to add (a typo, a joke, already listed): mark it reviewed."""
    u = _unlisted_or_404(session, unlisted_id)
    u.reviewed = True
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="vehicle.dismiss_unlisted",
        entity_type="unlisted_vehicle",
        entity_id=u.id,
        before={"reviewed": False},
        after={"reviewed": True},
        ip=staff.ip,
    )
    session.commit()
    return {"ok": True}
