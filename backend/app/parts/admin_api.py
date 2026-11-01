"""/api/admin/parts: the Parts & Prices editors. Reads come from a draft version; saves are edits in that draft through
/api/admin/knowledge/versions/{id}/edits (entities part, part_price, part_fit, labour_rate, zone_rate, part_images),
published through the dataset pipeline. Plus: the second look on prices of 20,000 rupees or more, the zone labour
rates as YAML, and the CSV bulk import of prices (preview, then into the draft)."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import date
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.permissions import Perm
from app.db import get_session
from app.estimates.zones import zones
from app.knowledge.edits import service
from app.knowledge.edits.handlers import HANDLERS, Invalid
from app.knowledge.edits.parts_handlers import (
    SECOND_LOOK_INR,
    PartData,
    PriceData,
    fit_key,
    needs_second_look,
    new_part_key,
    price_key,
)
from app.knowledge.models import DatasetVersion, EditStatus, Image, KnowledgeEdit
from app.parts.models import LabourRate, Part, PartCompatibility, PartImage, PartPrice, ZoneLabourRate
from app.vehicles.models import Make, Model

router = APIRouter(prefix="/admin/parts", tags=["admin"], dependencies=[Depends(enforce)])
DbSession = Annotated[Session, Depends(get_session)]
SEGMENTS = ("budget", "mid", "premium")
CSV_COLUMNS = [
    "part_type",
    "description",
    "brand",
    "part_number",
    "quantity",
    "segment",
    "price_inr",
    "price_max_inr",
    "supplier",
    "source_url",
    "checked_on",
    "make",
    "model",
    "year_from",
    "year_to",
    "fuel",
    "transmission",
    "note",
]


def _version(session: Session, version_id: int) -> DatasetVersion:
    v = session.get(DatasetVersion, version_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset version not found")
    return v


def _actor(staff) -> service.Actor:
    return service.Actor(staff.user.id, staff.label, staff.ip)


def _pending(session: Session, v: DatasetVersion) -> dict[str, int]:
    return {
        f"{e.entity}:{e.key}": e.id
        for e in session.scalars(
            select(KnowledgeEdit).where(
                KnowledgeEdit.dataset_version_id == v.id, KnowledgeEdit.status == EditStatus.draft
            )
        )
    }


def _new_parts(session: Session, v: DatasetVersion) -> list[str]:
    """Parts this draft creates (their rows exist already; listed even before they have a price)."""
    return list(
        session.scalars(
            select(KnowledgeEdit.key).where(
                KnowledgeEdit.dataset_version_id == v.id,
                KnowledgeEdit.status == EditStatus.draft,
                KnowledgeEdit.entity == "part",
                KnowledgeEdit.base.is_(None),
            )
        )
    )


@router.get("/versions/{version_id}/parts")
@requires(Perm.content_read)
def parts(version_id: int, session: DbSession):
    """Parts with a price or fit in this version (and the parts the draft adds), with price range and flags."""
    v = _version(session, version_id)
    prices = select(PartPrice.part_id).where(PartPrice.dataset_version_id == v.id)
    fits = select(PartCompatibility.part_id).where(PartCompatibility.dataset_version_id == v.id)
    rows = session.scalars(
        select(Part).where(or_(Part.id.in_(prices), Part.id.in_(fits), Part.part_key.in_(_new_parts(session, v))))
    ).all()
    stats = {
        pid: (n, lo, hi, flagged)
        for pid, n, lo, hi, flagged in session.execute(
            select(
                PartPrice.part_id,
                func.count(),
                func.min(PartPrice.price_inr),
                func.max(func.coalesce(PartPrice.price_max_inr, PartPrice.price_inr)),
                func.count().filter(
                    func.coalesce(PartPrice.price_max_inr, PartPrice.price_inr) >= SECOND_LOOK_INR,
                    PartPrice.second_look_by.is_(None),
                ),
            )
            .where(PartPrice.dataset_version_id == v.id)
            .group_by(PartPrice.part_id)
        )
    }
    n_fits = dict(
        session.execute(
            select(PartCompatibility.part_id, func.count())
            .where(PartCompatibility.dataset_version_id == v.id)
            .group_by(PartCompatibility.part_id)
        ).all()
    )
    edited = {k.split(":", 1)[1].split("|")[0] for k in _pending(session, v)}
    return [
        {
            "key": p.part_key,
            "description": p.description,
            "part_type": p.part_type.name,
            "brand": p.brand.name if p.brand else "",
            "part_number": p.part_number or "",
            "kind": str(p.kind),
            "prices": stats.get(p.id, (0, None, None, 0))[0],
            "price_min": stats.get(p.id, (0, None, None, 0))[1],
            "price_max": stats.get(p.id, (0, None, None, 0))[2],
            "second_look": stats.get(p.id, (0, 0, 0, 0))[3],
            "fits": n_fits.get(p.id, 0),
            "edited": p.part_key in edited,
        }
        for p in sorted(rows, key=lambda p: (p.part_type.name.lower(), p.description.lower()))
    ]


def _price_out(r: PartPrice, part_key: str, edited: dict) -> dict:
    key = price_key(part_key, str(r.segment), r.source_ref)
    out = {
        "key": key,
        "segment": str(r.segment),
        "source": str(r.source),
        "source_ref": r.source_ref,
        "price_inr": r.price_inr,
        "price_max_inr": r.price_max_inr,
        "supplier": r.supplier or "",
        "source_url": r.source_url or "",
        "checked_on": r.checked_on.isoformat() if r.checked_on else None,
        "verification_status": str(r.verification_status),
        "gst_included": r.gst_included,
        "fitting_included": r.fitting_included,
        "model_verified": r.model_verified,
        "price_basis": r.price_basis or "",
        "note": r.note or "",
        "second_look_by": r.second_look_by,
        "second_look_at": r.second_look_at.isoformat() if r.second_look_at else None,
        "edit": edited.get(f"part_price:{key}"),
    }
    out["flagged"] = needs_second_look(out)
    out["missing_source"] = not (out["supplier"] or out["source_url"]) or not out["checked_on"]
    return out


@router.get("/versions/{version_id}/parts/{part_key:path}", responses={404: {}})
@requires(Perm.content_read)
def part_detail(version_id: int, part_key: str, session: DbSession):
    """One part: details (the draft's when it changes them), pictures, prices and fits."""
    v = _version(session, version_id)
    snap = HANDLERS["part"].snapshot(session, v, part_key)
    if snap is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Part not found")
    edited = _pending(session, v)
    p = session.scalar(select(Part).where(Part.part_key == part_key))
    prices = []
    fits = []
    images = []
    if p is not None:
        prices = [
            _price_out(r, part_key, edited)
            for r in session.scalars(
                select(PartPrice)
                .where(PartPrice.dataset_version_id == v.id, PartPrice.part_id == p.id)
                .order_by(PartPrice.segment, PartPrice.price_inr)
            )
        ]
        models = {m.id: f"{mk} {m.name}" for m, mk in session.execute(select(Model, Make.name).join(Make))}
        for r in session.scalars(
            select(PartCompatibility).where(
                PartCompatibility.dataset_version_id == v.id, PartCompatibility.part_id == p.id
            )
        ):
            d = {
                "model_id": r.model_id,
                "year_from": r.year_from,
                "year_to": r.year_to,
                "fuel": str(r.fuel) if r.fuel else None,
                "transmission": str(r.transmission) if r.transmission else None,
            }
            key = fit_key(part_key, d)
            fits.append(
                {
                    "key": key,
                    **d,
                    "model": models.get(r.model_id, "?"),
                    "fit_text": r.fit_text,
                    "verification_status": str(r.verification_status),
                    "source_url": r.source_url or "",
                    "source": str(r.source),
                    "edit": edited.get(f"part_fit:{key}"),
                }
            )
        for img in session.scalars(
            select(Image).join(PartImage, PartImage.image_id == Image.id).where(PartImage.part_id == p.id)
        ):
            images.append(
                {"sha1": img.sha1, "url": "/media/" + img.path.removeprefix("data/media/"), "caption": img.caption}
            )
    return {
        "key": part_key,
        "part": snap,
        "part_edit": edited.get(f"part:{part_key}"),
        "prices": prices,
        "fits": fits,
        "images": images,
        "images_edit": edited.get(f"part_images:{part_key}"),
    }


@router.get("/versions/{version_id}/prices")
@requires(Perm.content_read)
def prices(version_id: int, session: DbSession):
    """Every price of the version with its source, date and flags (20,000 rupees or more without a second look;
    missing source or date)."""
    v = _version(session, version_id)
    edited = _pending(session, v)
    out = []
    for r, key, desc in session.execute(
        select(PartPrice, Part.part_key, Part.description)
        .join(Part, Part.id == PartPrice.part_id)
        .where(PartPrice.dataset_version_id == v.id)
        .order_by(Part.description, PartPrice.segment)
    ):
        out.append({**_price_out(r, key, edited), "part_key": key, "part": desc})
    return out


@router.get("/versions/{version_id}/labour")
@requires(Perm.content_read)
def labour(version_id: int, session: DbSession):
    """Zone labour rates (per hour, zone x segment) and the labour research rows of the version."""
    v = _version(session, version_id)
    edited = _pending(session, v)
    rates = {
        (r.zone, str(r.segment)): r
        for r in session.scalars(select(ZoneLabourRate).where(ZoneLabourRate.dataset_version_id == v.id))
    }
    grid = []
    for code, z in zones().items():
        for seg in SEGMENTS:
            r = rates.get((code, seg))
            key = f"{code}|{seg}"
            grid.append(
                {
                    "key": key,
                    "zone": code,
                    "zone_label": z.label,
                    "segment": seg,
                    "rate_min_inr": r.rate_min_inr if r else None,
                    "rate_max_inr": r.rate_max_inr if r else None,
                    "source": r.source if r else "",
                    "checked_on": r.checked_on.isoformat() if r else None,
                    "edit": edited.get(f"zone_rate:{key}"),
                }
            )
    research = [
        {
            "key": f"{r.repair}|{r.segment}|{r.city}",
            "repair": r.repair,
            "segment": str(r.segment),
            "city": r.city,
            "amount_inr": r.amount_inr,
            "workshop_type": r.workshop_type or "",
            "basis": r.basis or "",
            "status": r.status,
            "checked_on": r.checked_on.isoformat() if r.checked_on else None,
            "source": str(r.source),
            "edit": edited.get(f"labour_rate:{r.repair}|{r.segment}|{r.city}"),
        }
        for r in session.scalars(
            select(LabourRate)
            .where(LabourRate.dataset_version_id == v.id)
            .order_by(LabourRate.repair, LabourRate.segment)
        )
    ]
    return {"zones": grid, "research": research}


@router.get("/versions/{version_id}/zone-rates.yaml", response_class=PlainTextResponse)
@requires(Perm.content_read)
def zone_rates_yaml(version_id: int, session: DbSession):
    """The version's zone rates in the format of data/catalogue/zone_labour_rates.yaml (to commit to the repo)."""
    v = _version(session, version_id)
    rows = session.scalars(select(ZoneLabourRate).where(ZoneLabourRate.dataset_version_id == v.id)).all()
    by_zone: dict[str, dict] = {
        code: {s: None for s in SEGMENTS} | {"source": "", "checked_on": None} for code in zones()
    }
    for r in rows:
        z = by_zone.setdefault(r.zone, {s: None for s in SEGMENTS})
        z[str(r.segment)] = r.rate_min_inr if r.rate_min_inr == r.rate_max_inr else [r.rate_min_inr, r.rate_max_inr]
        z["source"], z["checked_on"] = r.source, r.checked_on  # one source per zone in the file: the latest wins
    head = (
        f"# Exported from dataset version {v.id} (admin Parts & Prices). Mechanic labour per hour by Delhi NCR zone\n"
        "# and price segment (rupees). A zone's rates count only with a source and a checked_on date.\n"
    )
    return head + yaml.safe_dump({"reviewed": False, "zones": by_zone}, sort_keys=False, allow_unicode=True)


class KeyIn(BaseModel):
    key: str


@router.post("/versions/{version_id}/prices/second-look", responses={404: {}, 422: {}})
@requires(Perm.knowledge_edit)
def second_look(version_id: int, body: KeyIn, staff: CurrentStaff, session: DbSession):
    """A second person checks a price of 20,000 rupees or more (never the person who entered it)."""
    v = _version(session, version_id)
    try:
        service.second_look(session, v, _actor(staff), body.key)
    except (Invalid, ValueError) as e:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    session.commit()
    return HANDLERS["part_price"].snapshot(session, v, body.key)


# ---------------------------------------------------------------- CSV bulk import


@router.get("/csv-template", response_class=PlainTextResponse)
@requires(Perm.content_read)
def csv_template():
    """The columns of the price import, with one example row."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_COLUMNS)
    w.writerow(
        [
            "Brake pad set",
            "Front brake pads",
            "Bosch",
            "0986AB1234",
            "1",
            "budget",
            "1450",
            "1700",
            "Boodmo",
            "https://boodmo.com/...",
            date.today().isoformat(),
            "Maruti Suzuki",
            "Swift",
            "2018",
            "2023",
            "petrol",
            "",
            "front axle",
        ]
    )
    return out.getvalue()


async def _csv_body(request: Request) -> str:
    data = await request.body()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The file is larger than 2 MB")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Save the CSV as UTF-8") from e


def _num(value: str) -> int | None:
    value = (value or "").replace(",", "").replace("₹", "").strip()
    return int(float(value)) if value else None


def _parse_rows(session: Session, text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    missing = [
        c
        for c in ("part_type", "description", "segment", "price_inr", "checked_on")
        if c not in (reader.fieldnames or [])
    ]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Missing columns: {', '.join(missing)}")
    models = {(mk.lower(), m.name.lower()): m.id for m, mk in session.execute(select(Model, Make.name).join(Make))}
    out = []
    for n, raw in enumerate(reader, start=2):
        row = {k: (raw.get(k) or "").strip() for k in CSV_COLUMNS}
        errors: list[str] = []
        part = price = fit = None
        try:
            part = PartData(
                description=row["description"],
                part_type=row["part_type"],
                brand=row["brand"],
                part_number=row["part_number"],
                quantity=int(row["quantity"] or 1),
            ).model_dump(mode="json")
        except (ValidationError, ValueError) as e:
            errors.append(_short(e))
        if row["segment"] not in SEGMENTS:
            errors.append("segment must be budget, mid or premium")
        try:
            price = PriceData(
                price_inr=_num(row["price_inr"]),
                price_max_inr=_num(row["price_max_inr"]),
                supplier=row["supplier"],
                source_url=row["source_url"],
                checked_on=row["checked_on"],
                note=row["note"],
            ).model_dump(mode="json")
        except (ValidationError, ValueError, TypeError) as e:
            errors.append(_short(e))
        if row["make"] or row["model"]:
            model_id = models.get((row["make"].lower(), row["model"].lower()))
            if model_id is None:
                errors.append(f"unknown car {row['make']} {row['model']} (add it on the Vehicles page first)")
            else:
                fit = {
                    "model_id": model_id,
                    "year_from": _num(row["year_from"]),
                    "year_to": _num(row["year_to"]),
                    "fuel": row["fuel"] or None,
                    "transmission": row["transmission"] or None,
                    "verification_status": "listed",
                    "fit_text": f"{row['make']} {row['model']} (CSV import)",
                    "source_url": row["source_url"],
                }
        key = new_part_key(part) if part else None
        out.append(
            {
                "line": n,
                "row": row,
                "errors": errors,
                "part_key": key,
                "part": part,
                "price": price,
                "fit": fit,
                "flagged": bool(price) and needs_second_look(price),
            }
        )
    return out


def _short(e: Exception) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(f"{'.'.join(map(str, x['loc'])) or 'row'}: {x['msg']}" for x in e.errors())
    return str(e)


@router.post("/versions/{version_id}/import", responses={404: {}, 413: {}, 422: {}})
@requires(Perm.knowledge_edit)
def import_csv(
    version_id: int,
    staff: CurrentStaff,
    session: DbSession,
    text: Annotated[str, Depends(_csv_body)],
    commit: Annotated[bool, Query()] = False,
):
    """Check a price CSV (commit=false: the preview, nothing saved), then import the valid rows into the draft: the
    part (new ones), its price for the segment and, with a car, its fit. One audit entry for the import."""
    v = _version(session, version_id)
    rows = _parse_rows(session, text)
    ok = [r for r in rows if not r["errors"]]
    summary = {
        "rows": len(rows),
        "valid": len(ok),
        "errors": len(rows) - len(ok),
        "flagged": sum(r["flagged"] for r in ok),
    }
    if not commit:
        return {"summary": summary, "rows": rows}
    if not ok:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No valid rows to import")
    actor = _actor(staff)
    try:
        service.editable(v)
        for r in ok:
            if HANDLERS["part"].snapshot(session, v, r["part_key"]) is None:
                service.save(session, v, actor, "part", r["part_key"], r["part"], "CSV import", audit_entry=False)
            tag = "csv-" + hashlib.sha1(repr(sorted(r["row"].items())).encode()).hexdigest()[:10]
            service.save(
                session,
                v,
                actor,
                "part_price",
                price_key(r["part_key"], r["row"]["segment"], tag),
                r["price"],
                "CSV import",
                audit_entry=False,
            )
            if r["fit"]:
                service.save(
                    session,
                    v,
                    actor,
                    "part_fit",
                    fit_key(r["part_key"], r["fit"]),
                    r["fit"],
                    "CSV import",
                    audit_entry=False,
                )
    except (Invalid, ValueError) as e:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _short(e)) from e
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="parts.csv_import",
        entity_type="dataset_version",
        entity_id=v.id,
        before=None,
        after=summary,
        ip=staff.ip,
    )
    session.commit()
    return {"summary": summary, "rows": rows}
