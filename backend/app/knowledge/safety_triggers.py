"""Reviewed trigger phrases for global emergency rules (data/review/safety_global_triggers.yaml).

A global rule with trigger phrases uses them instead of the words of its heading (engine/safety.py). Rules are matched
by their sheet row (source_ref), which stays the same across re-imports. Re-run `apply` after every import.

`placeholder_roadside_actions`: sheet values in the roadside action column that are not advice ("No - None.", the
road-repairable value in some file 12 rows). They are cleared (the sheet value is kept in details as
`sheet_roadside_action`), so the rule's own stop-driving text is its advice. Otherwise every rule with the same
placeholder shared one "advice" and the engine merged their alerts into the most serious one, hiding the others.

    uv run python -m app.knowledge.safety_triggers check
    uv run python -m app.knowledge.safety_triggers apply
"""

import argparse
import sys
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.models import DatasetVersion, SafetyRule
from app.knowledge.questions.inputs import target_version

TRIGGERS_PATH = Path(__file__).resolve().parents[3] / "data" / "review" / "safety_global_triggers.yaml"


class TriggerFileError(ValueError):
    pass


def read(path: Path = TRIGGERS_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _flat(items: list) -> list[str]:
    """Phrase lists may include a shared list by YAML alias (`*smoke`)."""
    out: list[str] = []
    for x in items:
        out.extend(_flat(x) if isinstance(x, list) else [str(x)])
    return out


def clear_placeholder_actions(session: Session, doc: dict, version: DatasetVersion) -> int:
    """Clear placeholder roadside actions (see the module docstring) on every rule of the version; returns how many."""
    placeholders = {str(p).strip().lower() for p in doc.get("placeholder_roadside_actions") or [] if str(p).strip()}
    if not placeholders:
        return 0
    n = 0
    for rule in session.scalars(select(SafetyRule).where(SafetyRule.dataset_version_id == version.id)):
        value = (rule.roadside_action or "").strip()
        if value and value.lower() in placeholders:
            rule.details = {**(rule.details or {}), "sheet_roadside_action": value}
            rule.roadside_action = ""
            n += 1
    session.flush()
    return n


def apply_triggers(session: Session, doc: dict, version: DatasetVersion | None = None) -> int:
    version = version or target_version(session)
    clear_placeholder_actions(session, doc, version)
    rules = {
        r.source_ref: r
        for r in session.scalars(
            select(SafetyRule).where(SafetyRule.dataset_version_id == version.id, SafetyRule.scope == "global")
        )
    }
    entries = doc.get("rules") or {}
    missing = [ref for ref in entries if ref not in rules]
    if missing:
        raise TriggerFileError(f"no global rule with source_ref {missing}")
    for ref, entry in entries.items():
        phrases = list(dict.fromkeys(p.strip() for p in _flat(entry.get("phrases") or []) if p and p.strip()))
        if not phrases:
            raise TriggerFileError(f"{ref}: no phrases")
        rule = rules[ref]
        rule.triggers = {**(rule.triggers or {}), "phrases": phrases, "reviewed_by": doc.get("reviewed_by", "")}
    session.flush()
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    from app.config import get_settings
    from app.db import make_engine, make_session_factory

    ap = argparse.ArgumentParser(prog="python -m app.knowledge.safety_triggers")
    ap.add_argument("command", choices=["check", "apply"])
    args = ap.parse_args(argv)
    with make_session_factory(make_engine(get_settings().database_url))() as session:
        n = apply_triggers(session, read())
        if args.command == "apply":
            session.commit()
            print(f"{n} global rules updated. Restart the API to use them.")
        else:
            session.rollback()
            print(f"OK: {n} global rules found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
