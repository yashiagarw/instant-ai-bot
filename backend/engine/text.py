"""Free text to faults: IDF-weighted keyword overlap plus embedding cosine against customer phrases and
symptom lines. The query embedding is computed outside the engine (an `embed` callable is passed in)."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from engine.types import TextEntry

# Very common English / Hinglish words that carry no fault meaning. Negations ("nahi", "not") are kept.
STOPWORDS = frozenset(
    "a an the is are was were be been am i my me we our you your it its this that of to in on at for with and or "
    "but so if when while from by as do does did have has had very too also just please can could will would "
    "hai hain ho raha rahi rahe tha thi the hua hui ka ki ke ko se me mein par pe aur ya bhi kya kuch bahut "
    "meri mera mere gaadi gadi car".split()
)
EMBED_WEIGHT = 0.1  # embedding similarity is added on top of the keyword score (chosen on a dev split)
EMBED_FLOOR = 0.6  # cosine below this counts as no similarity


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+|[ऀ-ॿ]+", text.lower()) if t not in STOPWORDS]


@dataclass
class Match:
    score: float  # 0..1
    text: str  # the phrase or symptom that matched best
    kind: str  # phrase | symptom


class TextIndex:
    def __init__(self, entries: list[TextEntry]):
        self.entries = entries
        self._tokens = [set(tokens(e.text)) for e in entries]
        df: dict[str, int] = defaultdict(int)
        for toks in self._tokens:
            for t in toks:
                df[t] += 1
        n = max(len(entries), 1)
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}
        self._postings: dict[str, list[int]] = defaultdict(list)
        for i, toks in enumerate(self._tokens):
            for t in toks:
                self._postings[t].append(i)
        self._mass = [sum(self.idf[t] for t in toks) for toks in self._tokens]
        with_vec = [i for i, e in enumerate(entries) if e.vector is not None]
        self._vec_rows = np.array(with_vec, dtype=np.int64)
        self._matrix = (
            np.array([entries[i].vector for i in with_vec], dtype=np.float32) if with_vec else np.zeros((0, 0))
        )

    def keyword_scores(self, query: str) -> dict[int, float]:
        """Entry index -> cosine-like overlap of IDF-weighted token sets."""
        q = set(tokens(query))
        q_mass = sum(self.idf.get(t, math.log(1 + len(self.entries))) for t in q)
        if not q or q_mass == 0:
            return {}
        overlap: dict[int, float] = defaultdict(float)
        for t in q:
            w = self.idf.get(t)
            if w is None:
                continue
            for i in self._postings[t]:
                overlap[i] += w
        return {i: s / math.sqrt(q_mass * self._mass[i]) for i, s in overlap.items() if self._mass[i] > 0}

    def embed_scores(self, query_vector: list[float] | None) -> dict[int, float]:
        if query_vector is None or len(self._vec_rows) == 0:
            return {}
        sims = self._matrix @ np.asarray(query_vector, dtype=np.float32)
        scaled = np.clip((sims - EMBED_FLOOR) / (1 - EMBED_FLOOR), 0, 1)
        keep = np.nonzero(scaled > 0)[0]
        return {int(self._vec_rows[k]): float(scaled[k]) for k in keep}

    def match(self, query: str, query_vector: list[float] | None, fault_ids: Iterable[int]) -> dict[int, Match]:
        """Best match per fault among the given faults."""
        allowed = set(fault_ids)
        kw = self.keyword_scores(query)
        em = self.embed_scores(query_vector)
        best: dict[int, Match] = {}
        for i in set(kw) | set(em):
            e = self.entries[i]
            if e.fault_id not in allowed:
                continue
            s = min(1.0, kw.get(i, 0.0) + EMBED_WEIGHT * em.get(i, 0.0))
            if s > 0 and (e.fault_id not in best or s > best[e.fault_id].score):
                best[e.fault_id] = Match(s, e.text, e.kind)
        return best


def phrase_in(phrase: str, text_tokens: set[str]) -> bool:
    """All content words of the phrase appear in the text."""
    p = tokens(phrase)
    return bool(p) and all(t in text_tokens for t in p)


Embed = Callable[[str], list[float]]
# Free text -> best match per fault, among the given (applicable) fault ids. The app passes hybrid search.
Search = Callable[[str, set[int]], dict[int, Match]]


NEAR_DUPLICATE = 0.6  # word overlap (Jaccard) at which two lines say the same thing
COVERED = 0.85  # share of a line's words already said by shorter lines -> the line only repeats them
PIECE = 0.6  # share of a short line's words found in a long line -> the short line is a piece of it


def _words(text: str) -> set[str]:
    return {t for t in tokens(text) if len(t) > 2}


def drop_repeats(lines: list[str]) -> list[str]:
    """Remove exact and near-duplicate lines (the first one is kept)."""
    kept: list[str] = []
    for line in lines:
        w = _words(line)
        if not line.strip() or any(
            line.strip().lower() == k.strip().lower() or _jaccard(w, _words(k)) >= NEAR_DUPLICATE for k in kept
        ):
            continue
        kept.append(line)
    return kept


def pick_lines(lines: list[str], limit: int) -> list[str]:
    """Up to `limit` lines without duplicates. A line that just repeats shorter lines combined (its words are
    almost all in them) is replaced, at its place, by those shorter pieces, so nothing it says is lost."""
    pool = drop_repeats(lines)
    out: list[str] = []

    def add(line: str) -> None:
        if line in out:
            return
        w = _words(line)
        shorter = [k for k in pool if len(_words(k)) < len(w)]
        said = set().union(*(_words(k) for k in [*out, *shorter]))  # lines already shown count as said
        if len(w) >= 4 and len(w & said) / len(w) >= COVERED:
            for k in shorter:
                if _part_of(_words(k), w):
                    add(k)  # a piece may itself only repeat shorter lines (strictly shorter: this ends)
        else:
            out.append(line)

    for line in pool:
        add(line)
    return out[:limit]


def _part_of(piece: set[str], whole: set[str]) -> bool:
    return bool(piece) and len(piece & whole) / len(piece) >= PIECE


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0
