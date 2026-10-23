"""CLI: uv run python -m app.knowledge.importer --all | --file PATH [--no-embeddings]"""

import argparse
import sys
import time
from pathlib import Path

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.knowledge.importer.config import REPO_ROOT, load_config
from app.knowledge.importer.run import run_import, summary_table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.knowledge.importer",
        description="Import the Excel datasets in data/raw/ into the knowledge tables.",
    )
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true", help="import every file listed in data/schema/manifest.yaml")
    which.add_argument("--file", type=Path, action="append", help="import one file (repeatable)")
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="skip sentence-transformers (faster). Re-imported rows then have no vectors, "
        "so vectors from an earlier run are lost.",
    )
    args = parser.parse_args(argv)

    config = load_config()
    if args.all:
        entries = list(config.files.values())
    else:
        entries = [config.entry_for_path(p if p.is_absolute() else (Path.cwd() / p)) for p in args.file]
    missing = [e.path for e in entries if not e.path.exists()]
    if missing:
        print(f"Missing files: {missing}", file=sys.stderr)
        return 1

    embedder = None
    if not args.no_embeddings:
        from app.knowledge.importer.embed import SentenceTransformerEmbedder

        print("Loading embedding model ...")
        embedder = SentenceTransformerEmbedder()

    settings = get_settings()
    engine = make_engine(settings.database_url, settings.db_connect_timeout)
    started = time.time()
    # One transaction: a failure leaves the database exactly as it was.
    with make_session_factory(engine)() as session, session.begin():
        result = run_import(session, config, entries, all_files=args.all, embedder=embedder)
        reports = [r.as_dict() for r in result.reports.values()]
        version = result.version
        print()
        print(summary_table(reports))
        print()
        print(f"Dataset version {version.id}: {version.status}, checksum {version.checksum[:16]}…")
        print(
            f"Cross-reference links {result.links}, embeddings {result.embedded}, duplicate candidates "
            f"{result.duplicates}"
        )
        print("Review files: " + ", ".join(str(p.relative_to(REPO_ROOT)) for p in result.review_files))
    print(f"Done in {time.time() - started:.0f}s")
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
