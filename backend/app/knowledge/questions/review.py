"""Review files: data/review/questions/<category>.yaml, the approved-snapshot used by `diff`,
and the run log (model, tokens, cost)."""

import difflib
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.knowledge.importer.config import REVIEW_DIR

QUESTIONS_DIR = REVIEW_DIR / "questions"
REVIEW_STATUSES = ("draft", "approved", "rejected")

HEADER = """\
# Draft questions for one category, generated offline by an LLM. Nothing here is live.
#
# How to review:
#   1. Read each entry under questions, faults and safety_rules. Edit wording, options or effects freely.
#      effects: which faults an option supports or rules out (strength strong / moderate / weak).
#      safety_trigger: true shows an immediate stop-driving warning when that option is chosen.
#   2. Set status: approved (or rejected) on each entry you have checked. Leave the rest as draft.
#   3. Put your name in reviewed_by at the top.
#   4. Load:  cd backend && uv run python -m app.knowledge.questions load --category {category}
#      Only approved entries are loaded. `diff` shows what changed since the last load.
# Every question keeps exactly one "Not sure" option (not_sure: true) with no effects.
"""


def path_for(category: str, directory: Path = QUESTIONS_DIR) -> Path:
    return directory / f"{category}.yaml"


def snapshot_path(category: str, directory: Path = QUESTIONS_DIR) -> Path:
    return directory / ".approved" / f"{category}.yaml"


def dump(doc: dict) -> str:
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)


def read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def entries(doc: dict) -> dict[str, dict]:
    """Every reviewable entry by id: questions, faults (keyed by fault key) and safety rules."""
    out = {f"question {q['id']}": q for q in doc.get("questions", [])}
    out.update({f"fault {k}": v for k, v in (doc.get("faults") or {}).items()})
    out.update({f"safety_rule {r['id']}": r for r in doc.get("safety_rules", [])})
    return out


def has_review_work(doc: dict) -> bool:
    return any(e.get("status") in ("approved", "rejected") for e in entries(doc).values())


def write_draft(doc: dict, directory: Path = QUESTIONS_DIR) -> Path:
    """Write <category>.yaml, unless it already holds reviewed entries: then <category>.new.yaml."""
    directory.mkdir(parents=True, exist_ok=True)
    target = path_for(doc["category"], directory)
    if target.exists() and has_review_work(read(target)):
        target = directory / f"{doc['category']}.new.yaml"
    target.write_text(HEADER.format(category=doc["category"]) + dump(doc), encoding="utf-8")
    return target


def status_counts(doc: dict) -> dict[str, int]:
    counts = dict.fromkeys(REVIEW_STATUSES, 0)
    for e in entries(doc).values():
        counts[e.get("status", "draft")] = counts.get(e.get("status", "draft"), 0) + 1
    return counts


def approved_only(doc: dict) -> dict[str, dict]:
    return {k: v for k, v in entries(doc).items() if v.get("status") == "approved"}


def save_snapshot(doc: dict, directory: Path = QUESTIONS_DIR) -> Path:
    path = snapshot_path(doc["category"], directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "category": doc["category"],
        "loaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reviewed_by": doc.get("reviewed_by", ""),
        "approved": approved_only(doc),
    }
    path.write_text(dump(snapshot), encoding="utf-8")
    return path


def diff(category: str, directory: Path = QUESTIONS_DIR) -> str:
    """What the approved entries look like now compared with the last load (added / removed / changed)."""
    current = approved_only(read(path_for(category, directory)))
    snap_path = snapshot_path(category, directory)
    if not snap_path.exists():
        return f"{category}: never loaded. {len(current)} entries are approved now."
    snap = read(snap_path)
    before = snap.get("approved") or {}
    lines = [f"{category}: compared with the load of {snap.get('loaded_at')}"]
    added = sorted(set(current) - set(before))
    removed = sorted(set(before) - set(current))
    changed = sorted(k for k in set(current) & set(before) if current[k] != before[k])
    lines.append(f"added {len(added)}, removed {len(removed)}, changed {len(changed)}")
    lines += [f"+ {k}" for k in added]
    lines += [f"- {k} (no longer approved or deleted)" for k in removed]
    for k in changed:
        lines += [f"~ {k}"]
        lines += [
            "    " + ln.rstrip("\n")
            for ln in difflib.unified_diff(
                dump(before[k]).splitlines(), dump(current[k]).splitlines(), "last load", "now", lineterm="", n=1
            )
        ]
    if not (added or removed or changed):
        lines.append("no changes")
    return "\n".join(lines)


def log_run(record: dict, directory: Path = QUESTIONS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "runs.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
