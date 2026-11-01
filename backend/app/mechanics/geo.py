"""Where a pincode is, without a paid maps API: centre points from data/schema/pincode_centres.yaml (GeoNames, CC BY
4.0; see the file's header for the source and date). Approximate: good for "who is nearest", not for routing."""

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.estimates.zones import REPO_ROOT, zone_for_pincode

CENTRES_PATH = REPO_ROOT / "data" / "schema" / "pincode_centres.yaml"


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float
    # "pincode" (its centre), "rough" (GeoNames estimated it from neighbouring pincodes: can be 10-20 km off) or
    # "zone" (the zone's centre: the pincode has no point of its own)
    precision: str
    zone: str


@lru_cache
def _centres(path: Path = CENTRES_PATH) -> tuple[dict, dict]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    zones = {code: (float(p[0]), float(p[1])) for code, p in (doc.get("zones") or {}).items()}
    pins = {
        str(pin): (float(v[0]), float(v[1]), str(v[2]), int(v[4]) if len(v) > 4 else 4)
        for pin, v in (doc.get("pincodes") or {}).items()
    }
    return zones, pins


def locate(pincode: str | None, path: Path = CENTRES_PATH) -> Point | None:
    """The pincode's centre, its zone's centre when it has none, or None (outside Delhi NCR / not a pincode)."""
    pin = re.sub(r"\s", "", pincode or "")
    zones, pins = _centres(path)
    if pin in pins:
        lat, lon, zone, accuracy = pins[pin]
        return Point(lat, lon, "pincode" if accuracy >= 3 else "rough", zone)
    zone = zone_for_pincode(pin)
    if zone is not None and zone.code in zones:
        lat, lon = zones[zone.code]
        return Point(lat, lon, "zone", zone.code)
    return None


def distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Straight-line (great-circle) distance. Roads are longer: treat it as a ranking signal."""
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
