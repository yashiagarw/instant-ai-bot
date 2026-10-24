"""Hybrid free-text search over the `embeddings` table: Postgres full-text search, vector similarity and a
typo-tolerant full-text list (query words corrected to the nearest indexed word by trigram similarity), merged
with reciprocal rank fusion (RRF). Hindi in Devanagari is also searched in its Hinglish form (engine.hindi).
Always restricted to the candidate faults the engine passes in, which already apply to the car (vehicle
filters on categories).

The engine calls an instance as `search(text, fault_ids) -> {fault_id: Match}`; it never imports this module.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.orm import Session

from engine.hindi import transliterate
from engine.text import Match, tokens

RRF_K = 5  # fusion constant: best within-category top-1 on training phrases (data/eval/tune_search.py)
PER_LIST = 50  # rows taken from each ranked list
VECTOR_FLOOR = 0.5  # cosine below this is not a match (multilingual MiniLM, normalised vectors)
FUZZY_FLOOR = 0.45  # trigram Jaccard for correcting a query word to an indexed word ("battry" -> "battery")
LISTS = ("fts", "vector", "fuzzy")
# Weighted RRF: on training phrases the vector list helps most at half weight (exact words are strong evidence in
# Hinglish and English; vectors carry Hindi and paraphrases). data/eval/tune_search.py
WEIGHTS = {"fts": 1.0, "vector": 0.5, "fuzzy": 1.0}
WORD = re.compile("[a-z0-9]+|[\u0900-\u097f]+")  # safe inside a tsquery
FTS_POOL = 200  # full-text rows fetched before re-ranking them by word rarity
# Hinglish verbs, helpers and negations: frequent in every kind of message, they say nothing about the fault
# (negation still reaches the vector list, which keeps the meaning). Added to the engine's stopwords.
SEARCH_STOPWORDS = frozenset(
    "nahi nhi nahin nai not no de diya di dena aa aaya aayi aate aati aata ja jaa jaata jaati jata gaya gayi gaye "
    "kar kr karta karti karte kiya rha rhi rhe hota hoti hote lag lagta lagti h hy he ab abhi wala wali "
    "bahut bohot thoda thodi ek pura puri sab".split()
)
KIND = {"synonym": "phrase", "symptom": "symptom", "fault": "symptom", "diagnosis_step": "symptom"}


@dataclass
class Hit:
    """One indexed row and where it ranked in each list."""

    owner_type: str
    owner_id: int
    fault_id: int
    text: str
    ranks: dict[str, int] = field(default_factory=dict)
    similarity: float = 0.0  # cosine, when the row came from the vector list
    lexical: float = 0.0  # word-rarity overlap with the query (0..1), when it came from a full-text list

    def relevance(self, vector_floor: float = VECTOR_FLOOR) -> float:
        """How well the row matches in absolute terms (0..1): the better of word overlap and vector similarity."""
        vec = max(0.0, (self.similarity - vector_floor) / (1 - vector_floor)) if self.similarity else 0.0
        return max(self.lexical, vec)

    def fused(self, k: int = RRF_K, weights: dict[str, float] = WEIGHTS) -> float:
        return sum(weights.get(n, 1.0) / (k + r) for n, r in self.ranks.items())


def fuse(lists: dict[str, list[tuple]], k: int = RRF_K, lexical: dict | None = None) -> list[Hit]:
    """Reciprocal rank fusion. lists: name -> rows (owner_type, owner_id, fault_id, text[, similarity]) in rank
    order. Returns hits, best first; a row found by several lists gets the sum of 1 / (k + rank). `lexical`:
    (owner_type, owner_id) -> word overlap score, kept on the hit."""
    lexical = lexical or {}
    hits: dict[tuple[str, int], Hit] = {}
    for name, rows in lists.items():
        for rank, row in enumerate(rows, start=1):
            key = (row[0], row[1])
            hit = hits.setdefault(key, Hit(row[0], row[1], row[2], row[3], lexical=lexical.get(key, 0.0)))
            hit.ranks.setdefault(name, rank)
            if name == "vector" and len(row) > 4:
                hit.similarity = float(row[4])
    return sorted(hits.values(), key=lambda h: (-h.fused(k), h.owner_type, h.owner_id))


def best_per_fault(
    hits: Iterable[Hit],
    k: int = RRF_K,
    weights: dict[str, float] = WEIGHTS,
    vector_floor: float = VECTOR_FLOOR,
) -> dict[int, Match]:
    """The best row of each fault as an engine Match (score 0..1, like the engine's keyword score).

    Score = fused RRF score (scaled so that ranking first in every list is 1.0) x the row's relevance. RRF alone is
    rank-based, so neighbours score almost the same; the relevance keeps an exact match sharp and a weak one low,
    which the engine's routing and stopping rules rely on."""
    top = sum(weights.values()) / (k + 1)
    out: dict[int, Match] = {}
    for h in hits:
        score = min(1.0, h.fused(k, weights) / top) * h.relevance(vector_floor)
        if score <= 0:
            continue
        if h.fault_id not in out or score > out[h.fault_id].score:
            out[h.fault_id] = Match(round(score, 4), h.text, KIND.get(h.owner_type, "symptom"))
    return out


def query_words(query: str, stopwords: frozenset[str] = SEARCH_STOPWORDS) -> list[str]:
    """Content words of the query for full-text search (engine stopwords and `stopwords` removed)."""
    return [w for w in dict.fromkeys(tokens(query)) if w not in stopwords and WORD.fullmatch(w)]


def tsquery(query: str, prefix: bool = False, stopwords: frozenset[str] = SEARCH_STOPWORDS) -> str:
    """Any of the query's content words; with `prefix` (off by default: it added noise on training phrases), words
    of 4+ letters also match longer words."""
    words = query_words(query, stopwords)
    return " | ".join(f"{w}:*" if prefix and len(w) >= 4 and w.isascii() else w for w in words)


# Candidate fault ids and excluded owner ids are passed as single array parameters (= ANY): one bind value however
# many faults apply, instead of hundreds of expanded IN placeholders.
CANDIDATES = (
    "fault_id = ANY(CAST(:ids AS bigint[])) "
    "AND NOT (owner_type = 'synonym' AND owner_id = ANY(CAST(:exclude AS bigint[])))"
)

FTS_SQL = text(
    f"""
    SELECT owner_type, owner_id, fault_id, text
    FROM embeddings, to_tsquery('simple', :q) query
    WHERE model_name = :model AND tsv @@ query AND {CANDIDATES}
    ORDER BY ts_rank_cd(tsv, query) DESC, id
    LIMIT :n
    """
)

# Large candidate sets (free text with no tile): the HNSW index, then the candidate filter. With ef_search rows
# from the index this can return fewer than :n rows when the filter is selective; the caller then falls back to
# the exact query. (No hnsw.iterative_scan: a backend crash was seen with it during a full evaluation run.)
VECTOR_HNSW_SQL = text(
    f"""
    SELECT owner_type, owner_id, fault_id, text, 1 - (vector <=> CAST(:v AS vector)) AS similarity
    FROM embeddings
    WHERE model_name = :model AND {CANDIDATES}
    ORDER BY vector <=> CAST(:v AS vector)
    LIMIT :n
    """
)

# Small candidate sets (a tile or category): exact distances over just those rows. The materialised subquery keeps
# the planner off the HNSW index, so every candidate row is considered.
VECTOR_EXACT_SQL = text(
    f"""
    WITH rows AS MATERIALIZED (
        SELECT owner_type, owner_id, fault_id, text, vector FROM embeddings WHERE model_name = :model AND {CANDIDATES}
    )
    SELECT owner_type, owner_id, fault_id, text, 1 - (vector <=> CAST(:v AS vector)) AS similarity
    FROM rows
    ORDER BY vector <=> CAST(:v AS vector)
    LIMIT :n
    """
)
EXACT_MAX_FAULTS = 150  # up to this many candidate faults (about 3,000 rows) the exact search is used
HNSW_EF_SEARCH = 200  # rows the index returns before the candidate filter


VOCABULARY_SQL = text(
    "SELECT word, ndoc FROM ts_stat($$SELECT tsv FROM embeddings WHERE model_name = $$ || quote_literal(:model))"
)


def trigrams(word: str) -> set[str]:
    padded = f"  {word} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


class Vocabulary:
    """Indexed words with a trigram index, to correct typos in query words."""

    def __init__(self, words: dict[str, int], n_docs: int | None = None):
        self.freq = words
        self.n_docs = n_docs or max(words.values(), default=1)
        self.index: dict[str, list[str]] = {}
        for w in words:
            if w.isascii() and w.isalpha() and len(w) >= 3:
                for g in trigrams(w):
                    self.index.setdefault(g, []).append(w)

    def idf(self, word: str) -> float:
        return math.log(1 + self.n_docs / self.freq.get(word, 1))

    def rerank(self, rows: list, words: list[str], n: int, scores: dict | None = None) -> list:
        """Rows (owner_type, owner_id, fault_id, text) ordered by the rarity of the query words they contain
        (IDF-weighted overlap, normalised by the length of both texts). Words of 4+ letters match as prefixes.
        Each kept row's overlap score goes into `scores` (best score per row)."""
        q_mass = sum(self.idf(w) for w in words) or 1.0
        scored = []
        for r in rows:
            row_words = set(tokens(r[3]))
            hit = sum(
                self.idf(w)
                for w in words
                if w in row_words or (len(w) >= 4 and any(t.startswith(w) for t in row_words))
            )
            if hit:
                mass = sum(self.idf(t) for t in row_words) or 1.0
                scored.append((hit / math.sqrt(q_mass * mass), r))
        scored.sort(key=lambda x: -x[0])
        if scores is not None:
            for sc, r in scored[:n]:
                scores[(r[0], r[1])] = max(sc, scores.get((r[0], r[1]), 0.0))
        return [r for _, r in scored[:n]]

    def correct(self, word: str, floor: float = FUZZY_FLOOR) -> str | None:
        """The closest indexed word, or None (the word is known, too short, or nothing is close enough)."""
        if word in self.freq or len(word) < 4 or not (word.isascii() and word.isalpha()):
            return None
        mine = trigrams(word)
        shared: dict[str, int] = {}
        for g in mine:
            for w in self.index.get(g, ()):
                shared[w] = shared.get(w, 0) + 1
        best, best_sim = None, floor
        for w, n in shared.items():
            sim = n / (len(mine) + len(trigrams(w)) - n)
            if sim > best_sim or (sim == best_sim and best and self.freq[w] > self.freq[best]):
                best, best_sim = w, sim
        return best


class HybridSearch:
    """`search(text, fault_ids)` for the engine. `connect()` returns a context manager yielding a Session (one per
    call, so the engine can be shared). `embed(text)` returns the query vector from the same model as the rows."""

    def __init__(
        self,
        connect: Callable[[], AbstractContextManager[Session]],
        embed: Callable[[str], list[float]],
        model_name: str,
        *,
        k: int = RRF_K,
        per_list: int = PER_LIST,
        vector_floor: float = VECTOR_FLOOR,
        fuzzy_floor: float = FUZZY_FLOOR,
        prefix: bool = False,
        fts_pool: int = FTS_POOL,
        stopwords: frozenset[str] = SEARCH_STOPWORDS,
        cache_size: int = 4096,
    ):
        self.prefix, self.fts_pool, self.stopwords = prefix, fts_pool, stopwords
        self.connect, self.model_name = connect, model_name
        self.k, self.per_list, self.vector_floor, self.fuzzy_floor = k, per_list, vector_floor, fuzzy_floor
        self._vocabulary: Vocabulary | None = None
        self._embed = lru_cache(maxsize=cache_size)(lambda t: tuple(embed(t)))
        self._cached = lru_cache(maxsize=cache_size)(self._search)

    def vocabulary(self, session: Session) -> Vocabulary:
        if self._vocabulary is None:
            rows = session.execute(VOCABULARY_SQL, {"model": self.model_name}).all()
            total = session.execute(
                text("SELECT count(*) FROM embeddings WHERE model_name = :m"), {"m": self.model_name}
            ).scalar_one()
            self._vocabulary = Vocabulary({w: n for w, n in rows}, total)
        return self._vocabulary

    def hits(self, query: str, fault_ids: Iterable[int], exclude: Iterable[int] = ()) -> list[Hit]:
        ids = sorted(set(fault_ids))
        query = query.strip()
        if not query or not ids:
            return []
        params = {"model": self.model_name, "ids": ids, "exclude": sorted(set(exclude)), "n": self.per_list}
        variants = list(dict.fromkeys([query, transliterate(query)]))  # Devanagari: also its Hinglish form
        q = tsquery(" ".join(variants), self.prefix, self.stopwords)
        with self.connect() as session:
            session.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
            vocab = self.vocabulary(session)
            words = query_words(" ".join(variants), self.stopwords)
            pool = {**params, "n": self.fts_pool}
            lexical: dict[tuple[str, int], float] = {}
            fts = (
                vocab.rerank(session.execute(FTS_SQL, {**pool, "q": q}).all(), words, self.per_list, lexical)
                if q
                else []
            )
            # One vector list over both forms: each row keeps its best similarity.
            best: dict[tuple[str, int], tuple] = {}
            for v in variants:
                vec = "[" + ",".join(f"{x:.6f}" for x in self._embed(v)) + "]"
                for r in self.nearest(session, {**params, "v": vec}, len(ids)):
                    key = (r[0], r[1])
                    if r[4] >= self.vector_floor and (key not in best or r[4] > best[key][4]):
                        best[key] = tuple(r)
            vector = sorted(best.values(), key=lambda r: -r[4])[: self.per_list]
            fixed = list(dict.fromkeys(c for w in words if (c := vocab.correct(w, self.fuzzy_floor))))
            fuzzy = (
                vocab.rerank(
                    session.execute(FTS_SQL, {**pool, "q": " | ".join(fixed)}).all(), fixed, self.per_list, lexical
                )
                if fixed
                else []
            )
        return fuse({"fts": fts, "vector": vector, "fuzzy": fuzzy}, self.k, lexical)

    def nearest(self, session: Session, params: dict, n_faults: int) -> list:
        """The per_list nearest candidate rows: exact for small candidate sets, HNSW (then exact if the filter left
        too few rows) for large ones."""
        if n_faults > EXACT_MAX_FAULTS:
            rows = session.execute(VECTOR_HNSW_SQL, params).all()
            if len(rows) >= params["n"]:
                return rows
        return session.execute(VECTOR_EXACT_SQL, params).all()

    def _search(self, query: str, ids: tuple[int, ...]) -> dict[int, Match]:
        return best_per_fault(self.hits(query, ids), self.k, vector_floor=self.vector_floor)

    def __call__(self, query: str, fault_ids: Iterable[int]) -> dict[int, Match]:
        return self._cached(query, tuple(sorted(set(fault_ids))))
