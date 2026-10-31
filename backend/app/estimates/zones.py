"""Delhi NCR zones (data/schema/zones.yaml) and per-zone labour rates (data/catalogue/zone_labour_rates.yaml)."""

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from app.estimates.maths import Range

REPO_ROOT = Path(__file__).resolve().parents[3]
ZONES_PATH = REPO_ROOT / "data" / "schema" / "zones.yaml"
RATES_PATH = REPO_ROOT / "data" / "catalogue" / "zone_labour_rates.yaml"


@dataclass(frozen=True)
class Zone:
    code: str
    label: str
    pincodes: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ZoneRate:
    rate: Range  # rupees per hour
    source: str
    checked_on: date


@lru_cache
def zones(path: Path = ZONES_PATH) -> dict[str, Zone]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        code: Zone(code, z["label"], tuple((int(a), int(b)) for a, b in z.get("pincodes", [])))
        for code, z in (doc.get("zones") or {}).items()
    }


def zone_for_pincode(pincode: str | None, path: Path = ZONES_PATH) -> Zone | None:
    """The zone a 6-digit pincode falls in, or None (outside Delhi NCR, or not a pincode)."""
    pin = re.sub(r"\s", "", pincode or "")
    if not re.fullmatch(r"\d{6}", pin):
        return None
    n = int(pin)
    return next((z for z in zones(path).values() if any(a <= n <= b for a, b in z.pincodes)), None)


@lru_cache
def zone_rates(path: Path = RATES_PATH) -> dict[tuple[str, str], ZoneRate]:
    """(zone, segment) -> hourly rate. A rate counts only with a source and a check date; empty values are ignored."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for code, z in (doc.get("zones") or {}).items():
        source, checked = (z.get("source") or "").strip(), z.get("checked_on")
        if not source or not isinstance(checked, date):
            continue
        for segment in ("budget", "mid", "premium"):
            value = z.get(segment)
            if value is None:
                continue
            low, high = (value, value) if isinstance(value, (int, float)) else value
            out[(code, segment)] = ZoneRate(Range(int(low), int(high)), source, checked)
    return out
