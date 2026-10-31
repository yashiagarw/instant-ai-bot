"""Split a fault's segment parts / part prices cells into one line per part, for the files without a price sheet.

The files write these cells in a few layouts:

- files 8, 10, 11, 13, 15-17: "IN TOTAL:" / "ONLY IF NEEDED", then
  "• Fuel hose clamp (Maruti Genuine, 15894M67P01) = Rs 6 [price checked online 22-Oct-2026]. Fits: ... Note: ..."
- files 2, 5, 7: "• Engine coolant, per litre: Rs 450" or "1. AC O-ring / seal kit (1 set): Rs 300" (₹ or Rs)
- file 3: "Steering rack boot: Rs 129 x 2 = Rs 258 [VERIFIED]; ..." (VERIFIED = maker's MRP checked on a date)
- file 1: the parts cell is numbered, the price cell repeats the numbers: "1. Rs 2,530 (range Rs 2,200 - 3,000)"
- file 6: "• Name — ₹800–₹3,000 × 1  [Published indicative estimate; source S1] Note: ..." or "— Quotation required"

Lines that match none of these (and are not totals, labour or headings) come back with parse_status
"needs_review" so a person can fix them in the review CSV. Service and labour lines are not parts and are left out.
"""

import re
from dataclasses import dataclass
from datetime import date

from app.knowledge.importer import parse as P

AMOUNT = r"(?:Rs\.?|₹|INR)\s*([\d,]+)"
BULLET = r"^(?:•|\d{1,2}\.|-)\s*"
LINE_A = re.compile(
    BULLET + r"(?P<name>.+?)(?:\s*\((?P<brand>[^(),]+),\s*(?P<pn>[A-Z0-9][A-Z0-9-]{4,}(?:\s*x\s*\d+)?)\))?"
    r"\s*=\s*" + AMOUNT + r"\s*\[(?P<tag>[^\]]+)\]\.?(?P<rest>.*)$",
    re.I,
)
LINE_B = re.compile(
    BULLET + r"(?P<name>.+?):\s*" + AMOUNT + r"(?:\s*[–-]\s*(?:Rs\.?|₹)?\s*(?P<max>[\d,]+))?\s*(?P<rest>.*)$", re.I
)
LINE_F = re.compile(r"^(?:•\s*)?(?P<name>[A-Za-z].+?)\s+(?:Rs\.?|₹)\s*(?P<price>[\d,]+)\s*(?P<rest>\(.*\))?$")
FITS = re.compile(r"\b(?:Fits:?|Seller says:)\s*(?P<fit>.*?)(?:\.\s*(?=Note:|Check\b)|\s*Note:|$)")
NOTE = re.compile(r"Note:\s*(?P<note>.*)$")
LINE_E = re.compile(
    BULLET + r"(?P<name>.+?)\s+—\s+₹(?P<min>[\d,]+)(?:\s*–\s*₹(?P<max>[\d,]+))?\s*×\s*(?P<qty>\d+)\s*"
    r"(?:\[(?P<tag>[^\]]*)\])?\s*(?:Note:\s*(?P<note>.*))?$",
)
LINE_E_QUOTE = re.compile(BULLET + r"(?P<name>.+?)\s+—\s+Quotation required", re.I)
ITEM_C = re.compile(
    r"(?P<name>[^;:.]+?):\s*Rs\s*(?P<unit>[\d,]+)\s*x\s*(?P<qty>\d+)\s*=\s*Rs\s*(?P<total>[\d,]+)\s*\[(?P<tag>\w+)\]"
)
NUMBERED_PRICE = re.compile(r"^(\d{1,2})\.\s*" + AMOUNT + r"(?P<rest>.*)$")
NUMBERED_NAME = re.compile(r"^(\d{1,2})\.\s*(.+)$")
SKIP = re.compile(
    r"^(•\s*)?(parts total|labour|no parts|none\b|in total|only if needed|price type|verified\s*=|estimate\s*=|"
    r"car example|vehicle example|representative vehicle|repair used for total|parts needed|total\b|•\s*$|"
    r"not used for this car|(?:Rs\.?|₹)\s*0\b|no part or repair)",
    re.I,
)
SERVICE = re.compile(
    r"\((?:workshop service|service|labour)[^)]*\)|\btowing service\b|^labour\b|\blabour\s*\("
    r"|^(diagnostic|inspection)\b.*\bscan\b",
    re.I,
)
CAR_EXAMPLE = re.compile(r"(?:car|vehicle) example:\s*([^\n]+?)(?:\.\s|\n|$)|representative vehicle:\s*([^\n]+)", re.I)
VERIFIED_ON = re.compile(r"VERIFIED\s*=.*?checked\s+(\d{4}-\d{2}-\d{2})", re.I)
TRAILING_PARENS = re.compile(r"\s*\([^()]*\)\s*$")


@dataclass
class SegmentLine:
    line_no: int
    part: str
    brand: str = ""
    part_number: str = ""
    quantity: int = 1
    price_inr: int | None = None
    price_max_inr: int | None = None
    price_tag: str = "approx"  # checked / listed_recheck / approx
    checked_on: date | None = None
    in_total: bool | None = None
    fit_text: str = ""
    note: str = ""
    parse_status: str = "ok"  # ok / no_price / needs_review


def part_type_name(part: str) -> str:
    """ "Clutch plate (Maruti part 22400M75T40, Swift 2024 5MT; genuine MRP)" -> "Clutch plate"."""
    name = part.strip().rstrip(".")
    while (shorter := TRAILING_PARENS.sub("", name)) != name and shorter:
        name = shorter
    return re.sub(r"\s+", " ", name).strip(" -–—:")


def price_tag(tag: str) -> tuple[str, date | None]:
    t = tag.lower()
    if "checked" in t or t.strip() == "verified":
        return "checked", P.parse_date(tag)
    if "list price" in t or "listed" in t:
        return "listed_recheck", P.parse_date(tag)
    return "approx", P.parse_date(tag)


def car_example(parts_text: str) -> str:
    m = CAR_EXAMPLE.search(parts_text or "")
    return (m.group(1) or m.group(2) or "").strip() if m else ""


def _qty(pn: str) -> tuple[str, int]:
    m = re.match(r"^(.+?)\s*x\s*(\d+)$", pn.strip(), re.I)
    return (m.group(1).strip(), int(m.group(2))) if m else (pn.strip(), 1)


def _parse_file3(text: str) -> list[SegmentLine]:
    checked = VERIFIED_ON.search(text)
    out = []
    for m in ITEM_C.finditer(text):
        name = m.group("name").strip()
        name = re.sub(r"^.*?\.\s+(?=[A-Z])", "", name)  # drop a sentence glued in front
        if SERVICE.search(name):
            continue
        tag = "checked" if m.group("tag").upper() == "VERIFIED" else "approx"
        out.append(
            SegmentLine(
                len(out) + 1,
                name,
                quantity=int(m.group("qty")),
                price_inr=P.to_int(m.group("total")),
                price_tag=tag,
                checked_on=P.parse_date(checked.group(1)) if checked and tag == "checked" else None,
            )
        )
    return out


def parse_segment(parts_text: str, prices_text: str) -> list[SegmentLine]:
    parts_text, prices_text = parts_text or "", prices_text or ""
    if ITEM_C.search(prices_text):
        return _parse_file3(prices_text)
    names = {int(m.group(1)): m.group(2).strip() for m in map(NUMBERED_NAME.match, parts_text.splitlines()) if m}
    out: list[SegmentLine] = []
    in_total: bool | None = None
    untagged_lines = 0
    for raw in prices_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("IN TOTAL"):
            in_total = True
            continue
        if upper.startswith("ONLY IF NEEDED"):
            in_total = False
            continue
        n = len(out) + 1
        if m := LINE_A.match(line):
            tag, checked = price_tag(m.group("tag"))
            pn, qty = _qty(m.group("pn") or "")
            item = SegmentLine(
                n,
                m.group("name").strip(),
                brand=(m.group("brand") or "").strip(),
                part_number=pn,
                quantity=qty,
                price_inr=P.to_int(_amount_after_equals(line)),
                price_tag=tag,
                checked_on=checked,
                in_total=in_total,
                fit_text=fit.group("fit").strip().rstrip(".") if (fit := FITS.search(m.group("rest"))) else "",
                note=note.group("note").strip() if (note := NOTE.search(m.group("rest"))) else "",
            )
        elif m := LINE_E.match(line):
            tag = (m.group("tag") or "").lower()
            item = SegmentLine(
                n,
                m.group("name").strip(),
                quantity=int(m.group("qty")),
                price_inr=P.to_int(m.group("min")),
                price_max_inr=P.to_int(m.group("max")) if m.group("max") else None,
                price_tag="checked" if "verified" in tag and "not" not in tag else "approx",
                note=(m.group("note") or "").strip(),
            )
        elif m := LINE_E_QUOTE.match(line):
            item = SegmentLine(n, m.group("name").strip(), parse_status="no_price", note="Quotation required")
        elif (m := NUMBERED_PRICE.match(line)) and int(m.group(1)) in names:
            item = SegmentLine(n, names[int(m.group(1))], price_inr=P.to_int(m.group(2)), note=m.group("rest").strip())
        elif SKIP.match(line):
            continue
        elif m := LINE_B.match(line):
            untagged_lines += 1
            item = SegmentLine(
                n,
                m.group("name").strip(),
                price_inr=P.to_int(m.group(2)),
                price_max_inr=P.to_int(m.group("max")) if m.group("max") else None,
                note=m.group("rest").strip(),
            )
        elif m := LINE_F.match(line):
            item = SegmentLine(
                n, m.group("name").strip(), price_inr=P.to_int(m.group("price")), note=m.group("rest") or ""
            )
        else:
            item = SegmentLine(n, line.lstrip("•- ").strip(), parse_status="needs_review", note="line not understood")
        item.part = re.sub(r"^\d+\s*[×x]\s*", "", item.part)  # "1 × Caliper kit"
        if SERVICE.search(item.part):
            continue
        if item.price_max_inr is not None and item.price_inr is not None and item.price_max_inr < item.price_inr:
            item.price_max_inr = None
        out.append(item)
    for i, item in enumerate(out, 1):
        item.line_no = i
    priced = [x.price_inr for x in out if x.price_inr]
    untagged = untagged_lines >= len(out)  # "name: ₹n" lines only; tagged lines give a real price each
    if untagged and len(priced) > 1 and len(set(priced)) == 1:  # file 7: the total written on every line
        for item in out:
            item.parse_status = "needs_review"
            item.note = (
                item.note + " " if item.note else ""
            ) + "Every line shows the same amount: it may be the total."
    return out


def _amount_after_equals(line: str) -> str:
    m = re.search(r"=\s*" + AMOUNT, line, re.I)
    return m.group(1) if m else "0"
