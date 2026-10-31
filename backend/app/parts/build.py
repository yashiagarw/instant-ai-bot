"""Build the parts catalogue for the target dataset version from:

1. the imported PARTS_PRICE_SOURCES rows (files 9, 12, 14, 18): parts, brands, prices, vehicle fit, pictures and
   fault links ("Fault IDs using it"; file 9's drafted links count once approved in
   data/review/parts/F09-fault-links.csv),
2. CSVs the team fills from data/schema/templates (data/catalogue/parts/F07-part_price_sources.csv,
   F07-labour_rates.csv, ...), read exactly like the sheets,
3. approved rows of the segment-parts review files (data/review/parts/F01.csv, ...): segment prices, never
   model-verified,
4. the imported LABOUR_PRICE_RESEARCH / LABOUR_AND_RECOVERY_RESEARCH rows: one labour rate per segment and city.

Fault links go to the canonical fault when the source fault was merged (data/review/merges.yaml), so run this after
`python -m app.knowledge.merges apply`. Safe to re-run: the version's prices, fits, links and labour are replaced;
parts keep their ids.
"""

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.enums import PriceSegment, ReviewStatus
from app.knowledge.importer import parse as P
from app.knowledge.importer.loader import col, ids_in, num, part_verification, segment_of
from app.knowledge.models import (
    DatasetVersion,
    Fault,
    FaultLink,
    Image,
    LabourRateResearch,
    LinkRelation,
    PartPriceSource,
    PartPriceSourceFault,
)
from app.parts import fit as F
from app.parts.models import (
    Brand,
    BrandKind,
    CatalogueSource,
    FaultPart,
    FaultPartSource,
    FaultServiceCharge,
    LabourRate,
    Part,
    PartCompatibility,
    PartImage,
    PartImageSource,
    PartKind,
    PartPrice,
    PartType,
)
from app.parts.segment_text import line_kind, part_type_name
from app.vehicles.models import Make, Model, Variant

REPO_ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = REPO_ROOT / "data" / "review" / "parts"
TEAM_DIR = REPO_ROOT / "data" / "catalogue" / "parts"

NO_NUMBER = re.compile(r"^(model specific|-+|–|n/?a|none|not stated)?$", re.I)
NO_BRAND = re.compile(r"^(any good brand|market price|authorised hsrp maker)", re.I)
BRAND_NOTE = re.compile(r"\s*\([^)]*\)")  # "(Mobis)", "(via Motrparts)", "(aftermarket)"
APPROVED = {"yes", "y", "true", "1", "approved"}
REJECTED = {"no", "n", "false", "0", "rejected"}
SEGMENTS = {s.value for s in PriceSegment}


@dataclass
class FileStats:
    file_no: int
    price_rows: int = 0
    team_rows: int = 0
    no_price: int = 0
    parts: set[int] = field(default_factory=set)
    specific: set[int] = field(default_factory=set)
    brands: set[int] = field(default_factory=set)
    prices: int = 0
    fits: int = 0
    fits_generic: int = 0
    fits_no_model: int = 0
    fits_out_of_catalogue: int = 0
    links: dict[str, int] = field(default_factory=lambda: defaultdict(int))  # status -> count
    images: int = 0
    labour: int = 0
    labour_not_applicable: int = 0
    segment_rows: int = 0
    segment_approved: int = 0
    services: int = 0
    excluded: dict[str, int] = field(default_factory=lambda: defaultdict(int))  # parse status -> approved rows skipped

    def row(self) -> dict:
        return {
            "file": self.file_no,
            "price rows (sheet / csv)": f"{self.price_rows} / {self.team_rows}",
            "parts (model-specific)": f"{len(self.parts)} ({len(self.specific)})",
            "brands": len(self.brands),
            "prices": self.prices,
            "fit records": self.fits,
            "fit: generic / no model / outside catalogue": (
                f"{self.fits_generic} / {self.fits_no_model} / {self.fits_out_of_catalogue}"
            ),
            "fault links approved / draft / rejected": "{} / {} / {}".format(
                self.links["approved"], self.links["draft"], self.links["rejected"]
            ),
            "pictures": self.images,
            "labour rates (n/a skipped)": f"{self.labour} ({self.labour_not_applicable})",
            "segment rows approved / total": f"{self.segment_approved} / {self.segment_rows}",
            "service charges (labour)": self.services,
            "excluded (not loaded)": ", ".join(f"{k} {v}" for k, v in sorted(self.excluded.items())) or "0",
        }


@dataclass
class SourceRow:
    """One price row, from a sheet or a team CSV, in the PARTS_PRICE_SOURCES shape."""

    file_no: int
    source: CatalogueSource
    source_ref: str
    segment: str
    part: str
    brand: str = ""
    oem_text: str = ""
    part_number: str = ""
    price_inr: int | None = None
    price_basis: str | None = None
    supplier: str | None = None
    source_url: str | None = None
    checked_on: date | None = None
    gst_text: str | None = None
    fitting_text: str | None = None
    verification: str = "approx"
    picture_code: str | None = None
    note: str | None = None
    fit_text: str = ""
    links: list[tuple[int, str, str]] = field(default_factory=list)  # (fault id, link source, status)


@dataclass
class BuildResult:
    version_id: int
    files: dict[int, FileStats]
    unmatched_fits: list[dict]
    unmatched_path: Path | None = None


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def decision(value: str) -> ReviewStatus:
    v = (value or "").strip().lower()
    return ReviewStatus.approved if v in APPROVED else ReviewStatus.rejected if v in REJECTED else ReviewStatus.draft


def brand_kind(oem_text: str) -> BrandKind:
    t = (oem_text or "").lower()
    if "oe supplier" in t or t.startswith("oes"):
        return BrandKind.oes
    if " or " in t:  # "Genuine or good aftermarket": either
        return BrandKind.unspecified
    if t.startswith(("genuine", "oem")):
        return BrandKind.oem
    if "aftermarket" in t:
        return BrandKind.aftermarket
    return BrandKind.unspecified


# Product lines sold under one maker's part numbers (AAM-FL-... is listed as "Amaron FLO" and as "Amaron").
BRAND_ALIASES = {"amaron flo": "Amaron"}


def canonical_brand(name: str) -> str:
    """One brand per maker: "Hyundai Genuine (Mobis)" -> "Hyundai Genuine", "Amaron FLO 40B20L" -> "Amaron"
    (a trailing model code is not part of the brand)."""
    words = BRAND_NOTE.sub("", name or "").split()
    while len(words) > 1 and re.search(r"\d", words[-1]):
        words.pop()
    joined = " ".join(words)
    return BRAND_ALIASES.get(joined.lower(), joined)


def is_service(part: str, oem_text: str = "") -> bool:
    return (oem_text or "").strip().lower() == "service" or line_kind(part) == "service"


def split_part_number(text: str) -> tuple[str | None, int]:
    """ "09482M00636 x 3" -> ("09482M00636", 3); placeholders ("Model specific", "-") -> (None, 1)."""
    t = (text or "").strip()
    if NO_NUMBER.match(t):
        return None, 1
    m = re.match(r"^(.+?)\s*x\s*(\d+)$", t, re.I)
    return (m.group(1).strip(), int(m.group(2))) if m else (t, 1)


def tri_state(text: str | None, yes: str, no: str) -> bool | None:
    t = (text or "").strip().lower()
    if not t or "assume" in t or "confirm" in t:
        return None
    if t.startswith(no):
        return False
    return True if t.startswith(yes) else None


class Builder:
    def __init__(self, session: Session, version: DatasetVersion, review_dir: Path, team_dir: Path):
        self.s, self.version, self.review_dir, self.team_dir = session, version, review_dir, team_dir
        self.stats: dict[int, FileStats] = {}
        self.unmatched: list[dict] = []
        self.types = {t.key: t for t in session.scalars(select(PartType))}
        self.merge_brands()
        self.brands = {b.name.lower(): b for b in session.scalars(select(Brand))}
        self.parts = {p.part_key: p for p in session.scalars(select(Part))}
        faults = session.scalars(select(Fault).where(Fault.dataset_version_id == version.id)).all()
        self.fault_by_id = {f.id: f for f in faults}
        self.fault_by_source = {(f.source_file_no, f.source_id): f for f in faults}
        self.fault_by_key = {f.fault_key: f for f in faults}
        self.canonical = dict(
            session.execute(
                select(FaultLink.from_fault_id, FaultLink.to_fault_id).where(
                    FaultLink.relation == LinkRelation.merged_into, FaultLink.from_fault_id.in_(self.fault_by_id)
                )
            ).all()
        )
        models = session.execute(select(Model.id, Make.name, Model.name).join(Make)).all()
        self.model_index = F.model_index([tuple(m) for m in models])
        self.variants: dict[int, list[F.VariantFacts]] = defaultdict(list)
        for v in session.scalars(select(Variant)):
            self.variants[v.model_id].append(
                F.VariantFacts(v.model_id, v.year_from, v.year_to, str(v.fuel), str(v.transmission))
            )
        self.links: dict[tuple[int, int, str], FaultPart] = {}

    def merge_brands(self) -> None:
        """Fold brands that differ only by a note or a model code into one; parts keep their ids (a part whose new
        key already exists is folded into that part: its prices, fits and links are rebuilt anyway)."""
        brands = {b.name.lower(): b for b in self.s.scalars(select(Brand))}
        for b in list(brands.values()):
            canon = canonical_brand(b.name)
            if canon == b.name:
                continue
            target = brands.get(canon.lower())
            if target is None or target is b:
                b.name = canon
                brands[canon.lower()] = b
                continue
            for part in self.s.scalars(select(Part).where(Part.brand_id == b.id)):
                part.brand = target
            self.s.flush()
            self.s.delete(b)
        self.s.flush()
        by_key = {p.part_key: p for p in self.s.scalars(select(Part))}
        for part in list(by_key.values()):
            if not part.part_key.startswith("PN:") or part.brand is None:
                continue
            _, _, number, qty = part.part_key.split(":", 3)
            key = f"PN:{part.brand.name.lower()}:{number}:{qty}"
            if key == part.part_key:
                continue
            if key in by_key:
                self.s.delete(part)
            else:
                del by_key[part.part_key]
                part.part_key = key
                by_key[key] = part
        self.s.flush()

    def file(self, file_no: int) -> FileStats:
        return self.stats.setdefault(file_no, FileStats(file_no))

    # ------------------------------------------------------------ upserts

    def part_type(self, name: str) -> PartType:
        key = re.sub(r"\s+", " ", name.lower()).strip()
        if key not in self.types:
            self.types[key] = PartType(key=key, name=name)
            self.s.add(self.types[key])
        return self.types[key]

    def brand(self, name: str, oem_text: str) -> Brand | None:
        name = canonical_brand((name or "").strip())
        if not name or NO_BRAND.match(name):
            return None
        kind = brand_kind(oem_text)
        if name.lower() not in self.brands:
            self.brands[name.lower()] = Brand(name=name, kind=kind)
            self.s.add(self.brands[name.lower()])
        b = self.brands[name.lower()]
        if b.kind == BrandKind.unspecified and kind != BrandKind.unspecified:  # a source that says which kind wins
            b.kind = kind
        return b

    def part(self, row: SourceRow, has_fit: bool) -> Part:
        number, qty = split_part_number(row.part_number)
        brand = self.brand(row.brand, row.oem_text)
        description = re.sub(r"\s+", " ", row.part).strip()
        if number:
            key = f"PN:{brand.name.lower() if brand else '-'}:{number.upper().replace(' ', '')}:{qty}"
        elif has_fit:
            key = f"SRC:{row.source_ref}"
        else:
            key = f"GEN:{row.segment}:{description.lower()}"
        kind = PartKind.consumable if line_kind(description) == "consumable" else PartKind.part
        part = self.parts.get(key)
        if part is not None and part.kind != kind:
            part.kind = kind
        if part is None:
            part = Part(
                part_key=key,
                part_type=self.part_type(part_type_name(description) or description),
                brand=brand,
                part_number=number,
                quantity=qty,
                description=description,
                generic=not number and not has_fit,
                segment=None if number else row.segment,
                kind=kind,
            )
            self.s.add(part)
            self.parts[key] = part
        return part

    # ------------------------------------------------------------ one price row

    def add_service(self, row: SourceRow, fault_ids: list[int], price_max: int | None = None) -> None:
        """A service line (wheel alignment, scan, towing) is labour for each approved fault, never a part."""
        if row.price_inr is None:
            self.file(row.file_no).no_price += 1
            return
        for fault_id in dict.fromkeys(self.canonical.get(f, f) for f in fault_ids):
            self.s.add(
                FaultServiceCharge(
                    dataset_version_id=self.version.id,
                    source=row.source,
                    source_ref=row.source_ref,
                    fault_id=fault_id,
                    segment=row.segment,
                    name=re.sub(r"\s+", " ", row.part).strip(),
                    amount_inr=row.price_inr,
                    amount_max_inr=price_max if price_max is not None and price_max >= row.price_inr else None,
                    verification_status=row.verification,
                    checked_on=row.checked_on,
                    source_url=row.source_url,
                )
            )
            self.file(row.file_no).services += 1

    def add_source_row(self, row: SourceRow) -> None:
        stats = self.file(row.file_no)
        if is_service(row.part, row.oem_text):
            self.add_service(row, [f for f, _, status in row.links if status == ReviewStatus.approved])
            return
        claims = self.fit_claims(row)
        part = self.part(row, has_fit=bool(claims))
        self.s.flush()
        stats.parts.add(part.id)
        if not part.generic:
            stats.specific.add(part.id)
        if part.brand_id:
            stats.brands.add(part.brand_id)
        if row.price_inr is None:
            stats.no_price += 1
        else:
            self.s.add(
                PartPrice(
                    dataset_version_id=self.version.id,
                    source=row.source,
                    source_ref=row.source_ref,
                    part_id=part.id,
                    segment=row.segment,
                    price_inr=row.price_inr,
                    price_basis=row.price_basis,
                    gst_text=row.gst_text,
                    gst_included=tri_state(row.gst_text, "incl", "excl"),
                    fitting_included=tri_state(row.fitting_text, "yes", "no"),
                    fitting_text=row.fitting_text,
                    supplier=row.supplier,
                    source_url=row.source_url,
                    checked_on=row.checked_on,
                    verification_status=row.verification,
                    model_verified=True,
                    note=row.note,
                )
            )
            stats.prices += 1
        if not part.generic:  # generic parts never fit a car (no model named)
            for claim, status in claims:
                self.s.add(
                    PartCompatibility(
                        dataset_version_id=self.version.id,
                        source=row.source,
                        source_ref=row.source_ref,
                        part_id=part.id,
                        model_id=claim.model_id,
                        year_from=claim.year_from,
                        year_to=claim.year_to,
                        fuel=claim.fuel,
                        transmission=claim.transmission,
                        verification_status=status,
                        fit_text=row.fit_text,
                        source_url=row.source_url,
                    )
                )
                stats.fits += 1
        if row.picture_code:
            stats.images += self.link_pictures(part, row.file_no, row.picture_code)
        for fault_id, link_source, status in row.links:
            self.link_fault(part, fault_id, row.segment, link_source, status, in_total=None)

    def fit_claims(self, row: SourceRow) -> list[tuple[F.FitClaim, str]]:
        stats = self.file(row.file_no)
        parsed = F.parse_fit(row.fit_text, self.model_index)
        if parsed.reason == "generic":
            stats.fits_generic += 1
            return []
        if not parsed.claims:
            stats.fits_no_model += 1
            self.unmatched.append(
                {"source_ref": row.source_ref, "part": row.part, "fit_text": row.fit_text, "reason": parsed.reason}
            )
            return []
        kept = []
        for c in parsed.claims:
            if any(
                F.fit_for_variant(c.model_id, c.year_from, c.year_to, c.fuel, c.transmission, parsed.status, v)
                for v in self.variants[c.model_id]
            ):
                kept.append((c, parsed.status))
            else:
                stats.fits_out_of_catalogue += 1
                years = f"{c.year_from or ''}-{c.year_to or ''}" if c.year_from or c.year_to else ""
                self.unmatched.append(
                    {
                        "source_ref": row.source_ref,
                        "part": row.part,
                        "fit_text": row.fit_text,
                        "reason": " ".join(x for x in (c.model_name, years, c.fuel or "") if x)
                        + " is not in the vehicle catalogue",
                    }
                )
        return kept

    def link_pictures(self, part: Part, file_no: int, codes: str) -> int:
        n = 0
        for code in re.split(r"[,;/\s]+", codes):
            if not code:
                continue
            images = self.s.scalars(
                select(Image).where(Image.image_code == code, Image.path.like(f"data/media/F{file_no:02d}/%"))
            ).all()
            for image in images:
                if self.s.get(PartImage, (part.id, image.id)) is None:
                    self.s.add(PartImage(part_id=part.id, image_id=image.id, source=PartImageSource.picture_id))
                    self.s.flush()
                    n += 1
        return n

    def link_fault(self, part: Part, fault_id: int, segment: str, link_source, status, in_total) -> None:
        source_key = self.fault_by_id[fault_id].fault_key
        target = self.canonical.get(fault_id, fault_id)
        k = (target, part.id, segment)
        existing = self.links.get(k)
        rank = {ReviewStatus.approved: 2, ReviewStatus.draft: 1, ReviewStatus.rejected: 0}
        if existing is not None and rank[ReviewStatus(existing.status)] >= rank[ReviewStatus(status)]:
            return
        if existing is not None:
            self.s.delete(existing)
            self.s.flush()
        link = FaultPart(
            fault_id=target,
            part_id=part.id,
            segment=segment,
            source_fault_key=source_key,
            link_source=link_source,
            status=status,
            in_total=in_total,
        )
        self.s.add(link)
        self.links[k] = link

    # ------------------------------------------------------------ inputs

    def sheet_rows(self) -> list[SourceRow]:
        f09 = {
            (r.get("source_ref"), r.get("fault_key")): decision(r.get("approved", ""))
            for r in read_csv(self.review_dir / "F09-fault-links.csv")
        }
        links: dict[int, list[tuple[int, str, str]]] = defaultdict(list)
        q = (
            select(PartPriceSourceFault)
            .join(PartPriceSource)
            .where(PartPriceSource.dataset_version_id == self.version.id)
        )
        sources = {
            s.id: s
            for s in self.s.scalars(
                select(PartPriceSource).where(PartPriceSource.dataset_version_id == self.version.id)
            )
        }
        for link in self.s.scalars(q):
            src = sources[link.part_price_source_id]
            status = ReviewStatus(link.status)
            if status == ReviewStatus.draft:  # file 9: decided in the review CSV
                key = (f"F{src.source_file_no:02d}-{src.key}", self.fault_by_id[link.fault_id].fault_key)
                status = f09.get(key, ReviewStatus.draft)
            links[src.id].append((link.fault_id, link.link_source, status))
        out = []
        for src in sorted(sources.values(), key=lambda s: (s.source_file_no, s.id)):
            out.append(
                SourceRow(
                    file_no=src.source_file_no,
                    source=CatalogueSource.price_sheet,
                    source_ref=f"F{src.source_file_no:02d}-{src.key}",
                    segment=str(src.segment),
                    part=src.part,
                    brand=src.brand or "",
                    oem_text=src.oem_or_aftermarket or "",
                    part_number=src.part_number or "",
                    price_inr=src.price_inr,
                    price_basis=src.price_basis,
                    supplier=src.supplier,
                    source_url=src.source_url,
                    checked_on=src.checked_on,
                    gst_text=src.gst_text,
                    fitting_text=src.fitting_included_text,
                    verification=str(src.verification_status),
                    picture_code=src.picture_code,
                    note=src.note,
                    fit_text=src.vehicle_fit_text,
                    links=links[src.id],
                )
            )
        return out

    def team_rows(self) -> list[SourceRow]:
        """data/catalogue/parts/F07-part_price_sources.csv: the PARTS_PRICE_SOURCES columns
        (data/schema/templates/part_price_sources.csv). Fault IDs are the file's own IDs (SS-01)."""
        out = []
        for path in sorted(self.team_dir.glob("F[0-9][0-9]-part_price_sources.csv")):
            file_no = int(path.name[1:3])
            for r in read_csv(path):
                key, segment = P.clean(col(r, "Key")), segment_of(col(r, "Segment"))
                if not key or segment is None:
                    continue
                links = []
                for sid in ids_in(col(r, "Fault IDs")):
                    fault = self.fault_by_source.get((file_no, sid))
                    if fault is not None:
                        links.append((fault.id, FaultPartSource.team_csv, ReviewStatus.approved))
                out.append(
                    SourceRow(
                        file_no=file_no,
                        source=CatalogueSource.team_csv,
                        source_ref=f"F{file_no:02d}-{key}",
                        segment=segment,
                        part=P.clean(col(r, "Part")),
                        brand=P.clean(col(r, "Manufacturer")),
                        oem_text=P.clean(col(r, "OEM")),
                        part_number=P.clean(col(r, "Part number")),
                        price_inr=num(col(r, "Price (INR)")),
                        price_basis=P.clean(col(r, "Price basis")) or None,
                        supplier=P.clean(col(r, "Supplier")) or None,
                        source_url=P.clean(col(r, "Source URL")) or None,
                        checked_on=P.parse_date(col(r, "Date")),
                        gst_text=P.clean(col(r, "GST")) or None,
                        fitting_text=P.clean(col(r, "Fitting")) or None,
                        verification=part_verification(col(r, "Verification")),
                        picture_code=P.clean(col(r, "Picture ID")) or None,
                        note=P.clean(col(r, "Note")) or None,
                        fit_text=P.clean(col(r, "Vehicle")),
                        links=links,
                    )
                )
                self.file(file_no).team_rows += 1
        return out

    def segment_rows(self) -> None:
        """Approved rows of data/review/parts/F01.csv ...: generic or numbered parts priced per segment, linked to the
        fault, never with a compatibility record (the columns are not model-verified)."""
        for path in sorted(self.review_dir.glob("F[0-9][0-9].csv")):
            file_no = int(path.name[1:3])
            stats = self.file(file_no)
            for r in read_csv(path):
                stats.segment_rows += 1
                if decision(r.get("approved", "")) != ReviewStatus.approved:
                    continue
                if (r.get("parse_status") or "ok") != "ok":  # copied totals, quotations, cross-references: never prices
                    stats.excluded[r["parse_status"]] += 1
                    continue
                fault = self.fault_by_key.get(r.get("fault_key", ""))
                segment = r.get("segment", "")
                if fault is None or segment not in SEGMENTS or not r.get("part"):
                    continue
                stats.segment_approved += 1
                row = SourceRow(
                    file_no=file_no,
                    source=CatalogueSource.segment_review,
                    source_ref=f"{r['fault_key']} {segment} line {r.get('line_no', '')}".strip(),
                    segment=segment,
                    part=r["part"],
                    brand=r.get("brand", ""),
                    part_number=r.get("part_number", ""),
                    price_inr=num(r.get("price_inr")),
                    checked_on=P.parse_date(r.get("checked_on")),
                    verification=part_verification(r.get("price_tag")),
                )
                if (r.get("kind") or line_kind(row.part)) == "service":
                    self.add_service(row, [fault.id], num(r.get("price_max_inr")))
                    continue
                part = self.part(row, has_fit=False)
                self.s.flush()
                stats.parts.add(part.id)
                price = num(r.get("price_inr"))
                if price is not None:
                    top = num(r.get("price_max_inr"))
                    self.s.add(
                        PartPrice(
                            dataset_version_id=self.version.id,
                            source=CatalogueSource.segment_review,
                            source_ref=row.source_ref,
                            part_id=part.id,
                            segment=segment,
                            price_inr=price,
                            price_max_inr=top if top is not None and top >= price else None,
                            checked_on=P.parse_date(r.get("checked_on")),
                            verification_status=part_verification(r.get("price_tag")),
                            model_verified=False,
                            note=r.get("note") or None,
                        )
                    )
                    stats.prices += 1
                in_total = {"yes": True, "no": False}.get((r.get("in_total") or "").lower())
                self.link_fault(
                    part, fault.id, segment, FaultPartSource.segment_review, ReviewStatus.approved, in_total
                )

    def labour(self) -> None:
        rows = self.s.scalars(
            select(LabourRateResearch)
            .where(LabourRateResearch.dataset_version_id == self.version.id)
            .order_by(LabourRateResearch.source_file_no, LabourRateResearch.id)
        ).all()
        items = [
            (
                r.source_file_no,
                CatalogueSource.price_sheet,
                r.repair,
                (r.budget_inr, r.mid_inr, r.premium_inr),
                r.location,
                r.workshop_type,
                r.basis,
                r.status,
                r.checked_on,
                r.extra,
            )
            for r in rows
        ]
        for path in sorted(self.team_dir.glob("F[0-9][0-9]-labour_rates.csv")):
            for r in read_csv(path):
                repair = P.clean(col(r, "Repair"))
                if repair:
                    prices = (num(col(r, "Budget")), num(col(r, "Mid")), num(col(r, "Premium")))
                    items.append(
                        (
                            int(path.name[1:3]),
                            CatalogueSource.team_csv,
                            repair,
                            prices,
                            P.clean(col(r, "City")),
                            P.clean(col(r, "Workshop")) or None,
                            P.clean(col(r, "Source")) or None,
                            P.clean(col(r, "Status")),
                            P.parse_date(col(r, "Date")),
                            {},
                        )
                    )
        for file_no, source, repair, prices, city, workshop, basis, status, checked, extra in items:
            stats = self.file(file_no)
            for segment, amount in zip(("budget", "mid", "premium"), prices, strict=True):
                if amount is None:
                    continue
                if amount <= 0:  # "0" in the sheets means the repair does not apply to that segment
                    stats.labour_not_applicable += 1
                    continue
                self.s.add(
                    LabourRate(
                        dataset_version_id=self.version.id,
                        source=source,
                        source_ref=f"F{file_no:02d} labour: {repair}",
                        source_file_no=file_no,
                        repair=repair,
                        segment=segment,
                        city=city or "Not stated",
                        amount_inr=amount,
                        workshop_type=workshop,
                        basis=basis,
                        status=(status or "").lower(),
                        checked_on=checked,
                        extra=extra or {},
                    )
                )
                stats.labour += 1

    # ------------------------------------------------------------ run

    def prune(self) -> int:
        """Delete parts nothing points at any more (no price, fit or fault link in any version), then brands and part
        types without parts. Parts in use keep their ids."""
        used = (
            select(PartPrice.part_id)
            .union(select(PartCompatibility.part_id), select(FaultPart.part_id))
            .scalar_subquery()
        )
        n = self.s.execute(delete(Part).where(Part.id.not_in(used))).rowcount
        self.s.execute(delete(Brand).where(Brand.id.not_in(select(Part.brand_id).where(Part.brand_id.is_not(None)))))
        self.s.execute(delete(PartType).where(PartType.id.not_in(select(Part.part_type_id))))
        self.s.flush()
        return n

    def clear(self) -> None:
        v = self.version.id
        for table in (PartCompatibility, PartPrice, LabourRate, FaultServiceCharge):
            self.s.execute(delete(table).where(table.dataset_version_id == v))
        self.s.execute(delete(FaultPart).where(FaultPart.fault_id.in_(list(self.fault_by_id))))
        self.s.execute(delete(PartImage))
        self.s.flush()

    def run(self) -> None:
        self.clear()
        for row in [*self.sheet_rows(), *self.team_rows()]:
            if row.source == CatalogueSource.price_sheet:
                self.file(row.file_no).price_rows += 1
            self.add_source_row(row)
        self.segment_rows()
        self.labour()
        self.s.flush()
        self.pruned = self.prune()
        for link in self.links.values():
            stats = self.file(int(link.source_fault_key[1:3]))
            stats.links[str(link.status)] += 1


def build(
    session: Session,
    version: DatasetVersion,
    review_dir: Path = REVIEW_DIR,
    team_dir: Path = TEAM_DIR,
    write_unmatched: bool = True,
) -> BuildResult:
    b = Builder(session, version, review_dir, team_dir)
    b.run()
    result = BuildResult(version.id, dict(sorted(b.stats.items())), b.unmatched)
    if write_unmatched:
        review_dir.mkdir(parents=True, exist_ok=True)
        path = review_dir / "fit-unmatched.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["source_ref", "part", "fit_text", "reason"])
            w.writeheader()
            w.writerows(b.unmatched)
        result.unmatched_path = path
    return result


def table(rows: list[dict]) -> str:
    if not rows:
        return "(nothing built)"
    heads = list(rows[0])
    lines = ["| " + " | ".join(heads) + " |", "|" + "|".join("---" for _ in heads) + "|"]
    lines += ["| " + " | ".join(str(r[h]) for h in heads) + " |" for r in rows]
    return "\n".join(lines)
