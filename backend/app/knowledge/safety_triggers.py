"""Reviewed trigger phrases for global emergency rules (data/review/safety_global_triggers.yaml).

A global rule with trigger phrases uses them instead of the words of its heading (engine/safety.py). Rules are matched
by their sheet row (source_ref), which stays the same across re-imports. Re-run `apply` after every import.

    uv run python -m app.knowledge.safety_triggers check
    uv run python -m app.knowledge.safety_triggers apply
"""

import argparse
import sys
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.models import SafetyRule
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


def apply_triggers(session: Session, doc: dict) -> int:
    version = target_version(session)
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
