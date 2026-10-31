"""Review files for the parts catalogue (data/review/parts/), written by `python -m app.parts review`:

- F01.csv ... F17.csv: for every file without a PARTS_PRICE_SOURCES sheet, one row per part line of the segment parts
  columns (file 5: its PRICE BREAKDOWN parts lines), with the price for that segment. All are "not model-verified".
  Type yes in `approved` to load a row (no = rejected); you may correct part, part_type, brand, part_number, price.
- F09-fault-links.csv: file 9 has no "Fault IDs using it" column, so its fault links were drafted from QUALITY_AUDIT
  keys and part numbers quoted in the fault's price text. Type yes / no in `approved`.

Re-running keeps every row whose source text did not change, including your edits and decisions.
"""

import csv
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ReviewStatus
from app.knowledge.models import (
    DatasetVersion,
    Fault,
    FaultCost,
    FaultLink,
    LinkRelation,
    PartPriceSource,
    PartPriceSourceFault,
    PriceBreakdownLine,
)
from app.parts.build import REVIEW_DIR, read_csv
from app.parts.segment_text import SegmentLine, car_example, parse_segment, part_type_name

SEGMENT_FIELDS = [
    "file_no",
    "fault_key",
    "canonical_fault_key",
    "fault_name",
    "segment",
    "line_no",
    "part",
    "part_type",
    "brand",
    "part_number",
    "quantity",
    "price_inr",
    "price_max_inr",
    "price_tag",
    "checked_on",
    "in_total",
    "vehicle_fit_text",
    "car_example",
    "fit_status",
    "parse_status",
    "note",
    "source_hash",
    "approved",
    "reviewer_note",
]
LINK_FIELDS = [
    "source_ref",
    "segment",
    "part",
    "part_number",
    "price_inr",
    "fault_key",
    "canonical_fault_key",
    "fault_name",
    "link_source",
    "source_hash",
    "approved",
    "reviewer_note",
]
TIERS = {"budget": "budget", "mid-range": "mid", "mid": "mid", "premium": "premium"}
SEGMENT_ORDER = {"budget": 0, "mid": 1, "premium": 2}


@dataclass
class ReviewStats:
    file_no: int
    faults: int = 0
    lines: int = 0
    needs_review: int = 0
    no_price: int = 0
    kept: int = 0  # rows kept from the earlier file (unchanged source)
    approved: int = 0
    by_segment: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def row(self) -> dict:
        return {
            "file": self.file_no,
            "faults": self.faults,
            "part lines (budget / mid / premium)": "{} ({} / {} / {})".format(
                self.lines, self.by_segment["budget"], self.by_segment["mid"], self.by_segment["premium"]
            ),
            "needs review": self.needs_review,
            "no price (quotation)": self.no_price,
            "kept from earlier run": self.kept,
            "approved": self.approved,
        }


def _hash(*parts: object) -> str:
    return hashlib.sha1("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:12]


def _write(path: Path, rows: list[dict], fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return path


def _canonical_keys(session: Session, version: DatasetVersion) -> dict[str, str]:
    alias = select(Fault.fault_key).where(Fault.id == FaultLink.from_fault_id).scalar_subquery()
    canon = select(Fault.fault_key).where(Fault.id == FaultLink.to_fault_id).scalar_subquery()
    rows = session.execute(
        select(alias, canon).where(
            FaultLink.relation == LinkRelation.merged_into,
            FaultLink.from_fault_id.in_(select(Fault.id).where(Fault.dataset_version_id == version.id)),
        )
    ).all()
    return dict(rows)


def _lines_for_file5(session: Session, version: DatasetVersion) -> dict[tuple[str, str], list[SegmentLine]]:
    out: dict[tuple[str, str], list[SegmentLine]] = defaultdict(list)
    q = (
        select(PriceBreakdownLine)
        .where(PriceBreakdownLine.dataset_version_id == version.id, PriceBreakdownLine.source_file_no == 5)
        .order_by(PriceBreakdownLine.id)
    )
    for line in session.scalars(q):
        segment = TIERS.get(line.tier.lower())
        if segment is None or line.type.lower() != "parts" or line.amount_inr is None:
            continue
        lines = out[(line.fault_source_id, segment)]
        lines.append(SegmentLine(len(lines) + 1, line.item, price_inr=line.amount_inr, note=line.note or ""))
    return out


def segment_review(session: Session, version: DatasetVersion, review_dir: Path = REVIEW_DIR) -> list[ReviewStats]:
    sheet_files = set(
        session.scalars(
            select(PartPriceSource.source_file_no).where(PartPriceSource.dataset_version_id == version.id).distinct()
        )
    )
    canonical = _canonical_keys(session, version)
    file5 = _lines_for_file5(session, version)
    costs = session.execute(
        select(Fault, FaultCost)
        .join(FaultCost, FaultCost.fault_id == Fault.id)
        .where(Fault.dataset_version_id == version.id, Fault.source_file_no.not_in(sheet_files))
        .order_by(Fault.source_file_no, Fault.source_row)
    ).all()
    by_file: dict[int, list[tuple[Fault, FaultCost]]] = defaultdict(list)
    for fault, cost in costs:
        by_file[fault.source_file_no].append((fault, cost))
    out = []
    for file_no, items in sorted(by_file.items()):
        stats = ReviewStats(file_no, faults=len({f.id for f, _ in items}))
        path = review_dir / f"F{file_no:02d}.csv"
        earlier = {(r["fault_key"], r["segment"], r["line_no"], r["source_hash"]): r for r in read_csv(path)}
        rows = []
        items.sort(key=lambda fc: (fc[0].source_row, SEGMENT_ORDER[str(fc[1].segment)]))
        for fault, cost in items:
            segment = str(cost.segment)
            if file_no == 5:
                lines = file5.get((fault.source_id, segment), [])
            else:
                lines = parse_segment(cost.parts_text, cost.part_prices_text)
            example = car_example(cost.parts_text) or (
                cost.parts_text.splitlines()[0].rpartition(" - ")[2] if file_no == 5 and cost.parts_text else ""
            )
            for line in lines:
                h = _hash(
                    fault.fault_key,
                    segment,
                    line.line_no,
                    line.part,
                    line.price_inr,
                    line.price_max_inr,
                    line.parse_status,
                    line.note,
                )
                key = (fault.fault_key, segment, str(line.line_no), h)
                if key in earlier:
                    row = earlier[key]
                    stats.kept += 1
                else:
                    row = {
                        "file_no": file_no,
                        "fault_key": fault.fault_key,
                        "canonical_fault_key": canonical.get(fault.fault_key, fault.fault_key),
                        "fault_name": fault.name,
                        "segment": segment,
                        "line_no": line.line_no,
                        "part": line.part,
                        "part_type": part_type_name(line.part),
                        "brand": line.brand,
                        "part_number": line.part_number,
                        "quantity": line.quantity,
                        "price_inr": "" if line.price_inr is None else line.price_inr,
                        "price_max_inr": "" if line.price_max_inr is None else line.price_max_inr,
                        "price_tag": line.price_tag,
                        "checked_on": line.checked_on.isoformat() if line.checked_on else "",
                        "in_total": "" if line.in_total is None else ("yes" if line.in_total else "no"),
                        "vehicle_fit_text": line.fit_text,
                        "car_example": example,
                        "fit_status": "not model-verified",
                        "parse_status": line.parse_status,
                        "note": line.note,
                        "source_hash": h,
                        "approved": "",
                        "reviewer_note": "",
                    }
                rows.append(row)
                stats.lines += 1
                stats.by_segment[segment] += 1
                stats.needs_review += row["parse_status"] == "needs_review"
                stats.no_price += row["parse_status"] == "no_price"
                stats.approved += (row.get("approved") or "").strip().lower() in {"yes", "y", "true", "1", "approved"}
        _write(path, rows, SEGMENT_FIELDS)
        out.append(stats)
    return out


def f09_links_review(session: Session, version: DatasetVersion, review_dir: Path = REVIEW_DIR) -> tuple[Path, int]:
    """Drafted fault links (file 9) for a person to approve."""
    path = review_dir / "F09-fault-links.csv"
    earlier = {(r["source_ref"], r["fault_key"], r["source_hash"]): r for r in read_csv(path)}
    canonical = _canonical_keys(session, version)
    q = (
        select(PartPriceSourceFault, PartPriceSource, Fault)
        .join(PartPriceSource, PartPriceSource.id == PartPriceSourceFault.part_price_source_id)
        .join(Fault, Fault.id == PartPriceSourceFault.fault_id)
        .where(PartPriceSource.dataset_version_id == version.id, PartPriceSourceFault.status == ReviewStatus.draft)
        .order_by(PartPriceSource.source_file_no, Fault.source_row, PartPriceSource.id)
    )
    rows = []
    for link, src, fault in session.execute(q):
        ref = f"F{src.source_file_no:02d}-{src.key}"
        h = _hash(ref, fault.fault_key, src.part, src.part_number, link.link_source)
        row = earlier.get((ref, fault.fault_key, h)) or {
            "source_ref": ref,
            "segment": str(src.segment),
            "part": src.part,
            "part_number": src.part_number or "",
            "price_inr": "" if src.price_inr is None else src.price_inr,
            "fault_key": fault.fault_key,
            "canonical_fault_key": canonical.get(fault.fault_key, fault.fault_key),
            "fault_name": fault.name,
            "link_source": str(link.link_source),
            "source_hash": h,
            "approved": "",
            "reviewer_note": "",
        }
        rows.append(row)
    _write(path, rows, LINK_FIELDS)
    return path, len(rows)
