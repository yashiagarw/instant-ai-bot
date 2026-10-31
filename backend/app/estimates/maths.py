"""Estimate arithmetic, with no database: ranges, labour from hours x rate, rounding, staleness and verification flags.

Every amount is a (low, high) range in rupees. Components are added as they are; only the total is rounded, each end to
the nearest Rs 50 (Rs 25 rounds up).
"""

import re
from dataclasses import dataclass, field
from datetime import date

ROUND_TO = 50
MAX_AGE_DAYS = 90
KINDS = ("part", "consumable", "labour", "service")


@dataclass(frozen=True)
class Range:
    low: int
    high: int

    def __post_init__(self):
        if self.low < 0 or self.high < self.low:
            raise ValueError(f"bad range {self.low}-{self.high}")

    def __add__(self, other: "Range") -> "Range":
        return Range(self.low + other.low, self.high + other.high)

    @staticmethod
    def zero() -> "Range":
        return Range(0, 0)


@dataclass
class Input:
    """One thing the estimate is made of, with where it came from."""

    kind: str  # part / consumable / labour / service
    name: str
    amount: Range
    source: str  # what a person can look up: "F12-B_O2 price sheet", "F07-SS-01 sheet labour (budget)"
    checked_on: date | None
    verified: bool  # price checked (and, for parts, listed for this car); False for estimates and approx prices
    note: str = ""


@dataclass
class Flags:
    stale: list[str] = field(default_factory=list)  # inputs older than MAX_AGE_DAYS, or with no check date
    unverified: list[str] = field(default_factory=list)

    @property
    def needs_check(self) -> bool:
        return bool(self.stale or self.unverified)


@dataclass
class Totals:
    parts: Range
    consumables: Range
    labour: Range  # labour and service charges
    total: Range  # rounded to ROUND_TO
    flags: Flags
    last_updated: date | None  # newest check date among the inputs
    oldest_input: date | None


def round_to(amount: int | float, step: int = ROUND_TO) -> int:
    """Nearest multiple of step; exactly half way rounds up (Rs 1,225 -> 1,250, Rs 1,224 -> 1,200)."""
    return int((amount + step / 2) // step * step)


def labour_from_rate(hours: tuple[float, float], rate: Range) -> Range:
    """Hours x hourly rate: the low end is the fewest hours at the lowest rate, the high end the most at the highest."""
    lo, hi = hours
    return Range(round(lo * rate.low), round(hi * rate.high))


_HOURS = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:[-–]|to)\s*(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?)\b"
    r"|(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\b",
    re.I,
)


def parse_hours(text: str | None) -> tuple[float, float] | None:
    """Mechanic work time from the repair-time text, in hours. Several steps are added up ("Inspection 20-40 min; scan
    30-60 min" -> 0.83-1.67 h); "waiting for parts" is not work time and is ignored."""
    if not text:
        return None
    lo = hi = 0.0
    found = False
    for line in re.split(r"[;\n]", text):
        if re.search(r"waiting|not mechanic work", line, re.I):
            continue
        for m in _HOURS.finditer(line):
            if m.group(1):
                a, b, unit = float(m.group(1)), float(m.group(2)), m.group(3)
            else:
                a = b = float(m.group(4))
                unit = m.group(5)
            scale = 1 / 60 if unit.lower().startswith("m") else 1
            lo, hi, found = lo + a * scale, hi + b * scale, True
    return (round(lo, 2), round(hi, 2)) if found and hi >= lo else None


def flags_for(inputs: list[Input], today: date, max_age_days: int = MAX_AGE_DAYS) -> Flags:
    f = Flags()
    for i in inputs:
        if i.checked_on is None or (today - i.checked_on).days > max_age_days:
            f.stale.append(i.name)
        if not i.verified:
            f.unverified.append(i.name)
    return f


def combine(inputs: list[Input], today: date, max_age_days: int = MAX_AGE_DAYS) -> Totals:
    def total(*kinds: str) -> Range:
        out = Range.zero()
        for i in inputs:
            if i.kind in kinds:
                out = out + i.amount
        return out

    unknown = {i.kind for i in inputs} - set(KINDS)
    if unknown:
        raise ValueError(f"unknown input kind {unknown}")
    parts, consumables, labour = total("part"), total("consumable"), total("labour", "service")
    raw = parts + consumables + labour
    dates = [i.checked_on for i in inputs if i.checked_on]
    return Totals(
        parts=parts,
        consumables=consumables,
        labour=labour,
        total=Range(round_to(raw.low), round_to(raw.high)),
        flags=flags_for(inputs, today, max_age_days),
        last_updated=max(dates) if dates else None,
        oldest_input=min(dates) if dates else None,
    )


def price_range(text: str | None) -> Range | None:
    """ "₹1,000–₹1,350 (incl. diagnosis)" -> 1000-1350; "Rs 600" -> 600-600; descriptive text -> None."""
    if not text:
        return None
    m = re.search(r"(?:₹|Rs\.?)\s*([\d,]+)\s*(?:[–-]|to)\s*(?:₹|Rs\.?)?\s*([\d,]+)", text)
    if m:
        a, b = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
        return Range(a, b) if b >= a else None
    amounts = re.findall(r"(?:₹|Rs\.?)\s*([\d,]+)", text)
    if len(amounts) == 1:
        v = int(amounts[0].replace(",", ""))
        return Range(v, v)
    return None
