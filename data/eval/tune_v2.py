"""Tune engine v2 on the DEV split only (never the test split; synthetic cases are always test).

Stage 1: structure (hard narrowing on the main complaint, several categories or not) at default maths.
Stage 2: text strength x answer sharpness at the best structure.
Stage 3: stopping thresholds at the best maths.
Prints each configuration's dev numbers next to v1's.

Run from backend/:  uv run python ../data/eval/tune_v2.py
"""

import os
import sys
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parents[1] / "backend"))
sys.path.insert(0, str(EVAL_DIR))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from evalkit.cli import _load, make_search  # noqa: E402
from evalkit.metrics import stats  # noqa: E402
from evalkit.runner import run_all  # noqa: E402

from engine import Engine, EngineV2  # noqa: E402


def row(name: str, results: list[dict], seconds: float) -> dict:
    s = stats(results)
    ft = stats([r for r in results if r["type"] == "free_text"])
    out = {
        "name": name,
        "top1": s["top1"],
        "top3": s["top3"],
        "ft_top3": ft["top3"],
        "qs": s["avg_questions"],
        "safety": s["safety_recall"],
        "flow": s["flow_safety_recall"],
    }
    print(
        f"{name:52s} top1 {100 * out['top1']:5.1f} top3 {100 * out['top3']:5.1f} free-text top3 "
        f"{100 * out['ft_top3']:5.1f} qs {out['qs']:4.2f} safety {100 * out['safety']:5.1f} "
        f"flow {100 * out['flow']:5.1f}  ({seconds:.0f}s)",
        flush=True,
    )
    return out


def focus(knowledge, cases, search):
    """Information gain over all candidates or only the N most likely ones (after the tuned settings)."""
    for n in (None, 10, 5):
        t = time.time()
        row(
            f"v2 tuned, focus_top={n}", run_all(EngineV2(knowledge, search=search, focus_top=n), cases), time.time() - t
        )


def main():
    knowledge, cases = _load(None, "dev")
    search = make_search("hybrid")
    print(f"dev split: {len(cases)} cases (hybrid search)", flush=True)
    if "--focus" in sys.argv:
        return focus(knowledge, cases, search)

    def run(name, engine):
        t = time.time()
        return row(name, run_all(engine, cases), time.time() - t)

    run("v1", Engine(knowledge, search=search))

    def v2(**kw):
        return EngineV2(knowledge, search=search, **kw)

    stage1 = [
        run(f"v2 hard_narrow={hn} multi_category={mc}", v2(hard_narrow=hn, multi_category=mc))
        for hn in (False, True)
        for mc in (True, False)
    ]
    best1 = max(stage1, key=lambda r: (r["top3"], r["top1"]))
    hn = "hard_narrow=True" in best1["name"]
    mc = "multi_category=True" in best1["name"]
    print(f"-> structure: hard_narrow={hn} multi_category={mc}", flush=True)

    stage2 = []
    for ts in (3.0, 6.0, 9.0):
        for beta in (0.7, 1.0, 1.5):
            name = f"v2 hn={hn} mc={mc} text_strength={ts} beta={beta}"
            stage2.append((run(name, v2(hard_narrow=hn, multi_category=mc, text_strength=ts, beta=beta)), ts, beta))
    best2, ts, beta = max(stage2, key=lambda x: (x[0]["top3"], x[0]["top1"]))
    print(f"-> maths: text_strength={ts} beta={beta}", flush=True)

    for sp, sm in ((0.6, 0.4), (0.75, 0.5), (0.9, 0.6)):
        defaults = {"stop_probability": sp, "stop_margin": sm}
        run(
            f"v2 best maths, stop_probability={sp} stop_margin={sm}",
            v2(hard_narrow=hn, multi_category=mc, text_strength=ts, beta=beta, defaults=defaults),
        )


if __name__ == "__main__":
    main()
