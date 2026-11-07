"""The eval gate in CI (Phase 5.6), with the same evaluation and gate as the dataset publish pipeline
(app.datasets.evaluation): the engine and dataset of a commit against a baseline report from `main`.

    python -m app.datasets.ci_eval run --scope quick --out eval.json     # quick: every danger case + the test split
    python -m app.datasets.ci_eval run --scope full --out eval.json      # full: every case (nightly)
    python -m app.datasets.ci_eval gate --candidate eval.json --baseline main.json [--summary file.md]

The database must hold the imported datasets (scripts/ci/eval-db.sh). `gate` fails (exit 1) when more danger cases
are missed than in the baseline (on the cases both have) or top-3 accuracy drops more than 3 points: the publish
gate's rules. Cases are matched by keys that are the same in every dataset version (evaluation.case_key), so a
baseline from an earlier commit or another database compares like for like.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app.config import get_settings
from app.datasets import evaluation
from app.datasets.pipeline import live_version
from app.datasets.worker import make_pipeline
from app.db import make_engine, make_session_factory
from app.knowledge.embeddings import version_model

SCOPES = {
    "quick": {"categories": None, "split": "test", "full": False, "danger_all": True},
    "full": {"categories": None, "split": "all", "full": True},
}


def run(scope_name: str, out: Path) -> dict:
    settings = get_settings()
    started = time.monotonic()
    factory = make_session_factory(make_engine(settings.database_url))
    # The publish pipeline's own set-up (engine, hybrid search with the version's model, real cases).
    pipe = make_pipeline(settings, factory)
    with factory() as session:
        version = live_version(session)
        if version is None:
            raise SystemExit("no dataset version in the database: run scripts/ci/eval-db.sh first")
        report = evaluation.run_eval(
            session,
            version,
            SCOPES[scope_name],
            diagnosis_engine=pipe.diagnosis_engine,
            search=pipe.search_factory(version_model(version)),
            real_dir=pipe.real_cases_dir,
            progress=lambda done, total: print(f"  {done}/{total} cases", flush=True) if done % 500 == 0 else None,
        )
    report["scope"] = scope_name
    report["seconds"] = round(time.monotonic() - started)
    out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    o = report["overall"]
    missed = round(o["safety_n"] * (1 - (o["safety_recall"] or 0)))
    danger = evaluation.missed_text({**o, "safety_missed": missed})
    print(f"{scope_name}: {report['cases']} cases in {report['seconds']} s · top-3 {o['top3']} · {danger}")
    return report


def gate(candidate: Path, baseline: Path | None, summary: Path | None) -> bool:
    cand = json.loads(candidate.read_text(encoding="utf-8"))
    base = json.loads(baseline.read_text(encoding="utf-8")) if baseline and baseline.is_file() else None
    if base is not None and base.get("scope") != cand.get("scope"):
        print(f"baseline scope {base.get('scope')} differs from {cand.get('scope')}: compared on common cases only")
    result = evaluation.gate(cand, base)
    lines = ["### Eval gate (safety recall and top-3, as the publish gate)", ""]
    if base is None:
        lines.append("No baseline report from `main` yet: nothing to compare with (passes). It is created by the next "
                     "run on `main`.")  # fmt: skip
    else:
        cmp = evaluation.compare(cand, base)
        d, c = cmp["draft"], cmp["live"]
        pts = evaluation._points  # noqa: SLF001 - same formatting as the admin Datasets page
        lines += [
            f"Compared on the {cmp['common']} cases both have ({cand.get('scope')} scope).",
            "",
            "| | main (baseline) | this commit |",
            "|---|---|---|",
            f"| Danger cases | {evaluation.missed_text(c)} | {evaluation.missed_text(d)} |",
            f"| Top-3 accuracy | {pts(c['top3'])}% | {pts(d['top3'])}% |",
            f"| Top-1 accuracy | {pts(c['top1'])}% | {pts(d['top1'])}% |",
        ]
        changed = cmp["safety_changed"]
        if changed:
            lines += ["", "Danger cases that changed:", ""]
            lines += [f"- {x['label']}: {x['live']} on main, {x['draft']} here" for x in changed[:50]]
    lines += ["", "**Passed.**" if result["ok"] else "**Failed:**"]
    lines += [f"- {r}" for r in result["reasons"]]
    text = "\n".join(lines) + "\n"
    print(text)
    if summary:
        with summary.open("a", encoding="utf-8") as f:
            f.write(text)
    return result["ok"]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.datasets.ci_eval", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="evaluate the served dataset version with this commit's engine")
    r.add_argument("--scope", choices=sorted(SCOPES), default="quick")
    r.add_argument("--out", type=Path, required=True)
    g = sub.add_parser("gate", help="compare a report with the baseline from main; exit 1 when the gate fails")
    g.add_argument("--candidate", type=Path, required=True)
    g.add_argument("--baseline", type=Path)
    g.add_argument("--summary", type=Path, help="append the result as Markdown (e.g. $GITHUB_STEP_SUMMARY)")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        run(args.scope, args.out)
    elif not gate(args.candidate, args.baseline, args.summary):
        sys.exit(1)


if __name__ == "__main__":
    main()
