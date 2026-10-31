"""Repair estimates from the database: the single source of the price a customer sees.

For each ranked fault and the car's price segment:

- Parts and consumables. The fault's needed part lines are the sheet's segment price list (lines "in total"; file 5:
  PRICE BREAKDOWN), matched to the approved catalogue (data/review/parts approvals, price sheets). A line whose part
  type has catalogue parts listed for the customer's car (part_compatibility) uses the min-max of those parts' current
  prices; otherwise the typical price for the segment ("fit not verified"). When the lines cannot all be priced from
  approved rows (copied totals in file 7, quotations in file 6, rows still under review), the parts amount comes from
  the sheet's own "Parts total", or the sheet total minus its labour, and says so.
- Labour. Hours (from the fault's repair time) x the zone's hourly rate when data/catalogue/zone_labour_rates.yaml has
  one for the zone and segment; otherwise the sheet's labour for the segment, labelled "Delhi NCR metro estimate".
  Service lines (wheel alignment, scans, towing) are added as labour.
- No estimate ("not enough data", with the reasons) when the segment, the labour or the part prices are missing.

The result page's cost field is built from these estimates (diagnosis API), so the two never disagree.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.enums import ReviewStatus
from app.estimates import maths as M
from app.estimates.zones import Zone, zone_for_pincode, zone_rates, zones
from app.knowledge.importer import parse as P
from app.knowledge.models import DatasetVersion, Fault, FaultCost, PriceBreakdownLine
from app.parts.fit import VariantFacts
from app.parts.models import FaultPart, FaultServiceCharge, Part, PartCompatibility, PartKind, PartPrice
from app.parts.segment_text import SegmentLine, line_kind, parse_segment
from app.parts.service import fit_status
from app.requests.models import ServiceRequest
from app.vehicles.models import Variant

METRO = "Delhi NCR metro estimate"
TIERS = {"budget": "Budget", "mid": "Mid-range", "premium": "Premium"}
SOURCE_OF_TRUTH = (
    "Prices come from this estimate service. The result page's cost uses the same numbers: sheet part prices and "
    "labour, replaced by catalogue prices for parts listed for your car and by zone labour rates where known."
)


class EstimateInputError(ValueError):
    pass


def today_in_india() -> date:
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


@dataclass
class ZoneChoice:
    zone: Zone | None
    source: str  # zone / pincode / service_request / none
    note: str


def resolve_zone(session: Session, session_id, zone_code: str | None, pincode: str | None) -> ZoneChoice:
    """zone= first, then pincode=, then the pincode of a service request made from this session, else none."""
    if zone_code:
        z = zones().get(zone_code.strip().lower())
        if z is None:
            raise EstimateInputError(f"unknown zone '{zone_code}'; choose one of: {', '.join(zones())}")
        return ZoneChoice(z, "zone", f"Zone chosen: {z.label}")
    if pincode:
        z = zone_for_pincode(pincode)
        if z is None:
            return ZoneChoice(None, "pincode", f"Pincode {pincode} is not in our Delhi NCR zones: using the {METRO}")
        return ZoneChoice(z, "pincode", f"Zone from pincode {pincode}: {z.label}")
    pin = session.scalar(
        select(ServiceRequest.pincode)
        .where(ServiceRequest.session_id == session_id, ServiceRequest.pincode != "")
        .order_by(ServiceRequest.created_at.desc())
    )
    if pin and (z := zone_for_pincode(pin)):
        return ZoneChoice(z, "service_request", f"Zone from the pincode on your service request: {z.label}")
    return ZoneChoice(None, "none", f"No zone chosen: using the {METRO}. Choose a zone or give a pincode.")


@dataclass
class FaultEstimate:
    fault_id: int
    fault_key: str
    fault_name: str
    segment: str | None
    status: str  # ok / not_enough_data
    reasons: list[str] = field(default_factory=list)
    inputs: list[M.Input] = field(default_factory=list)
    totals: M.Totals | None = None
    parts_basis: str = ""  # itemised / sheet_parts_total / sheet_total_minus_labour / none
    labour_basis: str = ""  # zone_rate / metro_estimate


@dataclass
class CarFacts:
    variant_id: int
    facts: VariantFacts


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _car(session: Session, variant_id: int | None) -> CarFacts | None:
    v = session.get(Variant, variant_id) if variant_id else None
    if v is None:
        return None
    return CarFacts(v.id, VariantFacts(v.model_id, v.year_from, v.year_to, str(v.fuel), str(v.transmission)))


def _needed_lines(session: Session, version: DatasetVersion, fault: Fault, cost: FaultCost) -> list[SegmentLine]:
    """Part and consumable lines in the segment's parts total (no "only if needed", cross-references or services)."""
    if fault.source_file_no == 5:
        rows = session.scalars(
            select(PriceBreakdownLine)
            .where(
                PriceBreakdownLine.dataset_version_id == version.id,
                PriceBreakdownLine.source_file_no == 5,
                PriceBreakdownLine.fault_source_id == fault.source_id,
                PriceBreakdownLine.tier == TIERS[str(cost.segment)],
                PriceBreakdownLine.type == "Parts",
            )
            .order_by(PriceBreakdownLine.id)
        ).all()
        lines = [SegmentLine(i, r.item, price_inr=r.amount_inr, kind=line_kind(r.item)) for i, r in enumerate(rows, 1)]
    else:
        lines = parse_segment(cost.parts_text, cost.part_prices_text)
    return [x for x in lines if x.in_total is not False and x.parse_status != "cross_reference" and x.kind != "service"]


@dataclass
class Candidate:
    part: Part
    prices: list[PartPrice]  # this segment
    compat: list[tuple]


def _match(line: SegmentLine, candidates: list[Candidate]) -> Candidate | None:
    number = (line.part_number or "").upper().replace(" ", "")
    for c in candidates:
        if number and c.part.part_number and c.part.part_number.upper().replace(" ", "") == number:
            return c
    name = _norm(line.part)
    return next((c for c in candidates if _norm(c.part.description) == name), None)


def _price_range(prices: list[PartPrice]) -> M.Range:
    return M.Range(min(p.price_inr for p in prices), max((p.price_max_inr or p.price_inr) for p in prices))


def _parts_inputs(
    session: Session,
    version: DatasetVersion,
    fault: Fault,
    cost: FaultCost,
    car: CarFacts | None,
    services: list[M.Input],
) -> tuple[list[M.Input], str, list[str]]:
    """(inputs, basis, problems). problems non-empty = no usable part prices. `services` are the fault's service
    charges, counted as labour: they are taken out of any sheet parts figure that already contains them."""
    segment = str(cost.segment)
    lines = _needed_lines(session, version, fault, cost)
    if not lines:
        return [], "itemised", []  # nothing in the parts total: no parts needed (or only "if needed" ones)
    links = session.scalars(
        select(FaultPart)
        .where(FaultPart.fault_id == fault.id, FaultPart.status == ReviewStatus.approved)
        .options(selectinload(FaultPart.part).selectinload(Part.part_type))
    ).all()
    part_ids = list({link.part_id for link in links})
    prices: dict[int, list[PartPrice]] = {}
    for p in session.scalars(
        select(PartPrice).where(PartPrice.part_id.in_(part_ids), PartPrice.dataset_version_id == version.id)
    ):
        prices.setdefault(p.part_id, []).append(p)
    compat: dict[int, list[tuple]] = {}
    for c in session.scalars(
        select(PartCompatibility).where(
            PartCompatibility.part_id.in_(part_ids), PartCompatibility.dataset_version_id == version.id
        )
    ):
        compat.setdefault(c.part_id, []).append((c, "", ""))
    seen, candidates, compatible = set(), [], []
    for link in links:
        if link.part_id in seen:
            continue
        seen.add(link.part_id)
        part = link.part
        if car is not None and fit_status(compat.get(part.id, []), car_for_fit(car)) != "not_verified":
            compatible.append(Candidate(part, prices.get(part.id, []), compat.get(part.id, [])))
    for link in links:
        if str(link.segment) == segment:
            seg_prices = [p for p in prices.get(link.part_id, []) if str(p.segment) == segment]
            candidates.append(Candidate(link.part, seg_prices, compat.get(link.part_id, [])))

    inputs, problems, car_specific = [], [], False
    for line in lines:
        if line.parse_status != "ok":
            problems.append(f"'{line.part[:60]}': {line.parse_status.replace('_', ' ')}")
            continue
        c = _match(line, candidates)
        if c is None or not c.prices or line.price_inr is None:
            problems.append(f"'{line.part[:60]}': no approved price yet")
            continue
        kind = "consumable" if c.part.kind == PartKind.consumable else "part"
        options = [x for x in compatible if x.part.part_type_id == c.part.part_type_id and x.prices]
        if options:
            car_specific = True
            all_prices = [p for x in options for p in x.prices]
            listed = all(fit_status(x.compat, car_for_fit(car)) == "listed" for x in options)
            inputs.append(
                M.Input(
                    kind,
                    c.part.part_type.name,
                    _price_range(all_prices),
                    "; ".join(sorted({p.source_ref for p in all_prices})),
                    max((p.checked_on for p in all_prices if p.checked_on), default=None),
                    verified=listed and all(str(p.verification_status) == "checked" for p in all_prices),
                    note=f"{len(options)} part(s) listed for your car",
                )
            )
        else:
            # The fault's own line price (a generic part is shared by faults with different prices).
            own = [p for p in c.prices if p.price_inr == line.price_inr] or c.prices
            inputs.append(
                M.Input(
                    kind,
                    c.part.description,
                    M.Range(line.price_inr, max(line.price_max_inr or line.price_inr, line.price_inr)),
                    "; ".join(sorted({p.source_ref for p in own})),
                    max((p.checked_on for p in own if p.checked_on), default=None),
                    verified=False,
                    note=f"Typical price for a {segment} car; fit not verified",
                )
            )
    sheet = _sheet_parts(cost, services)
    if problems:
        # Some lines cannot be priced from approved rows: the sheet's own parts figure for the whole list.
        note = "Part prices not itemised: " + "; ".join(problems[:3]) + (" ..." if len(problems) > 3 else "")
        if sheet is None:
            return [], "none", problems
        basis, amount = sheet
        return [_sheet_parts_input(fault, segment, basis, amount, cost, note)], basis, []
    if not car_specific and sheet is not None:
        basis, amount = sheet
        listed = M.Range(sum(i.amount.low for i in inputs), sum(i.amount.high for i in inputs))
        if abs(listed.low - amount.low) > M.ROUND_TO or abs(listed.high - amount.high) > M.ROUND_TO:
            # The sheet's line prices do not add up to its own parts figure: the sheet figure is what customers
            # were shown, and nothing car-specific replaces it.
            note = (
                f"The part lines add up to Rs {listed.low:,}-{listed.high:,}, the sheet's parts figure is "
                f"Rs {amount.low:,}-{amount.high:,}: the sheet figure is used"
            )
            return [_sheet_parts_input(fault, segment, basis, amount, cost, note)], basis, []
    return inputs, "itemised", []


def _sheet_parts(cost: FaultCost, services: list[M.Input]) -> tuple[str, M.Range] | None:
    """The sheet's own parts figure, without the service lines it contains (they are counted as labour): its
    "Parts total" less the services listed "in total" (files 8-18), else its total minus its labour and services."""
    by_name = {_norm(i.name): i.amount for i in services}
    stated = P.parts_total(cost.part_prices_text or "")
    if stated is not None:
        inside = [
            by_name[_norm(x.part)]
            for x in parse_segment(cost.parts_text, cost.part_prices_text)
            if x.kind == "service" and x.in_total is True and _norm(x.part) in by_name
        ]
        low, high = stated - sum(r.high for r in inside), stated - sum(r.low for r in inside)
        return ("sheet_parts_total", M.Range(low, high)) if 0 <= low <= high else None
    total, labour = _sheet_total(cost), _sheet_labour(cost)
    if total is None or labour is None:
        return None
    svc = sum((i.amount for i in services), M.Range.zero())
    low, high = total.low - labour.low - svc.low, total.high - labour.high - svc.high
    return ("sheet_total_minus_labour", M.Range(low, high)) if 0 <= low <= high else None


def _sheet_parts_input(fault: Fault, segment: str, basis: str, amount: M.Range, cost: FaultCost, note: str) -> M.Input:
    name = "Parts (sheet parts total)" if basis == "sheet_parts_total" else "Parts (sheet total minus labour)"
    what = "parts total" if basis == "sheet_parts_total" else "total minus labour"
    return M.Input("part", name, amount, _sheet_ref(fault, segment, what), cost.checked_on, verified=False, note=note)


def car_for_fit(car: CarFacts):
    """The shape app.parts.service.fit_status expects (variant id + facts)."""
    return _FitCar(_FitVariant(car.variant_id), car.facts)


@dataclass
class _FitVariant:
    id: int


@dataclass
class _FitCar:
    variant: _FitVariant
    facts: VariantFacts


def _sheet_ref(fault: Fault, segment: str, what: str) -> str:
    return f"{fault.fault_key} sheet {what} ({segment})"


def _sheet_total(cost: FaultCost) -> M.Range | None:
    if cost.needs_review:
        return None
    if cost.total_inr is not None:
        return M.Range(cost.total_inr, cost.total_inr)
    if cost.total_min_inr is not None and cost.total_max_inr is not None:
        return M.Range(cost.total_min_inr, cost.total_max_inr)
    return None


def _sheet_labour(cost: FaultCost) -> M.Range | None:
    if cost.needs_review:
        return None
    if cost.labour_inr is not None:
        return M.Range(cost.labour_inr, cost.labour_inr)
    return M.price_range(cost.labour_text)


def _labour_inputs(fault: Fault, cost: FaultCost, zone: Zone | None) -> tuple[list[M.Input], str, str]:
    """(inputs, basis, note). Empty inputs = no labour data."""
    segment = str(cost.segment)
    rate = zone_rates().get((zone.code, segment)) if zone else None
    hours = M.parse_hours(fault.repair_time_text)
    note = ""
    if rate and hours:
        h = f"{hours[0]:g}-{hours[1]:g} h" if hours[0] != hours[1] else f"{hours[0]:g} h"
        r = f"Rs {rate.rate.low}-{rate.rate.high}/h" if rate.rate.low != rate.rate.high else f"Rs {rate.rate.low}/h"
        return (
            [
                M.Input(
                    "labour",
                    f"Labour ({h} x {r}, {zone.label})",
                    M.labour_from_rate(hours, rate.rate),
                    f"zone_labour_rates.yaml: {rate.source}",
                    rate.checked_on,
                    verified=True,
                )
            ],
            "zone_rate",
            "",
        )
    if rate and not hours:
        note = f"{zone.label} has a labour rate, but this fault's repair time could not be read: {METRO} used"
    sheet = _sheet_labour(cost)
    if sheet is None:
        return [], "none", note
    return (
        [
            M.Input(
                "labour",
                f"Labour ({METRO})",
                sheet,
                _sheet_ref(fault, segment, "labour"),
                P.parse_date(cost.labour_text),  # labour has a date only when its own cell gives one
                verified=False,
                note=note,
            )
        ],
        "metro_estimate",
        note,
    )


def _service_inputs(
    session: Session, version: DatasetVersion, fault: Fault, segment: str, cost: FaultCost
) -> list[M.Input]:
    """Service charges in this fault's price list for the segment: a service the list marks "only if needed", or does
    not list at all (a price-sheet row shared with other faults), is not added."""
    listed = {
        _norm(x.part): x.in_total
        for x in parse_segment(cost.parts_text, cost.part_prices_text)
        if x.kind == "service" and x.parse_status == "ok"
    }
    rows = session.scalars(
        select(FaultServiceCharge)
        .where(
            FaultServiceCharge.fault_id == fault.id,
            FaultServiceCharge.segment == segment,
            FaultServiceCharge.dataset_version_id == version.id,
        )
        .order_by(FaultServiceCharge.id)
    ).all()
    out, seen = [], set()
    for r in rows:
        if r.name.lower() in seen or listed.get(_norm(r.name), False) is False:  # repeated, only if needed, unlisted
            continue
        seen.add(r.name.lower())
        out.append(
            M.Input(
                "service",
                r.name,
                M.Range(r.amount_inr, r.amount_max_inr or r.amount_inr),
                r.source_ref,
                r.checked_on,
                verified=str(r.verification_status) == "checked",
                note="Service charge (labour)",
            )
        )
    return out


def estimate_fault(
    session: Session,
    version: DatasetVersion,
    fault: Fault,
    segment: str | None,
    car: CarFacts | None,
    zone: Zone | None,
    today: date,
) -> FaultEstimate:
    est = FaultEstimate(fault.id, fault.fault_key, fault.name, segment, "not_enough_data")
    if segment is None:
        est.reasons.append("The car's price segment is not known")
        return est
    cost = session.get(FaultCost, (fault.id, segment))
    if cost is None:
        est.reasons.append(f"No price data for a {segment} car")
        return est
    labour, est.labour_basis, _ = _labour_inputs(fault, cost, zone)
    if not labour:
        est.reasons.append("No labour figure for this repair")
    services = _service_inputs(session, version, fault, segment, cost)
    parts, est.parts_basis, problems = _parts_inputs(session, version, fault, cost, car, services)
    if problems:
        est.reasons.append("Part prices are missing or not usable: " + "; ".join(problems[:5]))
    if est.reasons:
        return est
    est.inputs = parts + labour + services
    est.totals = M.combine(est.inputs, today)
    est.status = "ok"
    return est


def estimate_faults(
    session: Session,
    version: DatasetVersion,
    fault_ids: list[int],
    snapshot: dict,
    zone: Zone | None,
    today: date | None = None,
) -> list[FaultEstimate]:
    today = today or today_in_india()
    car = _car(session, snapshot.get("variant_id"))
    segment = snapshot.get("segment")
    faults = {f.id: f for f in session.scalars(select(Fault).where(Fault.id.in_(fault_ids)))}
    return [estimate_fault(session, version, faults[i], segment, car, zone, today) for i in fault_ids if i in faults]


def cost_out(est: FaultEstimate) -> dict | None:
    """The result page's cost (diagnosis CostOut fields) from an estimate: one source of truth."""
    if est.segment is None:
        return None
    if est.status != "ok":
        return {"segment": est.segment, "display": "on_inspection", "text": "Price on inspection"}
    t = est.totals
    single = t.total.low == t.total.high
    labour = t.labour
    return {
        "segment": est.segment,
        "display": "amount" if single else "range",
        "amount": t.total.low if single else None,
        "min": None if single else t.total.low,
        "max": None if single else t.total.high,
        "approx_label": "approx - estimate, check with the workshop" if t.flags.needs_check else None,
        "checked_on": t.last_updated.isoformat() if t.last_updated else None,
        "is_approx": t.flags.needs_check,
        "labour": labour.low if labour.low == labour.high else None,
        "labour_text": None if labour.low == labour.high else f"₹{labour.low:,}–₹{labour.high:,}",
    }
