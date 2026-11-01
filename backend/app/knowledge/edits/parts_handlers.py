"""Parts & Prices editor handlers (same contract as handlers.py). They run in the pipeline's "parts edits apply"
step, after `parts build` (which rebuilds a version's prices, fits and labour rows from the sheets and review files),
so an edit survives every rebuild.

- part: a buyable item. The parts table is shared by every version: a new part is created at once (unused until a
  price or fit points at it); a change to an existing part is written at publish (write_live), shown in the draft
  from the edit.
- part_price, part_fit, labour_rate, zone_rate: rows of the version. Prices and labour need a source and a date;
  prices of SECOND_LOOK_INR or more are flagged until a second person checks them.
- part_images: pictures of a part (uploaded ones too).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.enums import Fuel, PriceSegment, Transmission
from app.knowledge.edits.handlers import Handler, Invalid, Orphan, Schema
from app.knowledge.models import DatasetVersion, EditStatus, Image, KnowledgeEdit, PartVerification
from app.parts.models import (
    Brand,
    BrandKind,
    CatalogueSource,
    FitStatus,
    LabourRate,
    Part,
    PartCompatibility,
    PartImage,
    PartKind,
    PartPrice,
    PartType,
    ZoneLabourRate,
)

SECOND_LOOK_INR = 20_000
Source = Annotated[str, Field(max_length=500)]


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _part(s: Session, key: str) -> Part | None:
    return s.scalar(select(Part).where(Part.part_key == key))


def _pending(s: Session, version: DatasetVersion, entity: str, key: str) -> KnowledgeEdit | None:
    return s.scalar(
        select(KnowledgeEdit).where(
            KnowledgeEdit.dataset_version_id == version.id,
            KnowledgeEdit.entity == entity,
            KnowledgeEdit.key == key,
            KnowledgeEdit.status == EditStatus.draft,
        )
    )


def _not_future(v: date) -> date:
    if v > date.today():
        raise ValueError("the check date is in the future")
    return v


# ---------------------------------------------------------------- parts


class PartData(Schema):
    description: Annotated[str, Field(min_length=2, max_length=300)]
    part_type: Annotated[str, Field(min_length=2, max_length=120)]
    brand: Annotated[str, Field(max_length=120)] = ""
    brand_kind: BrandKind = BrandKind.unspecified
    part_number: Annotated[str, Field(max_length=80)] = ""
    quantity: int = Field(1, ge=1, le=50)
    kind: PartKind = PartKind.part
    segment: PriceSegment | None = None  # generic parts only
    generic: bool = False

    @model_validator(mode="after")
    def generic_rules(self):
        if self.generic and self.part_number:
            raise ValueError("a generic part has no part number")
        if self.generic and self.segment is None:
            raise ValueError("a generic part needs its price segment")
        return self


def new_part_key(data: dict) -> str:
    """PN:<brand>:<number>:<qty> with a part number (as the build makes them), else ADM:<type>:<description>."""
    if data.get("part_number"):
        number = data["part_number"].upper().replace(" ", "")
        return f"PN:{(data.get('brand') or '-').lower()}:{number}:{data.get('quantity', 1)}"
    slug = re.sub(r"[^a-z0-9]+", "-", f"{data['part_type']} {data['description']}".lower()).strip("-")[:80]
    return f"ADM:{slug}"


class PartHandler(Handler):
    entity, label, schema = "part", "Parts", PartData
    can_create = True
    global_table = True
    stage = "parts"

    def snapshot(self, s, version, key):
        pending = _pending(s, version, self.entity, key)
        if pending is not None and pending.data is not None:
            return pending.data  # the draft's version of a shared row
        p = _part(s, key)
        return None if p is None else self._out(p)

    @staticmethod
    def _out(p: Part) -> dict:
        return {
            "description": p.description,
            "part_type": p.part_type.name,
            "brand": p.brand.name if p.brand else "",
            "brand_kind": str(p.brand.kind) if p.brand else "unspecified",
            "part_number": p.part_number or "",
            "quantity": p.quantity,
            "kind": str(p.kind),
            "segment": str(p.segment) if p.segment else None,
            "generic": p.generic,
        }

    def write(self, s, version, key, data):
        """Draft: create the part if it does not exist yet; changes to an existing part wait for publish."""
        if data is not None and _part(s, key) is None:
            self._fill(s, Part(part_key=key), data, new=True)

    def write_live(self, s: Session, key: str, data: dict | None) -> None:
        p = _part(s, key)
        if p is None or data is None:
            raise Orphan(key)
        self._fill(s, p, data, new=False)

    def _fill(self, s: Session, p: Part, data: dict, new: bool) -> None:
        tkey = " ".join(data["part_type"].lower().split())
        ptype = s.scalar(select(PartType).where(PartType.key == tkey))
        if ptype is None:
            ptype = PartType(key=tkey, name=data["part_type"])
            s.add(ptype)
            s.flush()
        brand = None
        if data["brand"]:
            brand = s.scalar(select(Brand).where(Brand.name == data["brand"]))
            if brand is None:
                brand = Brand(name=data["brand"], kind=data["brand_kind"])
                s.add(brand)
                s.flush()
        p.part_type_id, p.brand_id = ptype.id, brand.id if brand else None
        p.description, p.part_number = data["description"], data["part_number"] or None
        p.quantity, p.kind, p.segment, p.generic = data["quantity"], data["kind"], data["segment"], data["generic"]
        if new:
            s.add(p)
        s.flush()

    def name(self, key, data, base):
        return f"part {(data or base or {}).get('description', key)}"


# ---------------------------------------------------------------- prices


class PriceData(Schema):
    price_inr: int = Field(ge=0, le=10_000_000)
    price_max_inr: int | None = Field(None, ge=0, le=10_000_000)
    supplier: Source = ""
    source_url: Source = ""
    checked_on: date
    verification_status: PartVerification = PartVerification.approx
    gst_included: bool | None = None
    fitting_included: bool | None = None
    model_verified: bool = False
    price_basis: Annotated[str, Field(max_length=200)] = ""
    note: Annotated[str, Field(max_length=1000)] = ""
    entered_by: str | None = None
    second_look_by: str | None = None
    second_look_at: str | None = None

    _check_date = field_validator("checked_on")(_not_future)

    @model_validator(mode="after")
    def source_and_range(self):
        if not (self.supplier.strip() or self.source_url.strip()):
            raise ValueError("a price needs its source: the supplier or a link")
        if self.price_max_inr is not None and self.price_max_inr < self.price_inr:
            raise ValueError("the highest price is below the lowest")
        return self


def price_key(part_key: str, segment: str, tag: str) -> str:
    return f"{part_key}|{segment}|{tag}"


def needs_second_look(data: dict | None) -> bool:
    return (
        bool(data)
        and max(data["price_inr"], data.get("price_max_inr") or 0) >= SECOND_LOOK_INR
        and not data.get("second_look_by")
    )


class PriceHandler(Handler):
    """A part's price for a segment. Key: <part key>|<segment>|<source ref> (an imported row) or |editor-<n>."""

    entity, label, schema = "part_price", "Part prices", PriceData
    can_create = can_delete = True
    stage = "parts"

    @staticmethod
    def _split(key: str) -> tuple[str, str, str]:
        part_key, segment, tag = key.rsplit("|", 2)
        if segment not in {s.value for s in PriceSegment}:
            raise Invalid(f"unknown segment {segment}")
        return part_key, segment, tag

    def _row(self, s, version, key) -> PartPrice | None:
        part_key, segment, tag = self._split(key)
        p = _part(s, part_key)
        if p is None:
            return None
        return s.scalar(
            select(PartPrice)
            .where(
                PartPrice.dataset_version_id == version.id,
                PartPrice.part_id == p.id,
                PartPrice.segment == segment,
                PartPrice.source_ref == tag,
            )
            .order_by(PartPrice.id)
            .limit(1)
        )

    def snapshot(self, s, version, key):
        r = self._row(s, version, key)
        if r is None:
            return None
        return {
            "price_inr": r.price_inr,
            "price_max_inr": r.price_max_inr,
            "supplier": r.supplier or "",
            "source_url": r.source_url or "",
            "checked_on": _iso(r.checked_on),
            "verification_status": str(r.verification_status),
            "gst_included": r.gst_included,
            "fitting_included": r.fitting_included,
            "model_verified": r.model_verified,
            "price_basis": r.price_basis or "",
            "note": r.note or "",
            "entered_by": None,
            "second_look_by": r.second_look_by,
            "second_look_at": _iso(r.second_look_at),
        }

    def write(self, s, version, key, data):
        part_key, segment, tag = self._split(key)
        r = self._row(s, version, key)
        if data is None:
            if r is None:
                raise Orphan(key)
            s.delete(r)
            s.flush()
            return
        p = _part(s, part_key)
        if p is None:
            raise Orphan(key)
        if r is None:
            r = PartPrice(
                dataset_version_id=version.id,
                part_id=p.id,
                segment=segment,
                source=CatalogueSource.team_csv,
                source_ref=tag,
            )
            s.add(r)
        r.price_inr, r.price_max_inr = data["price_inr"], data["price_max_inr"]
        r.supplier, r.source_url = data["supplier"] or None, data["source_url"] or None
        r.checked_on = date.fromisoformat(data["checked_on"])
        r.verification_status, r.model_verified = data["verification_status"], data["model_verified"]
        r.gst_included, r.fitting_included = data["gst_included"], data["fitting_included"]
        r.price_basis, r.note = data["price_basis"] or None, data["note"] or None
        r.second_look_by, r.second_look_at = data["second_look_by"], _dt(data["second_look_at"])
        s.flush()

    def name(self, key, data, base):
        part_key, segment, tag = key.rsplit("|", 2)
        d = data or base or {}
        return f"price {part_key} ({segment}) {d.get('price_inr', '')}"


# ---------------------------------------------------------------- fits


class FitData(Schema):
    model_id: int
    year_from: int | None = Field(None, ge=1980, le=2100)
    year_to: int | None = Field(None, ge=1980, le=2100)
    fuel: Fuel | None = None
    transmission: Transmission | None = None
    verification_status: FitStatus = FitStatus.listed
    fit_text: Annotated[str, Field(min_length=2, max_length=300)]
    source_url: Source = ""

    @model_validator(mode="after")
    def years(self):
        if self.year_from and self.year_to and self.year_to < self.year_from:
            raise ValueError("the last year is before the first")
        return self


def fit_key(part_key: str, d: dict) -> str:
    return "|".join(
        [part_key, str(d["model_id"]), *(str(d.get(k) or "") for k in ("year_from", "year_to", "fuel", "transmission"))]
    )


class FitHandler(Handler):
    """A part fits a model (optionally years, fuel, gearbox).
    Key: <part key>|<model id>|<from>|<to>|<fuel>|<gearbox>."""

    entity, label, schema = "part_fit", "Part fits (compatibility)", FitData
    can_create = can_delete = True
    stage = "parts"

    def _row(self, s, version, key) -> PartCompatibility | None:
        part_key, model_id, y0, y1, fuel, gear = key.rsplit("|", 5)
        p = _part(s, part_key)
        if p is None:
            return None

        def same(column, value, cast=str):
            return column == cast(value) if value else column.is_(None)

        q = select(PartCompatibility).where(
            PartCompatibility.dataset_version_id == version.id,
            PartCompatibility.part_id == p.id,
            PartCompatibility.model_id == int(model_id),
            same(PartCompatibility.year_from, y0, int),
            same(PartCompatibility.year_to, y1, int),
            same(PartCompatibility.fuel, fuel),
            same(PartCompatibility.transmission, gear),
        )
        return s.scalar(q.order_by(PartCompatibility.id).limit(1))

    def snapshot(self, s, version, key):
        r = self._row(s, version, key)
        if r is None:
            return None
        return {
            "model_id": r.model_id,
            "year_from": r.year_from,
            "year_to": r.year_to,
            "fuel": str(r.fuel) if r.fuel else None,
            "transmission": str(r.transmission) if r.transmission else None,
            "verification_status": str(r.verification_status),
            "fit_text": r.fit_text,
            "source_url": r.source_url or "",
        }

    def write(self, s, version, key, data):
        r = self._row(s, version, key)
        if data is None:
            if r is None:
                raise Orphan(key)
            s.delete(r)
            s.flush()
            return
        p = _part(s, key.rsplit("|", 5)[0])
        if p is None:
            raise Orphan(key)
        if r is None:
            r = PartCompatibility(
                dataset_version_id=version.id, part_id=p.id, source=CatalogueSource.team_csv, source_ref="admin editor"
            )
            s.add(r)
        r.model_id, r.year_from, r.year_to = data["model_id"], data["year_from"], data["year_to"]
        r.fuel, r.transmission = data["fuel"], data["transmission"]
        r.verification_status, r.fit_text = data["verification_status"], data["fit_text"]
        r.source_url = data["source_url"] or None
        s.flush()

    def name(self, key, data, base):
        return f"fit {key.rsplit('|', 5)[0]} -> {(data or base or {}).get('fit_text', '')}"


# ---------------------------------------------------------------- labour


class LabourData(Schema):
    amount_inr: int = Field(gt=0, le=1_000_000)
    workshop_type: Annotated[str, Field(max_length=120)] = ""
    basis: Annotated[str, Field(min_length=3, max_length=500)]  # the source: who quoted it, where
    status: Literal["approx", "listed"] = "approx"
    checked_on: date

    _check_date = field_validator("checked_on")(_not_future)


class LabourHandler(Handler):
    """Labour for one repair, segment and city (research rows). Key: <repair>|<segment>|<city>."""

    entity, label, schema = "labour_rate", "Labour rates", LabourData
    can_create = can_delete = True
    stage = "parts"

    def _row(self, s, version, key) -> LabourRate | None:
        repair, segment, city = key.rsplit("|", 2)
        return s.scalar(
            select(LabourRate)
            .where(
                LabourRate.dataset_version_id == version.id,
                LabourRate.repair == repair,
                LabourRate.segment == segment,
                LabourRate.city == city,
            )
            .order_by(LabourRate.id)
            .limit(1)
        )

    def snapshot(self, s, version, key):
        r = self._row(s, version, key)
        if r is None:
            return None
        return {
            "amount_inr": r.amount_inr,
            "workshop_type": r.workshop_type or "",
            "basis": r.basis or "",
            "status": r.status if r.status in ("approx", "listed") else "approx",
            "checked_on": _iso(r.checked_on),
        }

    def write(self, s, version, key, data):
        repair, segment, city = key.rsplit("|", 2)
        r = self._row(s, version, key)
        if data is None:
            if r is None:
                raise Orphan(key)
            s.delete(r)
            s.flush()
            return
        if r is None:
            r = LabourRate(
                dataset_version_id=version.id,
                source=CatalogueSource.team_csv,
                source_ref="admin editor",
                source_file_no=0,
                repair=repair,
                segment=segment,
                city=city,
            )
            s.add(r)
        r.amount_inr, r.workshop_type, r.basis = data["amount_inr"], data["workshop_type"] or None, data["basis"]
        r.status, r.checked_on = data["status"], date.fromisoformat(data["checked_on"])
        s.flush()

    def name(self, key, data, base):
        return f"labour {key.replace('|', ' / ')}"


class ZoneRateData(Schema):
    rate_min_inr: int = Field(gt=0, le=100_000)
    rate_max_inr: int = Field(gt=0, le=100_000)
    source: Annotated[str, Field(min_length=3, max_length=500)]
    checked_on: date

    _check_date = field_validator("checked_on")(_not_future)

    @model_validator(mode="after")
    def range_order(self):
        if self.rate_max_inr < self.rate_min_inr:
            raise ValueError("the highest rate is below the lowest")
        return self


class ZoneRateHandler(Handler):
    """Mechanic labour per hour for a Delhi NCR zone and price segment. Key: <zone>|<segment>."""

    entity, label, schema = "zone_rate", "Zone labour rates", ZoneRateData
    can_create = can_delete = True
    stage = "parts"

    def _row(self, s, version, key) -> ZoneLabourRate | None:
        zone, segment = key.split("|")
        return s.scalar(
            select(ZoneLabourRate).where(
                ZoneLabourRate.dataset_version_id == version.id,
                ZoneLabourRate.zone == zone,
                ZoneLabourRate.segment == segment,
            )
        )

    def check(self, s, version, key, data):
        from app.estimates.zones import zones

        zone, _, segment = key.partition("|")
        if zone not in zones() or segment not in {x.value for x in PriceSegment}:
            raise Invalid(f"unknown zone or segment {key}")

    def snapshot(self, s, version, key):
        r = self._row(s, version, key)
        if r is None:
            return None
        return {
            "rate_min_inr": r.rate_min_inr,
            "rate_max_inr": r.rate_max_inr,
            "source": r.source,
            "checked_on": _iso(r.checked_on),
        }

    def write(self, s, version, key, data):
        zone, segment = key.split("|")
        r = self._row(s, version, key)
        if data is None:
            if r is not None:
                s.delete(r)
                s.flush()
            return
        if r is None:
            r = ZoneLabourRate(dataset_version_id=version.id, zone=zone, segment=segment)
            s.add(r)
        r.rate_min_inr, r.rate_max_inr = data["rate_min_inr"], data["rate_max_inr"]
        r.source, r.checked_on = data["source"], date.fromisoformat(data["checked_on"])
        s.flush()

    def name(self, key, data, base):
        return f"zone labour rate {key.replace('|', ' / ')}"


def load_zone_rates(s: Session, version: DatasetVersion) -> int:
    """The pipeline step: data/catalogue/zone_labour_rates.yaml into the version's rows (rates with a source and a
    date only). Editor edits are applied after it."""
    from app.estimates.zones import zone_rates

    zone_rates.cache_clear()  # the file may have changed since the worker started
    s.execute(delete(ZoneLabourRate).where(ZoneLabourRate.dataset_version_id == version.id))
    rates = zone_rates()
    for (zone, segment), r in rates.items():
        s.add(
            ZoneLabourRate(
                dataset_version_id=version.id,
                zone=zone,
                segment=segment,
                rate_min_inr=r.rate.low,
                rate_max_inr=r.rate.high,
                source=r.source,
                checked_on=r.checked_on,
            )
        )
    s.flush()
    return len(rates)


# ---------------------------------------------------------------- part pictures


class PartImagesData(Schema):
    images: list[Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]] = Field(default_factory=list, max_length=12)


class PartImagesHandler(Handler):
    """A part's pictures (by SHA-1). part_images is shared and rebuilt by `parts build`: re-applied after it."""

    entity, label, schema = "part_images", "Part pictures", PartImagesData
    stage = "parts"

    def snapshot(self, s, version, key):
        p = _part(s, key)
        if p is None:
            pending = _pending(s, version, "part", key)
            return {"images": []} if pending else None
        rows = s.scalars(
            select(Image.sha1).join(PartImage, PartImage.image_id == Image.id).where(PartImage.part_id == p.id)
        )
        return {"images": sorted(rows)}

    def write(self, s, version, key, data):
        p = _part(s, key)
        if p is None:
            raise Orphan(key)
        wanted = (data or {}).get("images", [])
        images = {i.sha1: i for i in s.scalars(select(Image).where(Image.sha1.in_(wanted)))}
        if missing := [x for x in wanted if x not in images]:
            raise Invalid(f"unknown pictures {missing}")
        s.execute(delete(PartImage).where(PartImage.part_id == p.id))
        for sha in wanted:
            s.add(PartImage(part_id=p.id, image_id=images[sha].id, source="upload"))
        s.flush()

    def name(self, key, data, base):
        return f"pictures of part {key}"


PARTS_HANDLERS = (PartHandler(), PriceHandler(), FitHandler(), LabourHandler(), ZoneRateHandler(), PartImagesHandler())


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
