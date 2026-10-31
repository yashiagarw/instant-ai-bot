"""Automatic first review of the parts review files (as for the question files in 1.4b), pending a mechanic's sign-off.

    uv run python -m app.parts autoreview   # fills approved / reviewed_by / reviewer_note, writes REVIEW_NOTES.md

Rules, applied only to rows no person has decided (a row with a reviewed_by that is not claude_code is left alone):

Segment rows (data/review/parts/F??.csv)
- parse_status other than ok (copied total, quotation only, cross-reference, not understood) -> no
- no price, or a price of 0 -> no
- FLAG (approved left empty, so not loaded) when the price looks wrong next to the same part elsewhere:
  * the premium price of the fault's part is below its budget price;
  * it is more than 4x, or less than a quarter of, the median price of the same part type and segment across all files
    (at least 4 prices to compare);
  * a range whose top is more than 4x its bottom;
  * a single budget-car part of Rs 50,000 or more, or a mid-range one of Rs 1,00,000 or more.
- everything else -> yes (services too: they are loaded as labour, not parts)

File 9 fault links (F09-fault-links.csv): yes when the part is named in the fault's own price text (QUALITY_AUDIT key
links) or its part number is quoted there (part_number links); otherwise FLAG.
"""

import csv
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.models import DatasetVersion, Fault, FaultCost
from app.parts.build import REVIEW_DIR, read_csv
from app.parts.review import LINK_FIELDS, SEGMENT_FIELDS

REVIEWER = "claude_code (auto, pending mechanic sign-off)"
HIGH_VALUE = 20000  # approved prices at or above this are listed for a mechanic to check
OUTLIER = 4.0
SEGMENT_CEILING = {"budget": 50000, "mid": 100000}  # a single part above this is doubtful for the segment
STOP_WORDS = {"set", "piece", "pieces", "the", "and", "with", "for", "per"}


@dataclass
class FileDecisions:
    file_no: int | str
    approved: int = 0
    rejected: int = 0
    flagged: list[dict] = field(default_factory=list)
    high_value: list[dict] = field(default_factory=list)
    by_human: int = 0
    with_number: int = 0  # file 9 links whose part number is quoted in the fault's price text


def _human(row: dict) -> bool:
    return bool(row.get("reviewed_by")) and not row["reviewed_by"].startswith("claude_code")


def _num(v: str) -> int | None:
    return int(v) if v and re.fullmatch(r"\d+", v) else None


def _decide(row: dict, value: str, note: str) -> None:
    row["approved"], row["reviewed_by"], row["reviewer_note"] = value, REVIEWER, note


def _write(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def review_segments(review_dir: Path) -> list[FileDecisions]:
    files = {p: read_csv(p) for p in sorted(review_dir.glob("F[0-9][0-9].csv"))}
    medians: dict[tuple[str, str], list[int]] = defaultdict(list)
    by_fault: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for rows in files.values():
        for r in rows:
            price = _num(r["price_inr"])
            if r["parse_status"] == "ok" and price and r["kind"] != "service":
                medians[(r["part_type"].lower(), r["segment"])].append(price)
                by_fault[(r["fault_key"], r["part_type"].lower())][r["segment"]] = price
    out = []
    for path, rows in files.items():
        d = FileDecisions(int(path.name[1:3]))
        for r in rows:
            if _human(r):
                d.by_human += 1
                continue
            price, top = _num(r["price_inr"]), _num(r["price_max_inr"])
            if r["parse_status"] != "ok":
                _decide(r, "no", f"Excluded: {r['parse_status'].replace('_', ' ')}. {r['note']}".strip())
            elif not price:
                _decide(r, "no", "No usable price")
            else:
                flags = []
                if r["kind"] != "service":
                    seg = by_fault[(r["fault_key"], r["part_type"].lower())]
                    if "budget" in seg and "premium" in seg and seg["premium"] < seg["budget"]:
                        flags.append(f"premium Rs {seg['premium']} is below budget Rs {seg['budget']}")
                    peers = medians[(r["part_type"].lower(), r["segment"])]
                    if len(peers) >= 4:
                        med = statistics.median(peers)
                        if price > OUTLIER * med or price * OUTLIER < med:
                            flags.append(f"Rs {price} vs median Rs {med:.0f} for this part and segment ({len(peers)})")
                if price >= SEGMENT_CEILING.get(r["segment"], 10**9):
                    flags.append(f"Rs {price:,} is high for a {r['segment']} car")
                if top and top > OUTLIER * price:
                    flags.append(f"wide range Rs {price}-{top}")
                if flags:
                    _decide(r, "", "FLAG: " + "; ".join(flags))
                    d.flagged.append(r)
                else:
                    kind = "labour (service)" if r["kind"] == "service" else r["kind"]
                    _decide(r, "yes", f"Clear: parsed price, {kind}, not model-verified")
                    if price >= HIGH_VALUE:
                        d.high_value.append(r)
            d.approved += r["approved"] == "yes"
            d.rejected += r["approved"] == "no"
        _write(path, rows, SEGMENT_FIELDS)
        out.append(d)
    return out


def review_f09_links(session: Session, version: DatasetVersion, review_dir: Path) -> FileDecisions:
    path = review_dir / "F09-fault-links.csv"
    rows = read_csv(path)
    texts: dict[str, str] = defaultdict(str)
    q = (
        select(Fault.fault_key, FaultCost.part_prices_text)
        .join(FaultCost, FaultCost.fault_id == Fault.id)
        .where(Fault.dataset_version_id == version.id, Fault.source_file_no == 9)
    )
    for key, text in session.execute(q):
        texts[key] += " " + (text or "").lower()
    d = FileDecisions("F09 links")
    for r in rows:
        if _human(r):
            d.by_human += 1
            continue
        text = texts.get(r["fault_key"], "")
        words = [w for w in re.findall(r"[a-z]{3,}", r["part"].lower()) if w not in STOP_WORDS][:2]
        number = (r["part_number"] or "").split(" ")[0].lower()
        d.with_number += bool(number) and number in text
        if r["link_source"] == "part_number" and number and number in text:
            _decide(r, "yes", "Part number quoted in the fault's price text")
        elif words and all(w in text for w in words):
            _decide(r, "yes", "QUALITY_AUDIT key; part named in the fault's price text")
        else:
            _decide(r, "", "FLAG: part not found in the fault's price text")
            d.flagged.append(r)
        d.approved += r["approved"] == "yes"
    _write(path, rows, LINK_FIELDS)
    return d


def _money(row: dict) -> str:
    top = f"-{int(row['price_max_inr']):,}" if row.get("price_max_inr") else ""
    return f"Rs {int(row['price_inr']):,}{top}" if row.get("price_inr") else "-"


def write_notes(review_dir: Path, segments: list[FileDecisions], links: FileDecisions) -> Path:
    excluded = read_csv(review_dir / "excluded.csv")
    reasons: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in excluded:
        reasons[r["parse_status"]][f"F{int(r['file_no']):02d}"] += 1
    flagged = [r for d in segments for r in d.flagged]
    high = sorted((r for d in segments for r in d.high_value), key=lambda r: -int(r["price_inr"]))
    lines = [
        "# Parts review: what a mechanic must still check",
        "",
        "Generated by `cd backend && uv run python -m app.parts autoreview`",
        "(rules in `backend/app/parts/autoreview.py`).",
        f"Every decision below is by `{REVIEWER}`: no mechanic has checked any price yet. A person can overwrite any",
        "row (set `approved` and put their own name in `reviewed_by`); re-running autoreview never touches such rows.",
        "Segment prices are **not model-verified**: they are typical prices for the price segment, shown as such.",
        "",
        "## 1. Decisions per file",
        "",
        "| File | Approved | Rejected | Flagged (not loaded) | Decided by a person |",
        "|---|---|---|---|---|",
    ]
    for d in [*segments, links]:
        name = f"F{d.file_no:02d}" if isinstance(d.file_no, int) else d.file_no
        lines.append(f"| {name} | {d.approved} | {d.rejected} | {len(d.flagged)} | {d.by_human} |")
    lines += [
        "",
        "## 2. Lines never used as prices (rejected)",
        "",
        "Full list with the source text: `data/review/parts/excluded.csv`.",
        "",
        "| Reason | Rows per file | What a mechanic should do |",
        "|---|---|---|",
    ]
    advice = {
        "copied_total": "File 7 writes the total on every part line (battery and terminal clamp both Rs 7,650). "
        "Real per-part prices are needed: add them with the price template, then approve",
        "no_price": "File 6 says 'Quotation required': get a quotation, or leave as Price on inspection",
        "cross_reference": "File 1 lines point at another fault ('see CL-07') or an optional extra job; "
        "nothing to price here",
        "needs_review": "Line not understood: correct the row by hand",
    }
    for reason, per_file in sorted(reasons.items()):
        counts = ", ".join(f"{f} {n}" for f, n in sorted(per_file.items()))
        lines.append(f"| {reason.replace('_', ' ')} | {counts} | {advice.get(reason, '')} |")
    lines += [
        "",
        f"## 3. Flagged prices ({len(flagged)}): check, then set approved yes / no",
        "",
        "| Fault | Segment | Part | Price | Why flagged |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['fault_key']} | {r['segment']} | {r['part'][:70]} | {_money(r)} | {r['reviewer_note'][6:]} |"
        for r in flagged
    ]
    lines += [
        "",
        f"## 4. Approved prices of Rs {HIGH_VALUE:,} or more ({len(high)}): confirm with a workshop",
        "",
        "| Fault | Segment | Part | Price |",
        "|---|---|---|---|",
    ]
    lines += [f"| {r['fault_key']} | {r['segment']} | {r['part'][:70]} | {_money(r)} |" for r in high]
    lines += [
        "",
        "## 5. Other things to check",
        "",
        "- **Services count as labour.** Lines such as 'Wheel alignment (service)', 'Diagnostic scan + basic checks "
        "(service)' and 'Recovery / towing service' are loaded as service charges (`fault_service_charges`), never as "
        "parts. Check that each is a real charge for that repair and is not already inside the sheet's labour figure.",
        "- **Consumables** (coolant, brake fluid, oil, grease, refrigerant) are detected by name and shown separately "
        "in estimates. Check the split for parts such as 'Coolant hose clamp' (kept as a part).",
        f"- **File 9 fault links:** {links.approved} of {links.approved + len(links.flagged)} approved; each part is "
        f"named in the fault's own price text, and {links.with_number} also quote the part number.",
        "- **Brands merged:** 'Hyundai Genuine (Mobis)' and 'Hyundai Genuine (via Motrparts)' -> 'Hyundai Genuine'; "
        "'Amaron FLO 40B20L' -> 'Amaron FLO'; 'Maruti Genuine (via Motrparts)' -> 'Maruti Genuine'.",
        "- **Labour** comes from the sheet's labour column per segment ('Delhi NCR metro estimate'). City rates are "
        "empty in `data/catalogue/zone_labour_rates.yaml` until the team fills them.",
        "",
    ]
    path = review_dir / "REVIEW_NOTES.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def autoreview(session: Session, version: DatasetVersion, review_dir: Path = REVIEW_DIR):
    segments = review_segments(review_dir)
    links = review_f09_links(session, version, review_dir)
    return segments, links, write_notes(review_dir, segments, links)
