"""The photo label list (image_labels), seeded from data/review/image_labels.yaml and the datasets.

Each label names dataset faults and a pattern for their symptom lines. Seeding resolves them against the current
dataset version: the matching symptom ids (engine evidence) and, when the file gives none, the meaning from the
first fault's description. Labels stay reviewed: false until a mechanic signs them off (REVIEW_NOTES.md).

Run again after a dataset import (symptom ids change with the dataset version):

    uv run python -m app.vision.catalogue seed     # write image_labels
    uv run python -m app.vision.catalogue check    # what resolves, without writing
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.knowledge.models import Fault, FaultItem, FaultItemType
from app.knowledge.questions.inputs import target_version
from app.vision.models import AnalysisMode, ImageLabel, Severity

SPEC = Path(__file__).resolve().parents[3] / "data" / "review" / "image_labels.yaml"
SKIP_BULLETS = re.compile(r"^(which cars|fault:|the exact cause|possible .* causes)", re.I)


@dataclass
class Resolved:
    mode: AnalysisMode
    code: str
    name: str
    meaning: str
    severity: Severity | None
    look: str
    fault_keys: list[str]
    symptom_ids: list[int]
    reviewed: bool
    problems: list[str] = field(default_factory=list)


def load_spec(path: Path = SPEC) -> dict[str, list[dict]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {mode.value: list(data.get(mode.value) or []) for mode in AnalysisMode}


def meaning_from(description: str | None) -> str:
    """The first plain bullet of a fault description (skipping 'Which cars: ...' and template lines)."""
    for line in (description or "").splitlines():
        text = line.strip().lstrip("•-* ").strip()
        if text and not SKIP_BULLETS.match(text):
            return text
    return ""


def resolve(session: Session, spec: dict[str, list[dict]] | None = None) -> list[Resolved]:
    spec = spec or load_spec()
    version = target_version(session)
    out: list[Resolved] = []
    for mode in AnalysisMode:
        for item in spec[mode.value]:
            keys = list(item.get("faults") or [])
            faults = {
                f.fault_key: f
                for f in session.scalars(
                    select(Fault).where(Fault.dataset_version_id == version.id, Fault.fault_key.in_(keys))
                )
            }
            pattern = re.compile(item.get("symptoms") or ".", re.I)
            ids: list[int] = []
            problems = [f"fault {k} not in the dataset" for k in keys if k not in faults]
            for key in keys:
                if key not in faults:
                    continue
                lines = session.scalars(
                    select(FaultItem)
                    .where(FaultItem.fault_id == faults[key].id, FaultItem.type == FaultItemType.symptom)
                    .order_by(FaultItem.position)
                ).all()
                hits = [i.id for i in lines if pattern.search(i.text)]
                if not hits and lines:
                    hits = [lines[0].id]  # nothing matched: the fault's first symptom line
                    problems.append(f"{key}: no symptom line matches /{pattern.pattern}/, used the first one")
                ids += hits
            first = faults.get(keys[0]) if keys else None
            severity = item.get("severity")
            out.append(
                Resolved(
                    mode=mode,
                    code=item["code"],
                    name=item["name"],
                    meaning=item.get("meaning") or meaning_from(first.description if first else None),
                    severity=Severity(severity) if severity else None,
                    look=item.get("look", ""),
                    fault_keys=[k for k in keys if k in faults],
                    symptom_ids=list(dict.fromkeys(ids)),
                    reviewed=bool(item.get("reviewed", False)),
                    problems=problems,
                )
            )
    return out


def seed(session: Session, spec: dict[str, list[dict]] | None = None) -> list[Resolved]:
    """Replace image_labels with the resolved list (labels removed from the file are removed)."""
    labels = resolve(session, spec)
    session.execute(delete(ImageLabel))
    for r in labels:
        session.add(
            ImageLabel(
                mode=r.mode,
                code=r.code,
                name=r.name,
                meaning=r.meaning,
                severity=r.severity,
                look=r.look,
                fault_keys=r.fault_keys,
                symptom_ids=r.symptom_ids,
                reviewed=r.reviewed,
            )
        )
    session.flush()
    return labels


def main(argv: list[str]) -> int:
    from app.config import get_settings
    from app.db import make_engine, make_session_factory

    if not argv or argv[0] not in ("seed", "check"):
        print(__doc__)
        return 2
    with make_session_factory(make_engine(get_settings().database_url))() as session:
        labels = seed(session) if argv[0] == "seed" else resolve(session)
        for r in labels:
            flag = "" if r.reviewed else "  (not reviewed)"
            print(f"{r.mode.value:13} {r.code:22} {len(r.symptom_ids):2} symptom lines{flag}")
            for p in r.problems:
                print(f"{'':36}! {p}")
        if argv[0] == "seed":
            session.commit()
            print(f"{len(labels)} labels written to image_labels")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
