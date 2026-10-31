"""Read the "Vehicle (fit)" text of a price row into model-level fit claims, and match claims to a variant.

The text is written for people ("Hyundai Creta 2020-24 (CarDekho list)", "Maruti site lists: WagonR (Dec 2018+),
Swift (Feb 2018+), Dzire 2017+"). A claim is made only for a model in our vehicle catalogue that the text names
outright. Segment wording ("Mid-range car - check fit"), "any car", vague text ("Older Alto/WagonR") and part
numbers the maker does not list for any model give no claim, so those parts stay "fit not verified".
"""

import re
from dataclasses import dataclass, field

from app.enums import Fuel, Transmission
from app.parts.models import FitStatus

# The whole text gives no fit: segment placeholders, any car, a rating rule, or a vague / unlisted part.
NO_FIT = re.compile(
    r"check fit|does not list|any car|\bcars that\b|only cars|private car|other brands|older|part name says"
    r"|^select\b|accessory - check",
    re.I,
)
CONFIRM = re.compile(r"confirm|\bvin\b|chassis|check (variant|year|\d)|piece or set|type not stated", re.I)
# Chunks: "A 2020-24, B / C 2018+; D". A slash inside a date (06/2015) is not a separator.
CHUNK_SPLIT = re.compile(r"[,;]|\s/\s|(?<=[A-Za-z)])/(?=\s?[A-Za-z])|\s\+\s|\.\s+(?=[A-Z])")
YEAR_RANGE = re.compile(
    r"(?:\d{1,2}/)?((?:19|20)\d{2})\s*[-–]\s*(?:\d{1,2}/)?((?:19|20)\d{2}|\d{2})(?!\d)",
)
YEAR_FROM = re.compile(r"((?:19|20)\d{2})\s*\+")
YEAR_ONE = re.compile(r"\b((?:19|20)\d{2})\b")
FUELS = {"petrol": Fuel.petrol, "diesel": Fuel.diesel, "cng": Fuel.cng, "hybrid": Fuel.hybrid, "ev": Fuel.ev}
WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ModelName:
    model_id: int
    name: str  # "Maruti Suzuki Wagon R"


@dataclass(frozen=True)
class FitClaim:
    model_id: int
    model_name: str
    year_from: int | None = None
    year_to: int | None = None
    fuel: Fuel | None = None
    transmission: Transmission | None = None


@dataclass
class FitParse:
    claims: list[FitClaim] = field(default_factory=list)
    status: FitStatus | None = None
    reason: str = ""  # why there is no claim: "generic", "no catalogue model named"


def model_index(models: list[tuple[int, str, str]]) -> dict[str, ModelName]:
    """(model_id, make, model) -> {"wagonr": ModelName}. Spaces and hyphens are ignored, so "WagonR", "Wagon R"
    and "Wagon-R" all match the catalogue's "Wagon R"."""
    return {"".join(WORD.findall(name.lower())): ModelName(mid, f"{make} {name}") for mid, make, name in models}


def _find_model(chunk: str, index: dict[str, ModelName]) -> tuple[ModelName, int] | None:
    """The first catalogue model named in the chunk (longest match at each word), with the character offset after
    it. Matching is on whole words, so "ALTO800" never reads as "Alto K10"."""
    words = list(WORD.finditer(chunk.lower()))
    for i in range(len(words)):
        for k in (3, 2, 1):
            if i + k > len(words):
                continue
            key = "".join(w.group(0) for w in words[i : i + k])
            if key in index:
                return index[key], words[i + k - 1].end()
    return None


def _years(text: str) -> tuple[int | None, int | None] | None:
    if m := YEAR_RANGE.search(text):
        start, end = int(m.group(1)), m.group(2)
        end_year = int(end) if len(end) == 4 else (start // 100) * 100 + int(end)
        return (start, end_year) if end_year >= start else None
    if m := YEAR_FROM.search(text):
        return int(m.group(1)), None
    if m := YEAR_ONE.search(text):
        return int(m.group(1)), int(m.group(1))
    return None


def parse_fit(text: str, index: dict[str, ModelName]) -> FitParse:
    text = (text or "").strip()
    if not text or NO_FIT.search(text):
        return FitParse(reason="generic")
    claims: list[dict] = []
    for chunk in CHUNK_SPLIT.split(text):
        found = _find_model(chunk, index)
        if found is None:
            # "Hyundai Creta 1st gen petrol, 06/2015 - 03/2020": years in the next chunk belong to the model before.
            if claims and claims[-1]["years"] is None and (years := _years(chunk)):
                claims[-1]["years"] = years
            continue
        model, end = found
        rest = chunk[end:]
        words = set(WORD.findall(rest.lower()))
        fuels = [FUELS[w] for w in words if w in FUELS]
        claims.append(
            {
                "model": model,
                "years": _years(rest),
                "fuel": fuels[0] if len(fuels) == 1 else None,
                "transmission": Transmission.mt if "manual" in words else None,
            }
        )
    if not claims:
        return FitParse(reason="no catalogue model named")
    out = []
    for c in claims:
        y = c["years"] or (None, None)
        claim = FitClaim(c["model"].model_id, c["model"].name, y[0], y[1], c["fuel"], c["transmission"])
        if claim not in out:
            out.append(claim)
    return FitParse(out, FitStatus.confirm_fit if CONFIRM.search(text) else FitStatus.listed)


# ---------------------------------------------------------------- matching a variant


@dataclass(frozen=True)
class VariantFacts:
    model_id: int
    year_from: int
    year_to: int | None
    fuel: str
    transmission: str


def years_overlap(a_from: int | None, a_to: int | None, b_from: int | None, b_to: int | None) -> bool:
    lo = max(a_from or 0, b_from or 0)
    hi = min(a_to or 9999, b_to or 9999)
    return lo <= hi


def fit_for_variant(
    model_id: int,
    year_from: int | None,
    year_to: int | None,
    fuel: str | None,
    transmission: str | None,
    status: str,
    variant: VariantFacts,
) -> FitStatus | None:
    """How a compatibility record fits the variant: None when it does not apply. A record that covers only some
    of the variant's years (Creta 2020-24 for the 2020- variant) needs confirming."""
    if model_id != variant.model_id:
        return None
    if fuel is not None and fuel != variant.fuel:
        return None
    if transmission is not None and transmission != variant.transmission:
        return None
    if not years_overlap(year_from, year_to, variant.year_from, variant.year_to):
        return None
    covers = (year_from is None or year_from <= variant.year_from) and (
        year_to is None or (variant.year_to is not None and variant.year_to <= year_to)
    )
    return FitStatus(status) if covers else FitStatus.confirm_fit
