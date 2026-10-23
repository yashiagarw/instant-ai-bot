"""Fuzzy vehicle search: "swift 2019 petrol", "creta diesel automatic", "swfit".

1. Pull year, fuel and gearbox words out of the query; the rest is the model text.
2. Candidate models: pg_trgm word similarity of each model-text word against models.search_text.
3. Re-rank: add how closely the typed words spell the model name (catches typos like "swfit"
   and breaks ties such as "swift" vs Dzire's alias "swift dzire").
4. Return the matching variants, filtered by fuel / gearbox. The year filter is relaxed (and
   reported) when no variant covers that year, e.g. an older generation we do not list.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.enums import Fuel, Transmission
from app.vehicles.models import Model, Variant
from app.vehicles.seed import normalise

FUEL_WORDS = {
    "petrol": Fuel.petrol,
    "gasoline": Fuel.petrol,
    "diesel": Fuel.diesel,
    "cng": Fuel.cng,
    "hybrid": Fuel.hybrid,
    "ev": Fuel.ev,
    "electric": Fuel.ev,
}
AUTOMATICS = {Transmission.amt, Transmission.cvt, Transmission.dct, Transmission.at}
TRANSMISSION_WORDS = {
    "manual": {Transmission.mt},
    "mt": {Transmission.mt},
    "amt": {Transmission.amt},
    "ags": {Transmission.amt},
    "cvt": {Transmission.cvt},
    "ivt": {Transmission.cvt},
    "dct": {Transmission.dct},
    "dsg": {Transmission.dct},
    "at": {Transmission.at},
    "automatic": AUTOMATICS,
    "auto": AUTOMATICS,
}
STOP_WORDS = {"car", "my", "the", "model", "gaadi", "gadi", "ki", "ka", "hai", "variant", "version"}
YEAR_RE = re.compile(r"^(19[89]\d|20\d{2})$")

MIN_TRIGRAM = 0.3  # candidate threshold for the per-word trigram score
MIN_NAME_RATIO = 0.75  # or this close to the model name (typos)
MAX_CANDIDATE_MODELS = 15
# Keep models scoring at least this share of the best one, so "swift" does not also list
# Dzire (alias "swift dzire") and "maruti" still lists every Maruti model.
RELATIVE_CUTOFF = 0.85
PREFIX_RATIO = 0.95


@dataclass
class ParsedQuery:
    text_words: list[str] = field(default_factory=list)
    year: int | None = None
    fuel: Fuel | None = None
    transmissions: set[Transmission] | None = None


def parse_query(q: str) -> ParsedQuery:
    parsed = ParsedQuery()
    for word in normalise(q).split():
        if YEAR_RE.match(word) and parsed.year is None:
            parsed.year = int(word)
        elif word in FUEL_WORDS and parsed.fuel is None:
            parsed.fuel = FUEL_WORDS[word]
        elif word in TRANSMISSION_WORDS:
            wanted = TRANSMISSION_WORDS[word]
            parsed.transmissions = wanted if parsed.transmissions is None else parsed.transmissions & wanted
        elif word not in STOP_WORDS:
            parsed.text_words.append(word)
    return parsed


def name_ratio(words: list[str], model_name: str) -> float:
    """Best spelling match (0-1) between 1-3 consecutive typed words, joined, and the model name."""
    target = normalise(model_name).replace(" ", "")
    best = 0.0
    for size in (1, 2, 3):
        for i in range(len(words) - size + 1):
            candidate = "".join(words[i : i + size])
            best = max(best, SequenceMatcher(None, candidate, target).ratio())
            # "scorpio" -> Scorpio Classic, "thar" -> Thar Roxx: a typed prefix nearly counts as exact.
            if len(candidate) >= 3 and target.startswith(candidate):
                best = max(best, PREFIX_RATIO)
    return best


@dataclass
class SearchHit:
    variant: Variant
    score: float


@dataclass
class SearchResult:
    parsed: ParsedQuery
    year_matched: bool
    hits: list[SearchHit]


def search_vehicles(session: Session, q: str, limit: int = 20) -> SearchResult:
    parsed = parse_query(q)
    if not parsed.text_words:
        return SearchResult(parsed, year_matched=parsed.year is None, hits=[])

    # Per-word trigram score, averaged over the model-text words.
    per_word = [func.word_similarity(w, Model.search_text) for w in parsed.text_words]
    trigram = sum(per_word[1:], per_word[0]) / len(per_word)
    rows = (
        session.execute(
            select(Model, trigram.label("trigram"))
            .options(joinedload(Model.make), joinedload(Model.variants))
            .order_by(trigram.desc(), Model.name)
            .limit(100)
        )
        .unique()
        .all()
    )

    scored = []
    for model, trigram_score in rows:
        ratio = name_ratio(parsed.text_words, model.name)
        if trigram_score < MIN_TRIGRAM and ratio < MIN_NAME_RATIO:
            continue
        bonus = ratio if ratio >= MIN_NAME_RATIO else 0.0
        scored.append((float(trigram_score) + bonus, model))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    if scored:
        best = scored[0][0]
        scored = [(score, model) for score, model in scored if score >= RELATIVE_CUTOFF * best]
    scored = scored[:MAX_CANDIDATE_MODELS]

    def variant_ok(v: Variant, use_year: bool) -> bool:
        if parsed.fuel is not None and v.fuel != parsed.fuel:
            return False
        if parsed.transmissions is not None and v.transmission not in parsed.transmissions:
            return False
        if use_year and parsed.year is not None:
            return v.year_from <= parsed.year and (v.year_to is None or parsed.year <= v.year_to)
        return True

    def collect(use_year: bool) -> list[SearchHit]:
        return [
            SearchHit(v, round(score, 3)) for score, model in scored for v in model.variants if variant_ok(v, use_year)
        ]

    hits = collect(use_year=True)
    year_matched = True
    if not hits and parsed.year is not None:
        hits = collect(use_year=False)
        year_matched = False
    return SearchResult(parsed, year_matched=year_matched, hits=hits[:limit])
