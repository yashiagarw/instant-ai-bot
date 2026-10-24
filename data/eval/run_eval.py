"""Evaluate the diagnosis engine.

1. Every held-out customer phrase (never indexed by the engine). Expected fault = the phrase's own row.
   Two modes: free text only (no tile), and tile known (the first tile / emergency topic holding the category).
2. Every YAML case in data/eval/cases/*.yaml (format: see cases/README.md).
3. With --simulate: a simulated conversation per held-out phrase. The flow starts from the phrase as free text;
   a simulated customer who knows the true fault picks the true category when routing offers it and answers
   each question with the option that supports the true fault most ("Not sure" if none does). Reports top-1 /
   top-3 after the flow, average questions asked, safety-alert recall, and the most confused fault pairs.

Prints top-1 / top-3 accuracy per category, Phase 1 (wave 1) categories separately.

Run from backend/:  uv run python ../data/eval/run_eval.py [--simulate] [--no-embeddings] [--category CODE]

Harness (reports with a timestamp in data/eval/reports/, see data/eval/README.md):
  uv run python ../data/eval/run_eval.py run [--engine current|<git ref>|<folder>] [--embeddings] [--category CODE]
  uv run python ../data/eval/run_eval.py compare --base <engine or report.json> --candidate <engine or report.json>
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(EVAL_DIR))
# `run --engine-path DIR` (used for git refs): that engine package wins over backend/engine.
if "--engine-path" in sys.argv:
    sys.path.insert(0, sys.argv[sys.argv.index("--engine-path") + 1])
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # the model is already cached by the importer

from evalkit.cases import load_yaml_cases  # noqa: E402
from evalkit.runner import run_case  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.diagnosis.knowledge import load_knowledge  # noqa: E402
from app.enums import ReviewStatus  # noqa: E402
from app.knowledge.models import CustomerPhrase  # noqa: E402
from engine import ENGINE_VERSION, Engine, Request, Vehicle  # noqa: E402
from engine.simulate import confused_pairs, has_safety_rule, has_triggered_rule, simulate  # noqa: E402

CASES_DIR = EVAL_DIR / "cases"
REPORTS_DIR = EVAL_DIR / "reports"


def held_out_phrases(session, knowledge, with_language: bool = False) -> list[tuple]:
    """(text, expected fault id[, language tag]). A phrase of a folded duplicate expects its canonical fault."""
    rows = session.execute(
        select(CustomerPhrase.text, CustomerPhrase.fault_id, CustomerPhrase.language).where(
            CustomerPhrase.held_out.is_(True),
            CustomerPhrase.status == ReviewStatus.approved,
            CustomerPhrase.fault_id.in_(list(knowledge.faults) + list(knowledge.alias_of)),
        )
    )
    out = []
    for t, fid, lang in rows:
        fid = fid if fid in knowledge.faults else knowledge.canonical(fid)
        out.append((t, fid, str(lang) if lang else None) if with_language else (t, fid))
    return out


def group_for(knowledge, category: str) -> str | None:
    for gtype in ("tile", "emergency", "inspection"):
        for g in knowledge.groups.values():
            if g.group_type == gtype and category in g.categories:
                return g.code
    return None


KNOWLEDGE = None  # set in main(); merged duplicates count as the same fault


def hit(result, fault_id: int, k: int) -> bool:
    """The expected fault, or a merged duplicate of it, is in the top k."""
    same = KNOWLEDGE.canonical if KNOWLEDGE else (lambda f: f)
    return same(fault_id) in [same(r.fault_id) for r in result.ranked[:k]]


def load_cases(knowledge) -> list:
    """YAML cases with an expected fault (the harness runs every case type; this console mode prints these)."""
    return [c for c in load_yaml_cases(knowledge, CASES_DIR) if c.expected]


def table(title: str, rows: dict[str, dict], cols: list, waves: dict[str, float]):
    """cols: "key" (percent of n) or (label, key, denominator key, percent?)."""
    specs = [(c, c, "n", True) if isinstance(c, str) else c for c in cols]

    def fmt(stats):
        out = [f"{stats['n']:5d}"]
        for _, key, denom, percent in specs:
            d = stats[denom]
            out.append("     -" if not d else f"{(100 if percent else 1) * stats[key] / d:6.1f}")
        return out

    header = f"{'category':20s} {'n':>5s} " + " ".join(f"{label:>6s}" for label, *_ in specs)
    for label, keep in (("Phase 1 (wave 1)", lambda w: w == 1), ("Other categories", lambda w: w != 1)):
        cats = sorted(c for c in rows if keep(waves.get(c, 9)))
        if not cats:
            continue
        print(f"\n{title} - {label}\n{header}")
        total = defaultdict(int)
        for c in cats:
            print(f"{c:20s} " + " ".join(fmt(rows[c])))
            for key, v in rows[c].items():
                total[key] += v
        print(f"{'TOTAL':20s} " + " ".join(fmt(total)))


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("run", "compare"):
        from evalkit.cli import harness

        return harness(sys.argv[1:])
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-embeddings", action="store_true", help="keyword matching only")
    ap.add_argument("--category", help="only this category")
    ap.add_argument("--simulate", action="store_true", help="also run simulated conversations")
    ap.add_argument("--pairs", type=int, default=15, help="confused fault pairs to list (with --simulate)")
    args = ap.parse_args()

    global KNOWLEDGE
    with make_session_factory(make_engine(get_settings().database_url))() as session:
        knowledge = KNOWLEDGE = load_knowledge(session)
        phrases = held_out_phrases(session, knowledge)
    if args.category:
        phrases = [(t, fid) for t, fid in phrases if knowledge.faults[fid].category == args.category]

    cases = load_cases(knowledge)
    vectors = {}
    if not args.no_embeddings:
        from app.knowledge.importer.embed import SentenceTransformerEmbedder

        texts = sorted(
            {t for t, _ in phrases}
            | {c.get("text", "") for c in cases}
            | {g.label for g in knowledge.groups.values()} - {""}
        )
        vectors = dict(zip(texts, SentenceTransformerEmbedder().encode(texts), strict=True))
    engine = Engine(knowledge, embed=(lambda t: vectors[t]) if vectors else None)
    waves = {c: cat.wave for c, cat in knowledge.categories.items()}

    rows: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for text, fid in phrases:
        cat = knowledge.faults[fid].category
        s = rows[cat]
        s["n"] += 1
        free = engine.diagnose(Request(text=text))
        s["txt@1"] += hit(free, fid, 1)
        s["txt@3"] += hit(free, fid, 3)
        s["cat@3"] += cat in [c.code for c in free.suggested_categories]
        group = group_for(knowledge, cat)
        tiled = engine.diagnose(Request(text=text, group=group) if group else Request(text=text, category=cat))
        s["tile@1"] += hit(tiled, fid, 1)
        s["tile@3"] += hit(tiled, fid, 3)

    print(
        f"Engine {ENGINE_VERSION} | dataset version {knowledge.dataset_version_id} | "
        f"embeddings {'on' if vectors else 'off'} | {len(phrases)} held-out phrases"
    )
    print("txt = free text only, tile = tile known, cat@3 = right category among the 3 suggested (free text)")
    table("Held-out phrases", rows, ["txt@1", "txt@3", "tile@1", "tile@3", "cat@3"], waves)

    if args.simulate:
        emergency_check(engine, knowledge)
        run_simulation(engine, knowledge, phrases, waves, args.pairs)

    if cases:
        crow: dict[str, dict] = defaultdict(lambda: defaultdict(int))
        print(f"\nYAML cases ({len(cases)})")
        for c in cases:
            r = run_case(engine, c)
            s = crow[c.category]
            s["n"] += 1
            s["top1"] += r["hit1"]
            s["top3"] += r["hit3"]
            mark = "ok " if r["hit1"] else "top3" if r["hit3"] else "MISS"
            print(f"  [{mark}] {c.id}: expected {'/'.join(c.expected)}, got {(r['got'] or ['-'])[0]}")
        table("YAML cases", crow, ["top1", "top3"], waves)


def emergency_check(engine, knowledge):
    """Every emergency topic, for each fuel and with / without free text: tips and live rules shown."""
    print(
        "\nEmergency topics (fast_track): tips shown for every fuel (unknown, petrol, diesel, cng, hybrid, ev), "
        "without and with free text"
    )
    print(f"{'topic':16s} {'categories':32s} {'live rules':>10s} {'min tips':>8s} {'max tips':>8s}")
    for g in sorted((g for g in knowledge.groups.values() if g.group_type == "emergency"), key=lambda g: g.code):
        counts, cats = [], set()
        for fuel in (None, "petrol", "diesel", "cng", "hybrid", "ev"):
            for text in ("", g.label):
                r = engine.diagnose(Request(group=g.code, text=text, vehicle=Vehicle(fuel=fuel)))
                counts.append(len(r.safety_tips))
                cats |= set(r.active_categories)
        rules = sum(
            1 for x in engine.rules if x.fault_id in knowledge.faults and knowledge.faults[x.fault_id].category in cats
        )
        flag = "" if min(counts) else "  <- NO TIPS"
        print(f"{g.code:16s} {','.join(sorted(cats)):32s} {rules:10d} {min(counts):8d} {max(counts):8d}{flag}")


def run_simulation(engine, knowledge, phrases, waves, n_pairs=15):
    rows: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    mistakes: list[tuple[int, int]] = []
    key_ids = {f.key: f.id for f in knowledge.faults.values()}
    for text, fid in phrases:
        fault = knowledge.faults[fid]
        sim = simulate(engine, fault, text)
        s = rows[fault.category]
        s["n"] += 1
        s["top1"] += hit(sim.result, fid, 1)
        s["top3"] += hit(sim.result, fid, 3)
        s["asked"] += sim.result.questions_asked
        if sim.result.mode == "fast_track":
            s["ft_n"] += 1
            s["ft_tips"] += bool(sim.result.safety_tips)
        s["done"] += sim.result.done
        # A rule of the fault or of a merged duplicate of it (same fault, other category) fired.
        fired = any(knowledge.canonical(key_ids[key]) == knowledge.canonical(fid) for key in sim.alert_fault_keys)
        if has_triggered_rule(engine, fault):
            s["safe_n"] += 1
            s["safe_hit"] += fired
        if has_safety_rule(engine, fault):
            s["rule_n"] += 1
            s["rule_hit"] += fired
            if hit(sim.result, fid, 3):
                s["rule_top3"] += 1
                s["rule_top3_hit"] += fired
        if sim.result.ranked and not hit(sim.result, fid, 1):
            mistakes.append((fid, sim.result.ranked[0].fault_id))

    print("\nSimulated conversations: free text, then the true category and supporting answers")
    print(
        "q/avg = average questions asked (routing not counted), done = flow finished, "
        "safe = sessions whose true fault has a live triggered rule, recall = its alert fired;\n"
        "rules = sessions whose true fault has any live rule, rec/all = its alert fired, "
        "rec/t3 = same, when the true fault ended in the top 3;\n"
        "ft = sessions that ended in fast_track mode, ftTips = of those, safety tips shown"
    )
    cols = [
        "top1",
        "top3",
        ("q/avg", "asked", "n", False),
        "done",
        ("safe", "safe_n", "n", True),
        ("recall", "safe_hit", "safe_n", True),
        ("rules", "rule_n", "n", True),
        ("rec/all", "rule_hit", "rule_n", True),
        ("rec/t3", "rule_top3_hit", "rule_top3", True),
        ("ft", "ft_n", "n", True),
        ("ftTips", "ft_tips", "ft_n", True),
    ]
    table("Simulated conversations", rows, cols, waves)

    print(f"\nMost confused fault pairs (wrong top-1 after the flow, both directions; {len(mistakes)} mistakes)")
    print("sep = approved questions that separate the two, name = name word overlap, shared = identical phrases")
    print(f"{'count':>5s} {'sep':>3s} {'name':>4s} {'shared':>6s}  near-dup  faults")
    for p in confused_pairs(knowledge, mistakes, top=n_pairs):
        flag = "  YES   " if p.near_duplicate else "        "
        print(
            f"{p.count:5d} {p.separating:3d} {p.name_sim:4.2f} {p.shared_phrases:6d} {flag}  "
            f"{p.a.key} {p.a.name}  <->  {p.b.key} {p.b.name}"
        )


if __name__ == "__main__":
    main()
