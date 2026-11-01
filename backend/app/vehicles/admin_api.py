"""/api/admin/vehicles: the unlisted-vehicles review queue (cars customers typed because they were not listed). The
car catalogue is not part of the dataset versions: adding a car is live at once (and audited). `python -m
app.vehicles.seed` never deletes it unless run with --prune."""

from __future__ import annotations

from datetime import UTC, date, datetime
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
from app.vehicles.models import Generation, Make, Model, UnlistedVehicle, Variant
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
        _mark(make, staff)
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
        _mark(model, staff)
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
            _mark(v, staff)
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


# ---------------------------------------------------------------- catalogue editor (live, audited)


def _now() -> datetime:
    return datetime.now(UTC)


def _mark(row, staff) -> None:
    """Edited in the admin app: the seed keeps it as it is (and never prunes it)."""
    row.edited_by, row.edited_at = staff.label, _now()


def _search_text(make: Make, model: Model) -> str:
    spec = ModelSpec(name=model.name, aliases=model.aliases.split(), variants=[_ANY_VARIANT])
    return search_text(MakeSpec(name=make.name, aliases=make.aliases.split(), models=[spec]), spec)


_ANY_VARIANT = VariantSpec(
    years=(2000, None), fuel=Fuel.petrol, transmissions=[Transmission.mt], segment=PriceSegment.budget
)


def _audit(session: Session, staff, action: str, kind: str, row_id, before: dict | None, after: dict | None) -> None:
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action=action,
        entity_type=kind,
        entity_id=row_id,
        before=before,
        after=after,
        ip=staff.ip,
    )


def _get(session: Session, model, row_id: int, what: str):
    row = session.get(model, row_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")
    return row


def _variant_uses(session: Session, ids: list[int]) -> int:
    from app.accounts.models import UserVehicle
    from app.diagnosis.models import DiagnosisSession

    if not ids:
        return 0
    return (session.scalar(select(func.count()).where(DiagnosisSession.variant_id.in_(ids))) or 0) + (
        session.scalar(select(func.count()).where(UserVehicle.variant_id.in_(ids))) or 0
    )


DUPLICATE = "That already exists (same name, or same variant)."


def _commit_or_409(session: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE) from e


def _flush_or_409(session: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()  # nothing of this request is kept
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE) from e


class MakeIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=60)
    aliases: str = Field("", max_length=300, description="Other words people type, space separated")


class ModelIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    make_id: int
    name: str = Field(min_length=1, max_length=60)
    body_type: str | None = Field(None, max_length=40)
    aliases: str = Field("", max_length=300)


class GenerationIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    model_id: int
    name: str = Field(min_length=1, max_length=80)
    year_from: int = Field(ge=1980, le=2100)
    year_to: int | None = Field(None, ge=1980, le=2100)

    @model_validator(mode="after")
    def years_in_order(self):
        if self.year_to is not None and self.year_to < self.year_from:
            raise ValueError("the last year is before the first")
        return self


class VariantIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    model_id: int
    generation_id: int | None = None
    fuel: Fuel
    transmission: Transmission
    engine: str = Field("", max_length=40)
    year_from: int = Field(ge=1980, le=2100)
    year_to: int | None = Field(None, ge=1980, le=2100)
    price_segment: PriceSegment
    features: dict[str, bool] = {}

    @model_validator(mode="after")
    def check(self):
        from app.vehicles.features import FEATURES

        if self.year_to is not None and self.year_to < self.year_from:
            raise ValueError("the last year is before the first")
        if unknown := sorted(set(self.features) - set(FEATURES)):
            raise ValueError(f"unknown features {unknown}")
        return self


def _make_out(m: Make) -> dict:
    return {"id": m.id, "name": m.name, "aliases": m.aliases, "edited_by": m.edited_by}


def _model_out(m: Model) -> dict:
    return {
        "id": m.id,
        "make_id": m.make_id,
        "name": m.name,
        "body_type": m.body_type,
        "aliases": m.aliases,
        "edited_by": m.edited_by,
    }


def _generation_out(g: Generation) -> dict:
    return {
        "id": g.id,
        "model_id": g.model_id,
        "name": g.name,
        "year_from": g.year_from,
        "year_to": g.year_to,
        "edited_by": g.edited_by,
    }


def _variant_out(v: Variant) -> dict:
    return {
        "id": v.id,
        "model_id": v.model_id,
        "generation_id": v.generation_id,
        "name": v.name,
        "fuel": str(v.fuel),
        "transmission": str(v.transmission),
        "engine": v.engine,
        "year_from": v.year_from,
        "year_to": v.year_to,
        "price_segment": str(v.price_segment),
        "features": dict(v.features or {}),
        "edited_by": v.edited_by,
    }


@router.get("/catalogue")
@requires(Perm.content_read)
def catalogue(session: DbSession):
    """The whole car catalogue: makes, their models, each model's generations and variants."""
    out = []
    for make in session.scalars(select(Make).order_by(Make.name)):
        out.append(
            {
                **_make_out(make),
                "models": [
                    {
                        **_model_out(m),
                        "generations": [_generation_out(g) for g in m.generations],
                        "variants": [_variant_out(v) for v in m.variants],
                    }
                    for m in make.models
                ],
            }
        )
    from app.vehicles.features import FEATURES

    return {"makes": out, "features": FEATURES}


@router.post("/makes", status_code=201, responses={409: {}})
@requires(Perm.vehicles_manage)
def create_make(body: MakeIn, staff: CurrentStaff, session: DbSession):
    make = Make(name=body.name, aliases=normalise(body.aliases))
    _mark(make, staff)
    session.add(make)
    _flush_or_409(session)
    _audit(session, staff, "vehicle.make_create", "make", make.id, None, _make_out(make))
    _commit_or_409(session)
    return _make_out(make)


@router.put("/makes/{make_id}", responses={404: {}, 409: {}})
@requires(Perm.vehicles_manage)
def update_make(make_id: int, body: MakeIn, staff: CurrentStaff, session: DbSession):
    make = _get(session, Make, make_id, "Make")
    before = _make_out(make)
    make.name, make.aliases = body.name, normalise(body.aliases)
    _mark(make, staff)
    for m in make.models:
        m.search_text = _search_text(make, m)
    _audit(session, staff, "vehicle.make_update", "make", make.id, before, _make_out(make))
    _commit_or_409(session)
    return _make_out(make)


@router.delete("/makes/{make_id}", status_code=204, responses={404: {}, 409: {}})
@requires(Perm.vehicles_manage)
def delete_make(make_id: int, staff: CurrentStaff, session: DbSession):
    make = _get(session, Make, make_id, "Make")
    if make.models:
        raise HTTPException(status.HTTP_409_CONFLICT, "Delete its models first.")
    _audit(session, staff, "vehicle.make_delete", "make", make.id, _make_out(make), None)
    session.delete(make)
    session.commit()


@router.post("/models", status_code=201, responses={404: {}, 409: {}})
@requires(Perm.vehicles_manage)
def create_model(body: ModelIn, staff: CurrentStaff, session: DbSession):
    make = _get(session, Make, body.make_id, "Make")
    model = Model(make_id=make.id, name=body.name, body_type=body.body_type, aliases=normalise(body.aliases))
    model.make = make
    model.search_text = _search_text(make, model)
    _mark(model, staff)
    session.add(model)
    _flush_or_409(session)
    _audit(session, staff, "vehicle.model_create", "model", model.id, None, _model_out(model))
    _commit_or_409(session)
    return _model_out(model)


@router.put("/models/{model_id}", responses={404: {}, 409: {}})
@requires(Perm.vehicles_manage)
def update_model(model_id: int, body: ModelIn, staff: CurrentStaff, session: DbSession):
    model = _get(session, Model, model_id, "Model")
    before = _model_out(model)
    model.name, model.body_type, model.aliases = body.name, body.body_type, normalise(body.aliases)
    model.search_text = _search_text(model.make, model)
    _mark(model, staff)
    _audit(session, staff, "vehicle.model_update", "model", model.id, before, _model_out(model))
    _commit_or_409(session)
    return _model_out(model)


@router.delete("/models/{model_id}", status_code=204, responses={404: {}, 409: {}})
@requires(Perm.vehicles_manage)
def delete_model(model_id: int, staff: CurrentStaff, session: DbSession):
    model = _get(session, Model, model_id, "Model")
    if model.variants:
        raise HTTPException(status.HTTP_409_CONFLICT, "Delete its variants first.")
    _audit(session, staff, "vehicle.model_delete", "model", model.id, _model_out(model), None)
    session.delete(model)
    session.commit()


@router.post("/generations", status_code=201, responses={404: {}, 409: {}})
@requires(Perm.vehicles_manage)
def create_generation(body: GenerationIn, staff: CurrentStaff, session: DbSession):
    _get(session, Model, body.model_id, "Model")
    g = Generation(**body.model_dump())
    _mark(g, staff)
    session.add(g)
    _flush_or_409(session)
    _audit(session, staff, "vehicle.generation_create", "generation", g.id, None, _generation_out(g))
    _commit_or_409(session)
    return _generation_out(g)


@router.put("/generations/{generation_id}", responses={404: {}, 409: {}})
@requires(Perm.vehicles_manage)
def update_generation(generation_id: int, body: GenerationIn, staff: CurrentStaff, session: DbSession):
    g = _get(session, Generation, generation_id, "Generation")
    before = _generation_out(g)
    g.name, g.year_from, g.year_to = body.name, body.year_from, body.year_to
    _mark(g, staff)
    _audit(session, staff, "vehicle.generation_update", "generation", g.id, before, _generation_out(g))
    _commit_or_409(session)
    return _generation_out(g)


@router.delete("/generations/{generation_id}", status_code=204, responses={404: {}})
@requires(Perm.vehicles_manage)
def delete_generation(generation_id: int, staff: CurrentStaff, session: DbSession):
    """Its variants stay (no longer grouped)."""
    g = _get(session, Generation, generation_id, "Generation")
    _audit(session, staff, "vehicle.generation_delete", "generation", g.id, _generation_out(g), None)
    session.delete(g)
    session.commit()


def _apply_variant(session: Session, v: Variant, body: VariantIn) -> None:
    model = _get(session, Model, body.model_id, "Model")
    if body.generation_id is not None:
        g = _get(session, Generation, body.generation_id, "Generation")
        if g.model_id != model.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That generation belongs to another model.")
    spec = VariantSpec(
        years=(body.year_from, body.year_to),
        fuel=body.fuel,
        transmissions=[body.transmission],
        segment=body.price_segment,
        engine=body.engine,
    )
    v.model_id, v.generation_id, v.fuel, v.transmission = model.id, body.generation_id, body.fuel, body.transmission
    v.engine, v.year_from, v.year_to, v.price_segment = body.engine, body.year_from, body.year_to, body.price_segment
    v.features, v.name = body.features, variant_name(spec, body.transmission)


@router.post("/variants", status_code=201, responses={404: {}, 409: {}, 422: {}})
@requires(Perm.vehicles_manage)
def create_variant(body: VariantIn, staff: CurrentStaff, session: DbSession):
    v = Variant()
    _apply_variant(session, v, body)
    _mark(v, staff)
    session.add(v)
    _flush_or_409(session)
    _audit(session, staff, "vehicle.variant_create", "variant", v.id, None, _variant_out(v))
    _commit_or_409(session)
    return _variant_out(v)


@router.put("/variants/{variant_id}", responses={404: {}, 409: {}, 422: {}})
@requires(Perm.vehicles_manage)
def update_variant(variant_id: int, body: VariantIn, staff: CurrentStaff, session: DbSession):
    """Change a variant (price segment, years, features ...): live at once for new diagnoses."""
    v = _get(session, Variant, variant_id, "Variant")
    before = _variant_out(v)
    _apply_variant(session, v, body)
    _mark(v, staff)
    _audit(session, staff, "vehicle.variant_update", "variant", v.id, before, _variant_out(v))
    _commit_or_409(session)
    return _variant_out(v)


@router.delete("/variants/{variant_id}", status_code=204, responses={404: {}, 409: {}})
@requires(Perm.vehicles_manage)
def delete_variant(variant_id: int, staff: CurrentStaff, session: DbSession):
    v = _get(session, Variant, variant_id, "Variant")
    if uses := _variant_uses(session, [v.id]):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{uses} diagnoses or saved cars use this variant: change it instead (e.g. its years) of deleting it.",
        )
    _audit(session, staff, "vehicle.variant_delete", "variant", v.id, _variant_out(v), None)
    session.delete(v)
    session.commit()
