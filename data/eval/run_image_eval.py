"""Evaluate photo analysis (backend/app/vision) on the labelled photos in data/eval/images/manifest.yaml.

Each photo goes through the same checks and re-encoding as a customer upload, then the same model call as the API
(app.vision.analysis.read_photo, labels from the image_labels table). Reports correct / wrong / unclear rates per
mode, red-light recall, and the calls' tokens and estimated cost; with --out also a JSON report.

It calls Claude only when LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY are set; otherwise nothing is called and it
says so. Zero photos is fine (it reports that there is nothing to evaluate).

Run from backend/:  uv run python ../data/eval/run_image_eval.py [--manifest PATH] [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.vision.models import AnalysisMode, FindingStatus  # noqa: E402

IMAGES_DIR = Path(__file__).resolve().parent / "images"
MANIFEST = IMAGES_DIR / "manifest.yaml"


@dataclass
class Item:
    file: str
    mode: AnalysisMode
    expect: list[str]
    note: str = ""


@dataclass
class Scored:
    item: Item
    verdict: str  # correct | wrong | unclear | missing
    answered: list[str] = field(default_factory=list)
    status: str = ""


def load_manifest(path: Path) -> list[Item]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = []
    for i, p in enumerate(data.get("photos") or []):
        if not p.get("file") or p.get("mode") not in {m.value for m in AnalysisMode}:
            raise SystemExit(f"{path}: photo {i + 1} needs file and mode (warning_light or damage)")
        items.append(Item(p["file"], AnalysisMode(p["mode"]), list(p.get("expect") or []), p.get("note", "")))
    return items


def score(item: Item, status: FindingStatus, labels: list[dict]) -> Scored:
    answered = [x["code"] for x in labels]
    if status != FindingStatus.found:
        verdict = "correct" if not item.expect and status == FindingStatus.unclear else "unclear"
    elif not item.expect:
        verdict = "wrong"
    else:
        verdict = "correct" if answered[0] in item.expect and set(answered) <= set(item.expect) else "wrong"
    return Scored(item, verdict, answered, str(status))


def summarise(scored: list[Scored], red_codes: set[str]) -> dict:
    out: dict = {"photos": len(scored), "by_mode": {}}
    groups: dict[str, list[Scored]] = defaultdict(list)
    for s in scored:
        groups[s.item.mode.value].append(s)
        groups["all"].append(s)
    for name, rows in groups.items():
        counts = Counter(s.verdict for s in rows)
        n = len(rows)
        out["by_mode"][name] = {
            "n": n,
            **{k: counts.get(k, 0) for k in ("correct", "wrong", "unclear", "missing")},
            **{f"{k}_rate": round(counts.get(k, 0) / n, 3) for k in ("correct", "wrong", "unclear")},
        }
    red = [s for s in scored if set(s.item.expect) & red_codes]
    found = [s for s in red if set(s.answered) & set(s.item.expect) & red_codes]
    out["red_light_recall"] = {
        "n": len(red),
        "found": len(found),
        "rate": round(len(found) / len(red), 3) if red else None,
    }
    return out


def evaluate(items: list[Item], images_dir: Path, read, labels_by_mode: dict, max_bytes: int, max_px: int):
    """`read(mode, labels, jpeg) -> Reading`. Photos go through app.uploads.imaging.process like uploads do."""
    from app.uploads.imaging import ImageRejected, process

    scored = []
    for item in items:
        path = images_dir / item.file
        if not path.is_file():
            scored.append(Scored(item, "missing", status="file not found"))
            continue
        try:
            clean = process(path.read_bytes(), max_bytes, max_px)
        except ImageRejected as e:
            scored.append(Scored(item, "missing", status=f"rejected: {e.code}"))
            continue
        r = read(item.mode, labels_by_mode[item.mode], clean.data)
        scored.append(score(item, r.status, r.labels))
    return scored


def print_report(summary: dict, scored: list[Scored], calls: dict | None) -> None:
    print(f"Photos: {summary['photos']}")
    print(f"{'mode':14} {'n':>4} {'correct':>9} {'wrong':>9} {'unclear':>9} {'missing':>8}")
    for name, m in summary["by_mode"].items():
        print(
            f"{name:14} {m['n']:>4} {m['correct']:>4} {m['correct_rate']:>4.0%} {m['wrong']:>4} {m['wrong_rate']:>4.0%}"
            f" {m['unclear']:>4} {m['unclear_rate']:>4.0%} {m['missing']:>8}"
        )
    red = summary["red_light_recall"]
    if red["n"]:
        print(f"Red-light recall: {red['found']}/{red['n']} ({red['rate']:.0%})")
    for s in scored:
        if s.verdict in ("wrong", "missing"):
            print(f"  {s.verdict:8} {s.item.file}: expected {s.item.expect or 'unclear'}, got {s.answered or s.status}")
    if calls:
        print(f"Calls: {calls['calls']} {calls['outcomes']} | tokens in {calls['input_tokens']} out "
              f"{calls['output_tokens']} | ~${calls['cost_usd_estimate']}")  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--out", type=Path, help="also write the report as JSON")
    args = ap.parse_args(argv)

    items = load_manifest(args.manifest)
    if not items:
        print(f"No labelled photos in {args.manifest}: nothing to evaluate (see manifest.example.yaml).")
        return 0

    from app.config import get_settings
    from app.db import make_engine, make_session_factory
    from app.llm.client import MemoryRecorder, make_llm_client
    from app.vision.analysis import labels_for, read_photo
    from app.vision.models import Severity

    settings = get_settings()
    recorder = MemoryRecorder()
    llm = make_llm_client(settings, recorder)
    if llm is None:
        print(
            f"{len(items)} labelled photos, but no vision provider (LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY): "
            "nothing was called."
        )
        return 0
    with make_session_factory(make_engine(settings.database_url))() as session:
        labels = {m: labels_for(session, m) for m in AnalysisMode}
    if not any(labels.values()):
        raise SystemExit("image_labels is empty: cd backend && uv run python -m app.vision.catalogue seed")
    red = {lb.code for lb in labels[AnalysisMode.warning_light] if lb.severity == Severity.red}

    def read(mode, mode_labels, jpeg):
        return read_photo(llm, mode, mode_labels, jpeg, settings.vision_min_confidence)

    scored = evaluate(items, args.manifest.parent, read, labels, settings.upload_max_bytes, settings.upload_max_px)
    summary = summarise(scored, red)
    calls = recorder.summary()
    print_report(summary, scored, calls)
    if args.out:
        detail = [{"file": s.item.file, "mode": s.item.mode.value, "expect": s.item.expect, "answered": s.answered,
                   "status": s.status, "verdict": s.verdict} for s in scored]  # fmt: skip
        args.out.write_text(json.dumps({"summary": summary, "calls": calls, "photos": detail}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
