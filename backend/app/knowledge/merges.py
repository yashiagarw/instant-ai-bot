"""Reviewed duplicate decisions (data/review/merges.yaml) -> merged_into fault links.

A merge never deletes a fault row: the alias stays in the database and points at its canonical fault with
a `merged_into` link. The engine loader then folds same-category aliases into the canonical fault and shows
cross-category aliases once. Re-run `apply` after every re-import (links belong to a dataset version).

    uv run python -m app.knowledge.merges check    # validate the file against the database
    uv run python -m app.knowledge.merges apply    # write the links (replaces earlier merge links)
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session

from app.knowledge.models import Fault, FaultLink, LinkRelation, LinkSource
from app.knowledge.questions.inputs import target_version

MERGES_PATH = Path(__file__).resolve().parents[3] / "data" / "review" / "merges.yaml"


class MergeFileError(ValueError):
    pass


@dataclass
class MergeReport:
    groups: int = 0
    links: int = 0
    candidates_reviewed: int = 0


def read(path: Path = MERGES_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def validate(doc: dict, keys: set[str]) -> list[tuple[str, str, str]]:
    """(alias, canonical, reason) triples. Raises on unknown keys, self-merges and conflicting groups."""
    out, seen_alias, canon = [], set(), set()
    for g in doc.get("merge", []):
        c = g["canonical"]
        if c not in keys:
            raise MergeFileError(f"unknown canonical fault {c}")
        canon.add(c)
        for a in g.get("aliases", []):
            if a not in keys:
                raise MergeFileError(f"unknown alias fault {a}")
            if a == c or a in seen_alias:
                raise MergeFileError(f"{a} is merged twice or into itself")
            seen_alias.add(a)
            out.append((a, c, g.get("reason", "")))
    if both := seen_alias & canon:
        raise MergeFileError(f"faults are both canonical and alias: {sorted(both)}")
    return out


def apply_merges(session: Session, doc: dict) -> MergeReport:
    version = target_version(session)
    ids = dict(session.execute(select(Fault.fault_key, Fault.id).where(Fault.dataset_version_id == version.id)).all())
    triples = validate(doc, set(ids))
    in_version = select(Fault.id).where(Fault.dataset_version_id == version.id)
    session.execute(
        delete(FaultLink).where(
            FaultLink.relation == LinkRelation.merged_into,
            FaultLink.source == LinkSource.manual,
            FaultLink.from_fault_id.in_(in_version),
        )
    )
    decided_by = doc.get("decided_by", "")
    for alias, canonical, reason in triples:
        session.add(
            FaultLink(
                from_fault_id=ids[alias],
                to_fault_id=ids[canonical],
                relation=LinkRelation.merged_into,
                source=LinkSource.manual,
                note=f"{reason} ({decided_by})".strip(),
                reviewed=True,
            )
        )
    # Mark every duplicate-scan candidate that was decided (merged or kept separate) as reviewed.
    decided = [(ids[a], ids[c]) for a, c, _ in triples]
    for g in doc.get("merge", []):  # aliases of one group are duplicates of each other too
        aliases = g.get("aliases", [])
        decided += [(ids[x], ids[y]) for i, x in enumerate(aliases) for y in aliases[i + 1 :]]
    decided += [(ids[k["faults"][0]], ids[k["faults"][1]]) for k in doc.get("keep_separate", [])]
    reviewed = 0
    if decided:
        pairs = or_(
            *[
                or_(
                    and_(FaultLink.from_fault_id == a, FaultLink.to_fault_id == b),
                    and_(FaultLink.from_fault_id == b, FaultLink.to_fault_id == a),
                )
                for a, b in decided
            ]
        )
        reviewed = session.execute(
            update(FaultLink)
            .where(FaultLink.relation == LinkRelation.duplicate_candidate, pairs)
            .values(reviewed=True)
            .execution_options(synchronize_session=False)
        ).rowcount
    session.flush()
    return MergeReport(len(doc.get("merge", [])), len(triples), reviewed)


def main(argv: list[str] | None = None) -> int:
    from app.config import get_settings
    from app.db import make_engine, make_session_factory

    ap = argparse.ArgumentParser(prog="python -m app.knowledge.merges")
    ap.add_argument("command", choices=["check", "apply"])
    ap.add_argument("--file", type=Path, default=MERGES_PATH)
    args = ap.parse_args(argv)
    doc = read(args.file)
    with make_session_factory(make_engine(get_settings().database_url))() as session:
        if args.command == "check":
            version = target_version(session)
            keys = set(session.scalars(select(Fault.fault_key).where(Fault.dataset_version_id == version.id)))
            print(f"OK: {len(validate(doc, keys))} aliases in {len(doc.get('merge', []))} groups")
            return 0
        report = apply_merges(session, doc)
        session.commit()
    print(f"{report.groups} groups, {report.links} merged_into links, {report.candidates_reviewed} candidates reviewed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
