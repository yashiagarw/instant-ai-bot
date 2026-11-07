"""Read the parts catalogue for the customer API.

A part is shown as fitting the car only when a part_compatibility row of the current dataset version names the car's
model and its years / fuel / gearbox match the variant (app.parts.fit.fit_for_variant). Everything else is a segment
part with fit "not_verified". Only approved fault links are read.
"""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.enums import CoverageLevel, PriceSegment, ReviewStatus
from app.knowledge.models import DatasetVersion, Fault, FaultLink, LinkRelation
from app.knowledge.questions.inputs import target_version
from app.parts import schemas as S
from app.parts.fit import VariantFacts, fit_for_variant
from app.parts.models import FaultPart, FitStatus, Part, PartCompatibility, PartImage, PartPrice
from app.vehicles.models import Make, Model, Variant

APPROX_LABELS = {
    "checked": "Price checked online",
    "listed_recheck": "Listed price, check again",
    "approx": "Approx price, ask the shop",
}
FIT_LABELS = {
    "listed": "Listed for your car",
    "confirm_fit": "Listed for your model: confirm by chassis number (VIN) or variant",
    "not_verified": "Fit not verified for your car",
}
FIT_ORDER = {"listed": 0, "confirm_fit": 1, "not_verified": 2}
MAX_COMPARE = 6


class NotFound(LookupError):
    pass


@dataclass
class Car:
    variant: Variant
    facts: VariantFacts
    out: S.VehicleOut


def car(session: Session, variant_id: int | None) -> Car | None:
    if variant_id is None:
        return None
    v = session.get(Variant, variant_id)
    if v is None:
        raise NotFound("Variant not found")
    model = session.get(Model, v.model_id)
    make = session.get(Make, model.make_id)
    return Car(
        v,
        VariantFacts(v.model_id, v.year_from, v.year_to, str(v.fuel), str(v.transmission)),
        S.VehicleOut(
            variant_id=v.id,
            name=f"{make.name} {model.name} {v.name}",
            fuel=v.fuel,
            transmission=v.transmission,
            price_segment=v.price_segment,
        ),
    )


def canonical_fault(session: Session, version: DatasetVersion, key: str) -> Fault:
    fault = session.scalar(select(Fault).where(Fault.dataset_version_id == version.id, Fault.fault_key == key))
    if fault is None:
        raise NotFound("Fault not found")
    target = session.scalar(
        select(FaultLink.to_fault_id).where(
            FaultLink.from_fault_id == fault.id, FaultLink.relation == LinkRelation.merged_into
        )
    )
    return session.get(Fault, target) if target else fault


def _compat(session: Session, version: DatasetVersion, part_ids: list[int]) -> dict[int, list[tuple]]:
    rows = session.execute(
        select(PartCompatibility, Model.name, Make.name)
        .join(Model, Model.id == PartCompatibility.model_id)
        .join(Make, Make.id == Model.make_id)
        .where(PartCompatibility.part_id.in_(part_ids), PartCompatibility.dataset_version_id == version.id)
        .order_by(PartCompatibility.id)
    ).all()
    out: dict[int, list[tuple]] = defaultdict(list)
    for c, model, make in rows:
        out[c.part_id].append((c, make, model))
    return out


def _prices(session: Session, version: DatasetVersion, part_ids: list[int]) -> dict[int, list[PartPrice]]:
    out: dict[int, list[PartPrice]] = defaultdict(list)
    q = (
        select(PartPrice)
        .where(PartPrice.part_id.in_(part_ids), PartPrice.dataset_version_id == version.id)
        .order_by(PartPrice.segment, PartPrice.price_inr)
    )
    for p in session.scalars(q):
        out[p.part_id].append(p)
    return out


def fit_status(compat: list[tuple], vehicle: Car | None) -> str:
    """listed / confirm_fit only through a compatibility record that matches the variant; otherwise not_verified."""
    if vehicle is None:
        return "not_verified"
    best = "not_verified"
    for c, _, _ in compat:
        status = fit_for_variant(
            c.model_id, c.year_from, c.year_to, c.fuel, c.transmission, c.verification_status, vehicle.facts
        )
        if status is not None and c.variant_id not in (None, vehicle.variant.id):
            status = None
        if status is not None and FIT_ORDER[str(status)] < FIT_ORDER[best]:
            best = str(status)
    return best


def _listed_for(compat: list[tuple]) -> list[str]:
    out = []
    for c, make, model in compat:
        years = ""
        if c.year_from or c.year_to:
            years = f" {c.year_from or ''}-{c.year_to or ''}" if c.year_to != c.year_from else f" {c.year_from}"
        text = f"{make} {model}{years}" + (f" {c.fuel}" if c.fuel else "")
        if text not in out:
            out.append(text)
    return out


def _price_out(p: PartPrice) -> S.PriceOut:
    return S.PriceOut(
        segment=p.segment,
        price_inr=p.price_inr,
        price_max_inr=p.price_max_inr,
        approx_label=APPROX_LABELS[str(p.verification_status)],
        verification=str(p.verification_status),
        checked_on=p.checked_on,
        model_verified=p.model_verified,
        price_basis=p.price_basis,
        gst_text=p.gst_text,
        gst_included=p.gst_included,
        fitting_included=p.fitting_included,
        supplier=p.supplier,
        source_url=p.source_url,
        note=p.note,
    )


def _part_out(part: Part, fit: str, compat: list[tuple], prices: list[PartPrice], in_total=None) -> dict:
    return {
        "id": part.id,
        "name": part.description,
        "part_type": part.part_type.name,
        "brand": S.BrandOut(name=part.brand.name, kind=part.brand.kind) if part.brand else None,
        "part_number": part.part_number,
        "quantity": part.quantity,
        "generic": part.generic,
        "fit": S.FitOut(status=fit, label=FIT_LABELS[fit]),
        "listed_for": _listed_for(compat),
        "in_total": in_total,
        "prices": list(dict.fromkeys(_price_out(p) for p in prices)),  # same part priced in two files
        "images": [
            S.ImageOut(
                file=img.image.path.removeprefix("data/media/"),
                caption=img.image.caption,
                image_type=img.image.image_type,
            )
            for img in (part.images if get_settings().show_pictures else ())  # SHOW_PICTURES (the free demo: off)
        ],
    }


def _load_parts(session: Session, ids: list[int]) -> dict[int, Part]:
    q = (
        select(Part)
        .where(Part.id.in_(ids))
        .options(
            selectinload(Part.part_type),
            selectinload(Part.brand),
            selectinload(Part.images).selectinload(PartImage.image),
        )
    )
    return {p.id: p for p in session.scalars(q)}


def coverage(parts: list[S.PartOut], segment: PriceSegment | None) -> CoverageLevel:
    if any(p.fit.status == "listed" for p in parts):
        return CoverageLevel.part_fit_verified
    return CoverageLevel.segment_estimate if segment else CoverageLevel.general_guidance


def fault_parts(
    session: Session, key: str, variant_id: int | None, segment: PriceSegment | None, disclaimer: str
) -> S.FaultPartsOut:
    """Parts for a fault: those a compatibility record lists for the car first (any segment), then the parts of the
    car's segment marked "fit not verified". Without a car, every approved part of the segment (or of all segments)
    is "fit not verified"."""
    version = target_version(session)
    vehicle = car(session, variant_id)
    fault = canonical_fault(session, version, key)
    segment = vehicle.variant.price_segment if vehicle else segment
    links = session.scalars(
        select(FaultPart).where(FaultPart.fault_id == fault.id, FaultPart.status == ReviewStatus.approved)
    ).all()
    part_ids = sorted({link.part_id for link in links})
    parts, compat, prices = (
        _load_parts(session, part_ids),
        _compat(session, version, part_ids),
        _prices(session, version, part_ids),
    )
    fitting, segment_parts, seen = [], [], set()
    for link in sorted(links, key=lambda x: (x.in_total is False, x.id)):
        if link.part_id in seen:
            continue
        part = parts[link.part_id]
        fit = fit_status(compat[part.id], vehicle)
        if fit != "not_verified":
            seen.add(part.id)
            fitting.append(S.PartOut(**_part_out(part, fit, compat[part.id], prices[part.id], link.in_total)))
        elif segment is None or str(link.segment) == str(segment):
            seen.add(part.id)
            shown = [p for p in prices[part.id] if segment is None or str(p.segment) == str(segment)]
            segment_parts.append(S.PartOut(**_part_out(part, fit, compat[part.id], shown, link.in_total)))
    fitting.sort(key=lambda p: FIT_ORDER[p.fit.status])
    out = fitting + segment_parts
    return S.FaultPartsOut(
        fault_key=fault.fault_key,
        requested_key=key,
        fault_name=fault.name,
        vehicle=vehicle.out if vehicle else None,
        segment=segment,
        coverage_level=coverage(out, segment),
        parts=out,
        disclaimer=disclaimer,
    )


def part_details(session: Session, ids: list[int], variant_id: int | None) -> tuple[Car | None, list[S.PartDetailOut]]:
    version = target_version(session)
    vehicle = car(session, variant_id)
    parts = _load_parts(session, ids)
    if missing := [i for i in ids if i not in parts]:
        raise NotFound(f"Part not found: {', '.join(map(str, missing))}")
    compat, prices = _compat(session, version, ids), _prices(session, version, ids)
    faults: dict[int, list[S.FaultRefOut]] = defaultdict(list)
    q = (
        select(FaultPart.part_id, FaultPart.segment, Fault.fault_key, Fault.name)
        .join(Fault, Fault.id == FaultPart.fault_id)
        .where(
            FaultPart.part_id.in_(ids),
            FaultPart.status == ReviewStatus.approved,
            Fault.dataset_version_id == version.id,
        )
        .order_by(Fault.fault_key, FaultPart.segment)
    )
    for part_id, seg, fault_key, name in session.execute(q):
        faults[part_id].append(S.FaultRefOut(fault_key=fault_key, name=name, segment=seg))
    out = []
    for i in ids:
        part = parts[i]
        data = _part_out(part, fit_status(compat[i], vehicle), compat[i], prices[i])
        data["compatibility"] = [
            S.CompatibilityOut(
                make=make,
                model=model,
                year_from=c.year_from,
                year_to=c.year_to,
                fuel=c.fuel,
                transmission=c.transmission,
                status=FitStatus(c.verification_status).value,
            )
            for c, make, model in compat[i]
        ]
        data["faults"] = faults[i]
        out.append(S.PartDetailOut(**data))
    return vehicle, out
