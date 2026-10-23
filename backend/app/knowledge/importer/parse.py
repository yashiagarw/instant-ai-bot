"""Cell-level parsing rules. Pure functions, no database access."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime

EXCEL_ERRORS = {"#REF!", "#VALUE!", "#N/A", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!"}
ID_RE = re.compile(r"^([A-Z]{2})-(\d{2,3})$")
ID_IN_TEXT_RE = re.compile(r"\b([A-Z]{2})-(\d{2,3})\b")


def clean(value: object) -> str:
    """Cell value as stripped text ('' for empty)."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def is_excel_error(value: object) -> bool:
    return isinstance(value, str) and value.strip() in EXCEL_ERRORS


def fault_key(file_no: int, source_id: str) -> str:
    return f"F{file_no:02d}-{source_id}"


# ---------------------------------------------------------------- lists

_MARKER_RE = re.compile(r"^\s*(?:[•\-*–·▪]+|\[\s?[xX ]?\s?\]|\d{1,2}[.)])\s*")
_INLINE_NUM_RE = re.compile(r"(?:(?<=\s)|^)(\d{1,2})[.)]\s+")


def _strip_marker(line: str) -> str:
    return _MARKER_RE.sub("", line, count=1).strip()


def _inline_numbered(text: str) -> list[str] | None:
    """'1. Do this. 2. Then that.' -> ['Do this.', 'Then that.'] when the numbers run 1, 2, 3..."""
    matches = list(_INLINE_NUM_RE.finditer(text))
    starts, expected = [], 1
    for m in matches:
        if int(m.group(1)) == expected:
            starts.append(m)
            expected += 1
    if len(starts) < 2:
        return None
    parts = []
    head = text[: starts[0].start()].strip()
    if head:
        parts.append(head)
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        part = text[m.end() : end].strip()
        if part:
            parts.append(part)
    return parts


def split_list(value: object) -> list[str]:
    """Split a list cell into items, in order, markers removed.

    Rules (docs/data-model.md): lines (bullets, numbers, [ ] checkboxes); a single line with an
    inline 1. 2. 3. sequence; a single line with semicolons; else one item. Intro lines such as
    "Check in this order:" are kept as items.
    """
    text = clean(value)
    if not text:
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1:
        return [item for item in (_strip_marker(ln) for ln in lines) if item]
    line = lines[0]
    inline = _inline_numbered(line)
    if inline:
        return inline
    if ";" in line:
        parts = [p.strip() for p in line.split(";") if p.strip()]
        if len(parts) > 1:
            return [_strip_marker(p) for p in parts]
    return [_strip_marker(line)] if _strip_marker(line) else []


# ---------------------------------------------------------------- customer phrases

SYNTHETIC_RE = re.compile(r"example|illustrative|synthetic", re.I)
_EXAMPLE_TAIL_RE = re.compile(r"\s*\((?=[^)]*(?:example|illustrative|record|real case))[^)]*\)\s*$", re.I)
_EXAMPLE_HEAD_RE = re.compile(r"^\s*example\s*(\([^)]*\))?\s*:\s*", re.I)
_HINGLISH_WORDS = {
    "hai",
    "hain",
    "nahi",
    "nahin",
    "nhi",
    "gaadi",
    "gadi",
    "raha",
    "rahi",
    "rahe",
    "kar",
    "karta",
    "karti",
    "kya",
    "kyu",
    "kyun",
    "bhi",
    "aur",
    "mein",
    "lagta",
    "lagti",
    "chal",
    "chalti",
    "wala",
    "wali",
    "hota",
    "hoti",
    "bahut",
    "thoda",
    "liya",
    "gayi",
    "gaya",
    "abhi",
    "jab",
    "toh",
    "ho",
    "ki",
    "ka",
    "ke",
    "pe",
    "awaaz",
    "dikkat",
    "kaam",
    "baar",
    "jaldi",
    "sheesha",
    "dhila",
    "leti",
    "deti",
    "maar",
}


@dataclass
class Phrase:
    text: str
    english_gloss: str | None
    language: str


def guess_language(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    words = set(re.findall(r"[a-z]+", text.lower()))
    if words & _HINGLISH_WORDS:
        return "hinglish"
    if words:
        return "en"
    return "unknown"


def _clean_phrase(text: str) -> str:
    text = _EXAMPLE_HEAD_RE.sub("", text)
    text = _EXAMPLE_TAIL_RE.sub("", text)
    return text.strip().strip('"“”').strip()


def split_phrases(value: object) -> list[Phrase]:
    """CUSTOMER ON AI cell -> phrases. Numbered items (with '= gloss' lines), ' | ' lists,
    bullet lines, or the whole cell. Heading lines are dropped."""
    text = clean(value)
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out: list[Phrase] = []

    if any(re.match(r"^\d+[.)]\s", ln) for ln in lines):
        for ln in lines:
            if re.match(r"^\d+[.)]\s", ln):
                phrase = _clean_phrase(_strip_marker(ln))
                if phrase:
                    out.append(Phrase(phrase, None, guess_language(phrase)))
            elif ln.startswith("=") and out:
                out[-1].english_gloss = ln.lstrip("= ").strip()
        return out

    if " | " in text:
        parts = [p for p in text.split(" | ")]
    elif any(re.match(r"^[•\-]", ln) for ln in lines):
        parts = [_strip_marker(ln) for ln in lines if re.match(r"^[•\-]", ln)]
    else:
        parts = [" ".join(lines)]
    for p in parts:
        phrase = _clean_phrase(p)
        if phrase:
            out.append(Phrase(phrase, None, guess_language(phrase)))
    return out


def is_held_out(key: str, phrase: str, share: int = 20) -> bool:
    """Reproducible ~20% sample: the same phrase is always in or out, across re-imports."""
    return int(hashlib.sha1(f"{key}|{phrase}".encode()).hexdigest(), 16) % 100 < share


# ---------------------------------------------------------------- other fault fields


def road_repairable(value: object) -> str:
    """First word -> yes / limited / no; anything else -> unknown (sent to review)."""
    text = clean(value)
    word = re.split(r"[\s\-–—.,:;/(]+", text, maxsplit=1)[0].lower() if text else ""
    return {"yes": "yes", "limited": "limited", "no": "no"}.get(word, "unknown")


def stage2_choices(value: object) -> list[str]:
    """'Choices: a | b | c' (file 8) or 'Options: a | b | c' (files 9-18)."""
    m = re.search(r"^\s*(?:choices|options)\s*:\s*(.+)$", clean(value), re.I | re.M)
    return [c.strip() for c in m.group(1).split("|") if c.strip()] if m else []


# ---------------------------------------------------------------- money, approx labels, dates

_AMOUNT = r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)"
AMOUNT_RE = re.compile(_AMOUNT, re.I)
RANGE_RE = re.compile(_AMOUNT + r"\s*[–—\-]\s*(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)", re.I)
SEGMENT_MIN_RE = re.compile(r"(budget|mid(?:-range)?|premium)\s*:\s*" + _AMOUNT, re.I)
PARTS_TOTAL_RE = re.compile(r"parts total\s*[:=]?\s*" + _AMOUNT, re.I)


def to_int(text: str) -> int:
    return int(round(float(text.replace(",", ""))))


def as_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    return None


def parse_range(text: str) -> tuple[int, int] | None:
    m = RANGE_RE.search(text)
    if not m:
        return None
    lo, hi = to_int(m.group(1)), to_int(m.group(2))
    return (lo, hi) if lo <= hi else None


def single_amount(text: str) -> int | None:
    """The amount when the text holds exactly one rupee amount, else None."""
    amounts = AMOUNT_RE.findall(text)
    return to_int(amounts[0]) if len(amounts) == 1 else None


def segment_minimums(text: str) -> dict[str, int]:
    """'Budget: Rs 600 | Mid: Rs 800 | Premium: Rs 1,000' -> {budget: 600, mid: 800, premium: 1000}."""
    out = {}
    for seg, amount in SEGMENT_MIN_RE.findall(text):
        key = "mid" if seg.lower().startswith("mid") else seg.lower()
        out.setdefault(key, to_int(amount))
    return out


def parts_total(text: str) -> int | None:
    m = PARTS_TOTAL_RE.search(text)
    return to_int(m.group(1)) if m else None


# Label shown next to a price, in order of precedence.
_APPROX_LABELS = [
    (re.compile(r"approx\s*-\s*ask shop", re.I), "approx - ask shop"),
    (re.compile(r"quotation (required|needed)", re.I), "quotation required"),
    (re.compile(r"\[ESTIMATE\]|price type: estimate|\(estimate\)", re.I), "estimate"),
    (re.compile(r"\bapprox", re.I), "approx"),
    (re.compile(r"indicative", re.I), "indicative estimate"),
]


def approx_label(text: str) -> str | None:
    for rx, label in _APPROX_LABELS:
        if rx.search(text):
            return label
    return None


_MONTHS = {
    m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)
}
_FULL_DATE_RE = re.compile(r"\b(\d{1,2})[- ](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[- ](\d{4})\b", re.I)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# Month-year only counts after "price" ("online price Dec-2025"), never fitment text ("WagonR (Dec 2018+)").
_PRICE_MONTH_RE = re.compile(
    # (?<!\d[- ]) skips the month inside a full date such as "22-Oct-2026".
    r"price[^.\n\]]{0,20}?(?<!\d[- ])\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[- ](\d{4})\b",
    re.I,
)


def price_dates(text: str) -> list[date]:
    found = []
    for d, mon, y in _FULL_DATE_RE.findall(text):
        found.append(date(int(y), _MONTHS[mon[:3].lower()], int(d)))
    for y, mo, d in _ISO_DATE_RE.findall(text):
        try:
            found.append(date(int(y), int(mo), int(d)))
        except ValueError:
            pass
    for mon, y in _PRICE_MONTH_RE.findall(text):
        found.append(date(int(y), _MONTHS[mon[:3].lower()], 1))
    return found


def parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    dates = price_dates(clean(value)) or [
        date(int(y), _MONTHS[m[:3].lower()], int(d)) for d, m, y in _FULL_DATE_RE.findall(clean(value))
    ]
    return max(dates) if dates else None


# ---------------------------------------------------------------- segment costs

SEGMENTS = ("budget", "mid", "premium")


@dataclass
class CostRecord:
    segment: str
    parts_text: str = ""
    part_prices_text: str = ""
    labour_inr: int | None = None
    labour_text: str | None = None
    total_inr: int | None = None
    total_min_inr: int | None = None
    total_max_inr: int | None = None
    total_text: str | None = None
    minimum_inr: int | None = None
    minimum_text: str | None = None
    is_approx: bool = False
    approx_label: str | None = None
    checked_on: date | None = None
    price_basis: str | None = None
    cost_source: str = "sheet"
    display_mode: str = "on_inspection"
    quotation_required: bool = False
    needs_review: bool = False
    review_reason: str | None = None


@dataclass
class CostReview:
    """One line of data/review/costs.csv."""

    segment: str
    raw_total: str
    resolution: str  # range_parsed | text_quotation_required | recalculated | price_on_inspection | unparsed


@dataclass
class CostResult:
    records: list[CostRecord]
    reviews: list[CostReview] = field(default_factory=list)


def parse_costs(
    values: dict[str, object], file_rule: dict | None, f02_labour: dict[str, int] | None = None
) -> CostResult:
    """Segment costs for one fault row.

    values: canonical field -> raw cell value. file_rule: import_rules.yaml costs.<file_no> (None = numeric
    default). f02_labour: approved labour per segment for file 2's recalculation.
    """
    rule = file_rule or {}
    mode = rule.get("mode", "numeric")
    records, reviews = [], []

    min_raw = values.get("minimum_cost")
    min_text = "" if is_excel_error(min_raw) else clean(min_raw)
    min_number = as_number(min_raw)
    per_segment_min = segment_minimums(min_text) if min_number is None else {}

    for seg in SEGMENTS:
        rec = CostRecord(
            segment=seg,
            parts_text=clean(values.get(f"{seg}_parts")),
            part_prices_text=clean(values.get(f"{seg}_part_prices")),
        )
        labour_raw, total_raw = values.get(f"{seg}_labour"), values.get(f"{seg}_total")

        rec.labour_inr = as_number(labour_raw)
        if rec.labour_inr is None and not is_excel_error(labour_raw) and clean(labour_raw):
            rec.labour_text = clean(labour_raw)

        # Minimum: per segment when the cell names segments, else the single value on the budget row.
        if per_segment_min:
            rec.minimum_inr = per_segment_min.get(seg)
            rec.minimum_text = min_text if seg == "budget" else None
        elif seg == "budget":
            rec.minimum_inr = min_number if min_number is not None else (single_amount(min_text) if min_text else None)
            rec.minimum_text = min_text or None

        total_number = as_number(total_raw)
        total_text = "" if is_excel_error(total_raw) else clean(total_raw)

        if mode == "recalculate":
            pt = parts_total(rec.part_prices_text)
            labour = (f02_labour or {}).get(seg)
            if pt is not None and labour is not None:
                rec.total_inr, rec.labour_inr = pt + labour, labour
                rec.cost_source, rec.display_mode = "recalculated", "amount"
                reviews.append(CostReview(seg, clean(total_raw), "recalculated"))
            else:
                rec.cost_source, rec.display_mode = "none", "on_inspection"
                rec.needs_review = True
                missing = "parts total" if pt is None else "approved labour"
                rec.review_reason = f"#REF! total; recalculation needs {missing}"
                reviews.append(CostReview(seg, clean(total_raw), "price_on_inspection"))
        elif total_number is not None:
            rec.total_inr, rec.display_mode = total_number, "amount"
        elif mode == "text" and total_text:
            rec.total_text, rec.display_mode = total_text, "text"
            rec.quotation_required = bool(rule.get("quotation_required"))
            reviews.append(CostReview(seg, total_text, "text_quotation_required"))
        elif mode == "range" and total_text and parse_range(total_text):
            rec.total_min_inr, rec.total_max_inr = parse_range(total_text)
            rec.total_text, rec.display_mode = total_text, "range"
            reviews.append(CostReview(seg, total_text, "range_parsed"))
        else:
            rec.total_text = total_text or None
            rec.display_mode, rec.needs_review = "on_inspection", True
            rec.review_reason = "Excel error in total" if is_excel_error(total_raw) else "total is not a number"
            reviews.append(CostReview(seg, clean(total_raw), "unparsed"))

        price_text = "\n".join(
            t for t in (rec.parts_text, rec.part_prices_text, rec.labour_text or "", total_text, min_text) if t
        )
        rec.approx_label = rule.get("approx_label") or approx_label(price_text)
        rec.is_approx = bool(rule.get("is_approx")) or rec.approx_label is not None
        dates = price_dates(price_text)
        rec.checked_on = max(dates) if dates else None
        if "[VERIFIED]" in price_text:
            rec.price_basis = "Includes manufacturer MRP checked prices ([VERIFIED])"
        if values.get("ev_price_basis"):
            rec.price_basis = clean(values["ev_price_basis"])
        records.append(rec)
    return CostResult(records, reviews)
