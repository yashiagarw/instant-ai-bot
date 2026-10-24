"""Tune free-text matching on TRAINING phrases (leave-one-out), never on the evaluation cases.

Each sampled training phrase (not held out) is searched with its own row left out (and its English gloss, in the
keyword index); the expected fault is the phrase's fault. Prints top-1 / top-3 over all faults and within the
phrase's category for: the engine's keyword index, hybrid search (current settings, with a few variants), and the
two combined (each fault keeps its better score, as the engine does).

Run from backend/:  uv run python ../data/eval/tune_search.py [--sample 600]
"""

import argparse
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.diagnosis.knowledge import load_knowledge  # noqa: E402
from app.diagnosis.search import RRF_K, VECTOR_FLOOR, WEIGHTS, Hit, HybridSearch, best_per_fault  # noqa: E402
from app.enums import ReviewStatus  # noqa: E402
from app.knowledge.importer.embed import MODEL_NAME, SentenceTransformerEmbedder  # noqa: E402
from app.knowledge.models import CustomerPhrase  # noqa: E402
from engine.text import TextIndex  # noqa: E402

VARIANTS = {  # name -> (RRF k, list weights)
    "hybrid (current)": (RRF_K, WEIGHTS),
    "hybrid, equal weights": (RRF_K, {"fts": 1.0, "vector": 1.0, "fuzzy": 1.0}),
    "hybrid, k=60": (60, WEIGHTS),
    "hybrid, no vectors": (RRF_K, {"fts": 1.0, "vector": 0.0, "fuzzy": 1.0}),
}


def ranked(scores: dict[int, float]) -> list[int]:
    return [f for f, _ in sorted(scores.items(), key=lambda x: -x[1])]


def keyword_scores(index: TextIndex, kw: dict[int, float], allowed: set[int]) -> dict[int, float]:
    best: dict[int, float] = {}
    for i, v in kw.items():
        fid = index.entries[i].fault_id
        if fid in allowed and v > best.get(fid, 0.0):
            best[fid] = v
    return best


def hybrid_scores(hits: list[Hit], k: int, weights: dict[str, float]) -> dict[int, float]:
    return {f: m.score for f, m in best_per_fault(hits, k, weights, VECTOR_FLOOR).items()}


def combined(a: dict[int, float], b: dict[int, float]) -> dict[int, float]:
    return {f: max(a.get(f, 0.0), b.get(f, 0.0)) for f in a.keys() | b.keys()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=600)
    args = ap.parse_args()
    factory = make_session_factory(make_engine(get_settings().database_url))
    with factory() as s:
        k = load_knowledge(s)
        rows = s.execute(
            select(CustomerPhrase.id, CustomerPhrase.text, CustomerPhrase.fault_id, CustomerPhrase.english_gloss).where(
                CustomerPhrase.held_out.is_(False),
                CustomerPhrase.status == ReviewStatus.approved,
                CustomerPhrase.fault_id.in_(list(k.faults)),
            )
        ).all()
    sample = random.Random(7).sample(sorted(rows), min(args.sample, len(rows)))
    model = SentenceTransformerEmbedder()
    search = HybridSearch(factory.begin, lambda t: model.encode([t])[0], MODEL_NAME)
    index = TextIndex(k.texts)
    entry = {(e.fault_id, e.text): i for i, e in enumerate(k.texts) if e.kind == "phrase"}
    all_ids = set(k.faults)
    by_cat: dict[str, set[int]] = {}
    for f in k.faults.values():
        by_cat.setdefault(f.category, set()).add(f.id)

    same = k.canonical
    tally: dict[str, list[int]] = {}

    def record(name: str, fid: int, everywhere: list[int], within: list[int]) -> None:
        t = tally.setdefault(name, [0, 0, 0, 0])
        t[0] += bool(everywhere) and same(everywhere[0]) == same(fid)
        t[1] += same(fid) in [same(x) for x in everywhere[:3]]
        t[2] += bool(within) and same(within[0]) == same(fid)
        t[3] += same(fid) in [same(x) for x in within[:3]]

    for pid, text, fid, gloss in sample:
        cat = by_cat[k.faults[fid].category]
        left_out = {entry.get((fid, text)), entry.get((fid, gloss or ""))} - {None}
        kw = {i: v for i, v in index.keyword_scores(text).items() if i not in left_out}
        kw_all, kw_cat = keyword_scores(index, kw, all_ids), keyword_scores(index, kw, cat)
        record("keyword index", fid, ranked(kw_all), ranked(kw_cat))
        hits_all, hits_cat = search.hits(text, all_ids, exclude=[pid]), search.hits(text, cat, exclude=[pid])
        for name, (kk, weights) in VARIANTS.items():
            h_all, h_cat = hybrid_scores(hits_all, kk, weights), hybrid_scores(hits_cat, kk, weights)
            record(name, fid, ranked(h_all), ranked(h_cat))
            if name == "hybrid (current)":
                record(
                    "keyword + hybrid (engine)", fid, ranked(combined(kw_all, h_all)), ranked(combined(kw_cat, h_cat))
                )

    n = len(sample)
    print(f"{n} training phrases, leave-one-out      all faults top1  top3 | within category top1  top3")
    for name, t in tally.items():
        print(f"{name:40s} {100 * t[0] / n:16.1f} {100 * t[1] / n:5.1f} | {100 * t[2] / n:20.1f} {100 * t[3] / n:5.1f}")


if __name__ == "__main__":
    main()
