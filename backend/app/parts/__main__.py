"""CLI for the parts catalogue (run after the importer and `python -m app.knowledge.merges apply`):

uv run python -m app.parts review   # write data/review/parts/F??.csv and F09-fault-links.csv for approval
uv run python -m app.parts build    # build the catalogue for the target dataset version and print results
"""

import argparse
import sys

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.knowledge.questions.inputs import target_version
from app.parts.build import REPO_ROOT, build, table
from app.parts.review import f09_links_review, segment_review


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.parts")
    ap.add_argument("command", choices=["review", "build"])
    args = ap.parse_args(argv)
    settings = get_settings()
    engine = make_engine(settings.database_url, settings.db_connect_timeout)
    with make_session_factory(engine)() as session, session.begin():
        version = target_version(session)
        if args.command == "review":
            stats = segment_review(session, version)
            path, links = f09_links_review(session, version)
            print(f"Dataset version {version.id}: segment parts for review (not model-verified)\n")
            print(table([s.row() for s in stats]))
            print(f"\nFile 9 drafted fault links: {links} rows in {path.relative_to(REPO_ROOT)}")
            print("Review files: data/review/parts/. Type yes in `approved`, then run: python -m app.parts build")
        else:
            result = build(session, version)
            print(f"Dataset version {version.id}: parts catalogue\n")
            print(table([f.row() for f in result.files.values()]))
            if result.unmatched_path:
                print(
                    f"\nFit text naming no catalogue model, or years / fuel the catalogue does not list: "
                    f"{len(result.unmatched_fits)} rows in {result.unmatched_path.relative_to(REPO_ROOT)}"
                )
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
