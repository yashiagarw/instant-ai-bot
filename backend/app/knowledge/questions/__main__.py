"""Offline question structuring (never called by the live app).

uv run python -m app.knowledge.questions generate --category battery [--category ac ...] [--phase1]
uv run python -m app.knowledge.questions status
uv run python -m app.knowledge.questions diff --category battery
uv run python -m app.knowledge.questions load --category battery   (or --all)
"""

import argparse
import sys
import time
from datetime import UTC, datetime

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.knowledge.importer.config import REPO_ROOT, load_config
from app.knowledge.questions import review
from app.knowledge.questions.generate import generate_category
from app.knowledge.questions.inputs import category_inputs, target_version
from app.knowledge.questions.llm import PROVIDERS, LLMError, make_provider
from app.knowledge.questions.loader import ReviewFileError, load_document
from app.knowledge.questions.prompts import PROMPT_VERSION


def phase1_categories() -> list[str]:
    return [c["code"] for c in load_config().taxonomy["categories"] if c["wave"] == 1]


def provider_name(args, settings) -> str:
    """--provider wins; otherwise LLM_PROVIDER from backend/.env."""
    return args.provider or settings.llm_provider


def cmd_generate(args, session) -> int:
    settings = get_settings()
    categories = phase1_categories() if args.phase1 else args.category
    if not categories:
        print("Give --category CODE (repeatable) or --phase1", file=sys.stderr)
        return 2
    try:
        provider = make_provider(
            provider_name(args, settings), settings, model=args.model or "", effort=args.effort or ""
        )
    except LLMError as e:
        print(f"Cannot start: {e}", file=sys.stderr)
        return 2
    version = target_version(session)
    dataset = {"id": version.id, "checksum": version.checksum}
    failures = 0
    for code in categories:
        inputs = category_inputs(session, version, code)
        print(
            f"{code}: {len(inputs['faults'])} faults, choices from "
            f"{'file' if inputs['file_choices'] else 'model'}, draft safety rules: {inputs['draft_safety']}"
        )
        before = provider.usage.as_dict(provider.model)
        started = time.time()
        try:
            doc = generate_category(inputs, provider, dataset, workers=args.workers)
        except LLMError as e:
            print(f"  failed: {e}", file=sys.stderr)
            failures += 1
            continue
        path = review.write_draft(doc)
        after = provider.usage.as_dict(provider.model)
        delta = {k: after[k] - before[k] for k in after if isinstance(after[k], int) and k in before}
        usage = {**delta, "served_by": after["served_by"]}
        usage["cost_usd_estimate"] = (
            round(after["cost_usd_estimate"] - (before["cost_usd_estimate"] or 0), 4)
            if after["cost_usd_estimate"] is not None
            else None
        )
        errors = [k for k, v in doc["faults"].items() if v.get("error")]
        review.log_run(
            {
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
                "run_id": doc["generated"]["run_id"],
                "category": code,
                "provider": provider.name,
                "model": provider.model,
                "effort": getattr(provider, "effort", None),
                "prompt_version": PROMPT_VERSION,
                "dataset_version": version.id,
                "seconds": round(time.time() - started, 1),
                "faults": len(inputs["faults"]),
                "questions": len(doc["questions"]),
                "fault_errors": errors,
                "usage": usage,
                "output": str(path.relative_to(REPO_ROOT)),
            }
        )
        print(
            f"  wrote {path.relative_to(REPO_ROOT)}: {len(doc['questions'])} questions, "
            f"{len(doc.get('safety_rules', []))} drafted safety rules, {len(errors)} fault errors"
        )
        print(
            f"  tokens in {usage['input_tokens']} (+{usage['cache_read_input_tokens']} cached, "
            f"{usage['cache_creation_input_tokens']} cache writes), out {usage['output_tokens']}, "
            f"{usage['calls']} calls, ~${usage['cost_usd_estimate']}"
        )
    total = provider.usage.as_dict(provider.model)
    print(
        f"Total: {total['calls']} calls, in {total['input_tokens']}, out {total['output_tokens']}, "
        f"~${total['cost_usd_estimate']} ({provider.model}). Log: data/review/questions/runs.jsonl"
    )
    return 1 if failures else 0


def cmd_status(args, session) -> int:
    files = sorted(p for p in review.QUESTIONS_DIR.glob("*.yaml"))
    if not files:
        print("No review files yet. Run: python -m app.knowledge.questions generate --phase1")
    for path in files:
        doc = review.read(path)
        counts = review.status_counts(doc)
        loaded = "loaded" if review.snapshot_path(doc["category"]).exists() else "never loaded"
        print(
            f"{path.name:28} draft {counts['draft']:3}  approved {counts['approved']:3}  "
            f"rejected {counts['rejected']:3}  ({loaded})"
        )
    return 0


def cmd_diff(args, session) -> int:
    for code in args.category or []:
        print(review.diff(code))
    return 0


def cmd_load(args, session) -> int:
    codes = (
        [p.stem for p in review.QUESTIONS_DIR.glob("*.yaml") if not p.stem.endswith(".new")]
        if args.all
        else (args.category or [])
    )
    if not codes:
        print("Give --category CODE or --all", file=sys.stderr)
        return 2
    docs = {}
    for code in codes:
        path = review.path_for(code)
        if not path.exists():
            print(f"{code}: no review file {path}", file=sys.stderr)
            return 1
        docs[code] = review.read(path)
    try:
        for code, doc in docs.items():
            report = load_document(session, doc)
            print(
                f"{code}: {report.questions} questions, {report.options} options, {report.effects} effects, "
                f"{report.faults_updated} faults, {report.safety_rules} safety rules, "
                f"{report.triggers_attached} sheet-rule triggers"
            )
            for s in report.skipped_effects:
                print(f"  skipped: {s}")
    except ReviewFileError as e:
        print(f"Not loaded: {e}", file=sys.stderr)
        raise
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.knowledge.questions", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate", help="draft questions with the LLM into data/review/questions/")
    g.add_argument("--category", action="append")
    g.add_argument("--phase1", action="store_true", help="all wave-1 categories (BT SS NS OH AC CL BR TY)")
    g.add_argument("--provider", choices=PROVIDERS, help="default: LLM_PROVIDER from backend/.env")
    g.add_argument("--model", help="default: QUESTIONS_MODEL (anthropic) or OPENAI_MODEL (openai)")
    g.add_argument(
        "--effort",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="default: QUESTIONS_EFFORT (anthropic) or OPENAI_REASONING_EFFORT (openai)",
    )
    g.add_argument("--workers", type=int, default=6, help="parallel calls per category")
    sub.add_parser("status", help="draft / approved / rejected counts per review file")
    d = sub.add_parser("diff", help="approved entries now vs the last load")
    d.add_argument("--category", action="append", required=True)
    ld = sub.add_parser("load", help="load approved entries into the live tables")
    ld.add_argument("--category", action="append")
    ld.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = make_engine(settings.database_url, settings.db_connect_timeout)
    handler = {"generate": cmd_generate, "status": cmd_status, "diff": cmd_diff, "load": cmd_load}[args.command]
    try:
        with make_session_factory(engine)() as session, session.begin():
            code = handler(args, session)
    except ReviewFileError:
        return 1
    finally:
        engine.dispose()
    # Snapshots are written only after the load transaction committed.
    if args.command == "load" and code == 0:
        for code_ in (
            [p.stem for p in review.QUESTIONS_DIR.glob("*.yaml") if not p.stem.endswith(".new")]
            if args.all
            else args.category
        ):
            review.save_snapshot(review.read(review.path_for(code_)))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
