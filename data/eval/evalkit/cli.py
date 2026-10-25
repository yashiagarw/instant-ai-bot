"""`run_eval.py run` and `run_eval.py compare`. Fully offline: the database, the engine and (optionally) the
locally cached embedding model; no LLM or network calls."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from evalkit import report as rep
from evalkit.cases import chip_cases, load_yaml_cases, phrase_cases, safety_cases, split_of, unlisted_variants
from evalkit.metrics import summarise
from evalkit.versions import CURRENT, VersionError, engine_hash, git, git_info, materialise

EVAL_DIR = Path(__file__).resolve().parents[1]
RUN_EVAL = EVAL_DIR / "run_eval.py"
REPORT_MARK = "REPORT_JSON: "


def build_cases(knowledge, phrases, cases_dir: Path) -> list:
    """Every case type: dataset phrases (free text, typos, overlap), chips, safety rules, unlisted variants and the
    YAML files. Case ids are stable, so two runs can be compared case by case."""
    free = phrase_cases(knowledge, phrases)
    return [
        *free,
        *chip_cases(knowledge),
        *safety_cases(knowledge, knowledge.rules),
        *unlisted_variants(free),
        *load_yaml_cases(knowledge, cases_dir),
    ]


def make_search(kind: str):
    """Hybrid search on the configured database and the local model, or None for the keyword index."""
    if kind != "hybrid":
        return None
    from app.config import get_settings
    from app.db import make_engine, make_session_factory
    from app.diagnosis.search import HybridSearch
    from app.knowledge.importer.embed import SentenceTransformerEmbedder

    model = SentenceTransformerEmbedder()
    factory = make_session_factory(make_engine(get_settings().database_url))
    return HybridSearch(factory.begin, lambda t: model.encode([t])[0], model.name)


def evaluate(
    knowledge,
    cases,
    *,
    label: str,
    embeddings: bool,
    search: str = "keyword",
    diagnosis_engine: str = "v1",
    extra_meta: dict | None = None,
) -> dict:
    """Run the cases on the `engine` package this process imported and return the report (meta, summary,
    results)."""
    import engine as engine_pkg
    from engine import Engine
    from evalkit.runner import run_all

    embed = None
    if embeddings:
        from app.knowledge.importer.embed import SentenceTransformerEmbedder

        texts = sorted({c.text for c in cases if c.text} | {g.label for g in knowledge.groups.values()} - {""})
        vectors = dict(zip(texts, SentenceTransformerEmbedder().encode(texts), strict=True))
        embed = vectors.__getitem__
    hybrid = make_search(search)
    kwargs = {"embed": embed, **({"search": hybrid} if hybrid else {})}
    if diagnosis_engine == "v2":
        from engine import EngineV2  # not in engine versions before 2.0

        engine = EngineV2(knowledge, **kwargs)
    else:
        engine = Engine(knowledge, **kwargs)
    results = run_all(engine, cases)
    now = datetime.now(UTC)
    meta = {
        "created_at": now.isoformat(timespec="seconds"),
        "stamp": rep.timestamp(now),
        "engine_label": label,
        "engine_version": engine.version if hasattr(engine, "version") else engine_pkg.ENGINE_VERSION,
        "diagnosis_engine": diagnosis_engine,
        "engine_hash": engine_hash(Path(engine_pkg.__file__).parent),
        **git_info(),
        "dataset_version_id": knowledge.dataset_version_id,
        "embeddings": embeddings,
        "search": search,
        "vector_model": hybrid.model_name if hybrid else None,
        "cases": len(cases),
        "cases_by_type": dict(sorted(Counter(c.type for c in cases).items())),
        "cases_by_source": dict(sorted(Counter(c.source for c in cases).items())),
        **(extra_meta or {}),
    }
    return {"meta": meta, "summary": summarise(results), "results": results}


def _load(category: str | None, split: str = "all"):
    """Knowledge, held-out phrases (with language) and every case, from the configured database."""
    from run_eval import CASES_DIR, held_out_phrases

    from app.config import get_settings
    from app.db import make_engine, make_session_factory
    from app.diagnosis.knowledge import load_knowledge

    with make_session_factory(make_engine(get_settings().database_url))() as session:
        knowledge = load_knowledge(session)
        phrases = held_out_phrases(session, knowledge, with_language=True)
    cases = build_cases(knowledge, phrases, CASES_DIR)
    if category:
        cases = [c for c in cases if c.category == category]
    if split != "all":
        cases = [c for c in cases if split_of(c) == split]
    return knowledge, cases


def run_here(args) -> dict:
    knowledge, cases = _load(args.category, args.split)
    extra = {"category_filter": args.category} if args.category else {}
    extra["split"] = args.split
    if args.engine_ref:
        extra["engine_commit"] = args.engine_ref
    return evaluate(
        knowledge,
        cases,
        label=args.engine_label or CURRENT,
        embeddings=args.embeddings,
        search=args.search,
        diagnosis_engine=args.diagnosis_engine,
        extra_meta=extra,
    )


def run_version(spec: str, args, out: Path) -> dict:
    """Run an engine version and write its report; a git ref or folder runs in its own process."""
    if spec == CURRENT:
        args.engine_label = args.engine_label or CURRENT
        report = run_here(args)
        paths = rep.write(report, out)
        print(f"wrote {paths[1]}")
        return report
    path = materialise(spec)
    ref = None
    if not Path(spec).is_dir():
        ref = git("rev-parse", "--short", f"{spec}^{{commit}}")
    label = args.engine_label or spec
    cmd = [sys.executable, str(RUN_EVAL), "run", "--engine-path", str(path), "--engine-label", label, "--out", str(out)]
    cmd += ["--engine-ref", ref] if ref else []
    cmd += ["--embeddings"] if args.embeddings else []
    cmd += ["--search", args.search, "--diagnosis-engine", args.diagnosis_engine, "--split", args.split]
    cmd += ["--category", args.category] if args.category else []
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"engine {spec} failed (exit {proc.returncode})")
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith(REPORT_MARK))
    print(f"wrote {Path(line.removeprefix(REPORT_MARK)).with_suffix('.md')}")
    return json.loads(Path(line.removeprefix(REPORT_MARK)).read_text(encoding="utf-8"))


def _report_or_run(spec: str, args, out: Path) -> dict:
    if spec.endswith(".json") and Path(spec).is_file():
        return json.loads(Path(spec).read_text(encoding="utf-8"))
    return run_version(spec, args, out)


def print_summary(report: dict) -> None:
    m, s = report["meta"], report["summary"]
    print(
        f"\nEngine {m['engine_label']} (version {m['engine_version']}, code {m['engine_hash']}) · "
        f"dataset {m['dataset_version_id']} · {rep._search_label(m)} · {m['cases']} cases"
    )
    for line in rep._table(
        {
            "All": s["overall"],
            "Phase 1": s["phase1"],
            **{f"type: {k}": v for k, v in s["by_type"].items()},
            **{f"lang: {k}": v for k, v in s["by_language"].items()},
        },
        "Scope",
    ):
        print(line)


def harness(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="run_eval.py", description="Engine evaluation harness (offline)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="evaluate one engine version and write reports")
    run.add_argument("--engine", default=CURRENT, help="current (default), a git commit/tag/branch, or a folder")
    run.add_argument("--label", help="name for the run in the report and file name (default: the engine)")
    cmp = sub.add_parser("compare", help="evaluate two engine versions (or load two reports) and diff case by case")
    cmp.add_argument("--base", required=True, help="engine (current / git ref / folder) or a report .json")
    cmp.add_argument("--candidate", default=CURRENT, help="engine or report .json (default: current)")
    for p in (run, cmp):
        p.add_argument(
            "--embeddings", action="store_true", help="keyword search only: add the old embedding bonus (legacy)"
        )
        p.add_argument(
            "--diagnosis-engine",
            choices=["v1", "v2"],
            default=None,
            help="engine algorithm for current runs (default: DIAGNOSIS_ENGINE, as in the live app)",
        )
        p.add_argument(
            "--search",
            choices=["hybrid", "keyword"],
            default=None,
            help="free-text matching (default: DIAGNOSIS_SEARCH, as in the live app)",
        )
        p.add_argument("--category", help="only cases of this category")
        p.add_argument(
            "--split",
            choices=["all", "dev", "test"],
            default="all",
            help="dev (tune on it) or test (report on it); synthetic cases are always test",
        )
        p.add_argument("--out", type=Path, default=EVAL_DIR / "reports", help="report folder")
    # Internal: a child process running one engine version.
    run.add_argument("--engine-path", help=argparse.SUPPRESS)
    run.add_argument("--engine-label", help=argparse.SUPPRESS)
    run.add_argument("--engine-ref", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    from app.config import get_settings

    args.search = args.search or get_settings().diagnosis_search
    args.diagnosis_engine = args.diagnosis_engine or get_settings().diagnosis_engine

    try:
        if args.cmd == "run" and args.engine_path:  # child process
            report = run_here(args)
            jpath, _ = rep.write(report, args.out)
            print(REPORT_MARK + str(jpath))
            return
        if args.cmd == "run":
            args.engine_label = args.label or (None if args.engine == CURRENT else args.engine)
            args.engine_ref = None
            print_summary(run_version(args.engine, args, args.out))
            return
        args.engine_label = args.engine_ref = None
        base = _report_or_run(args.base, args, args.out)
        args.engine_label = None
        cand = _report_or_run(args.candidate, args, args.out)
        result = rep.compare(base, cand)
        _, mpath = rep.write(result, args.out, kind="compare")
        verdicts = Counter(ch["verdict"] for ch in result["changes"])
        print(
            f"\n{len(result['changes'])} cases changed ({dict(verdicts)}); "
            f"overall: {result['overall'] or 'no metric changed'}"
        )
        print(f"wrote {mpath}")
    except VersionError as e:
        raise SystemExit(str(e)) from e
