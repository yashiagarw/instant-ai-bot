"""Reviewed fault requirements (data/review/fault_requirements.yaml) -> faults.requires.

A requirement says what a car must have for the fault to be possible (a feature, a fuel or a gearbox). The engine
down-ranks a fault when the car is known not to meet it. Re-run `apply` after every re-import (requirements belong
to a dataset version), then restart the API.

    uv run python -m app.knowledge.requirements check    # validate the file against the database
    uv run python -m app.knowledge.requirements apply    # write faults.requires (others are reset to [])
"""

import argparse
import sys
from pathlib import Path

import yaml
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.enums import Fuel, Transmission
from app.knowledge.models import DatasetVersion, Fault
from app.knowledge.questions.inputs import target_version
from app.vehicles.features import FEATURES

REQUIREMENTS_PATH = Path(__file__).resolve().parents[3] / "data" / "review" / "fault_requirements.yaml"
ALLOWED = {
    "feature": set(FEATURES),
    "fuel": {f.value for f in Fuel},
    "transmission": {t.value for t in Transmission},
}


class RequirementsFileError(ValueError):
    pass


def read(path: Path = REQUIREMENTS_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def validate(doc: dict, keys: set[str]) -> dict[str, list[dict]]:
    """fault key -> needs, normalised ({"feature": code} / {"fuel": [...]} / {"transmission": [...]})."""
    out: dict[str, list[dict]] = {}
    for key, needs in (doc.get("requirements") or {}).items():
        if key not in keys:
            raise RequirementsFileError(f"unknown fault {key}")
        if not isinstance(needs, list) or not needs:
            raise RequirementsFileError(f"{key}: give a list of needs")
        clean = []
        for need in needs:
            if not isinstance(need, dict) or len(need) != 1:
                raise RequirementsFileError(f"{key}: each need has exactly one of {sorted(ALLOWED)}")
            ((kind, value),) = need.items()
            if kind not in ALLOWED:
                raise RequirementsFileError(f"{key}: unknown need '{kind}'")
            values = [value] if kind == "feature" else value
            if not isinstance(values, list) or not values or not set(map(str, values)) <= ALLOWED[kind]:
                raise RequirementsFileError(f"{key}: {kind} must be one of {sorted(ALLOWED[kind])}")
            clean.append({kind: str(value)} if kind == "feature" else {kind: [str(v) for v in values]})
        out[key] = clean
    return out


def apply(session: Session, doc: dict, version: DatasetVersion | None = None) -> int:
    """Write the requirements to the target dataset version's faults. Returns how many faults have some."""
    version = version or target_version(session)
    keys = set(session.scalars(select(Fault.fault_key).where(Fault.dataset_version_id == version.id)))
    reqs = validate(doc, keys)
    session.execute(update(Fault).where(Fault.dataset_version_id == version.id).values(requires=[]))
    for key, needs in reqs.items():
        session.execute(
            update(Fault).where(Fault.dataset_version_id == version.id, Fault.fault_key == key).values(requires=needs)
        )
    session.flush()
    return len(reqs)


def main(argv: list[str] | None = None) -> int:
    from app.config import get_settings
    from app.db import make_engine, make_session_factory

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "apply"])
    ap.add_argument("--file", type=Path, default=REQUIREMENTS_PATH)
    args = ap.parse_args(argv)
    doc = read(args.file)
    with make_session_factory(make_engine(get_settings().database_url))() as session, session.begin():
        try:
            if args.command == "check":
                version = target_version(session)
                keys = set(session.scalars(select(Fault.fault_key).where(Fault.dataset_version_id == version.id)))
                print(f"ok: {len(validate(doc, keys))} faults with requirements")
            else:
                print(f"applied: {apply(session, doc)} faults with requirements")
        except RequirementsFileError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    if not doc.get("reviewed"):
        print("Note: the file is marked reviewed: false.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
