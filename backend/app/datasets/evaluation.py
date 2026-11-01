"""The eval harness (data/eval/evalkit) on one dataset version, and the publish gate.

By default a draft is evaluated on the test split of the categories its upload changes (a full run, every case of
every category, takes long on a laptop and is optional). The live version is evaluated on the same scope in the same
job, so the comparison is like for like.

Gate: publishing is blocked when top-3 accuracy drops by more than 3 points or safety recall drops at all. A
super_admin can override with a written reason (app.datasets.api).
"""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.diagnosis.knowledge import load_knowledge
from app.knowledge.importer.config import REPO_ROOT
from app.knowledge.models import DatasetVersion

EVAL_DIR = REPO_ROOT / "data" / "eval"
TOP3_MAX_DROP_POINTS = 3.0
PROGRESS_EVERY = 25  # cases


def _evalkit():
    """The harness lives in data/eval (it also compares engine versions from git); import it from there."""
    if str(EVAL_DIR) not in sys.path:
        sys.path.insert(0, str(EVAL_DIR))
    from evalkit import cases
    from evalkit.metrics import group_by, stats
    from evalkit.runner import run_case
    from run_eval import CASES_DIR, held_out_phrases

    return cases, run_case, stats, group_by, CASES_DIR, held_out_phrases


def build_cases(knowledge, phrases, cases_dir, skipped: list[str]) -> list:
    """The harness's case set (evalkit.cli.build_cases), leaving out YAML cases whose fault this version lacks.
    Generated safety cases are split by their fault key instead of the rule's database id, which is new in every
    dataset version: two versions then get the same dev / test cases and the comparison is like for like."""
    ck = _evalkit()[0]
    free = ck.phrase_cases(knowledge, phrases)
    rule_fault = {r.id: knowledge.faults[r.fault_id].key for r in knowledge.rules if r.fault_id in knowledge.faults}
    safety = [
        dataclasses.replace(c, split_key=f"safety:{rule_fault[c.expected_alert['rule_id']]}")
        if c.expected_alert and c.expected_alert.get("rule_id") in rule_fault
        else c
        for c in ck.safety_cases(knowledge, knowledge.rules)
    ]
    return [
        *free,
        *ck.chip_cases(knowledge),
        *safety,
        *ck.unlisted_variants(free),
        *ck.load_yaml_cases(knowledge, cases_dir, skipped),
    ]


def scope_for(categories: list[str] | None, full: bool) -> dict:
    """{"categories": [...] or None (all), "split": "test" | "all", "full": bool}."""
    return {"categories": None if full else sorted(categories or []), "split": "all" if full else "test", "full": full}


def run_eval(
    session: Session,
    version: DatasetVersion,
    scope: dict,
    *,
    diagnosis_engine: str,
    search=None,
    cases_dir=None,
    progress: Callable[[int, int], None] = lambda _done, _total: None,
) -> dict:
    """Evaluate one version on `scope`. Returns {"version_id", "cases", "overall", "by_category", "skipped"}."""
    import engine as eng

    ck, run_case, stats, group_by, default_dir, held_out_phrases = _evalkit()
    knowledge = load_knowledge(session, version)
    phrases = held_out_phrases(session, knowledge, with_language=True)
    skipped: list[str] = []
    cases = build_cases(knowledge, phrases, cases_dir or default_dir, skipped)
    if scope["categories"] is not None:
        wanted = set(scope["categories"])
        cases = [c for c in cases if c.category in wanted]
    if scope["split"] != "all":
        cases = [c for c in cases if ck.split_of(c) == scope["split"]]
    engine = eng.make_engine(diagnosis_engine, knowledge, search=search)
    results = []
    for i, case in enumerate(cases, 1):
        results.append(run_case(engine, case))
        if i % PROGRESS_EVERY == 0 or i == len(cases):
            progress(i, len(cases))
    overall = stats(results)
    return {
        "version_id": version.id,
        "cases": len(cases),
        "overall": overall,
        "by_category": group_by(results, lambda r: r["category"]),
        "skipped": skipped,  # written cases naming a fault this version does not have
    }


def _points(rate: float | None) -> float | None:
    return None if rate is None else round(rate * 100, 2)


def gate(draft: dict, current: dict | None) -> dict:
    """{"ok", "reasons", "top3_change", "safety_change"} (changes in points, draft minus current)."""
    if current is None:
        return {"ok": True, "reasons": [], "note": "No published version to compare with.", "top3_change": None,
                "safety_change": None}  # fmt: skip
    d, c = draft["overall"], current["overall"]
    reasons = []
    top3_change = safety_change = None
    if c.get("top3") is not None:
        top3_change = round((_points(d.get("top3")) or 0.0) - _points(c["top3"]), 2)
        if -top3_change > TOP3_MAX_DROP_POINTS:
            reasons.append(
                f"Top-3 accuracy drops {-top3_change:.1f} points ({_points(c['top3']):.1f}% to "
                f"{_points(d.get('top3')) or 0:.1f}%); the limit is {TOP3_MAX_DROP_POINTS:.0f} points."
            )
    if c.get("safety_recall") is not None:
        safety_change = round((_points(d.get("safety_recall")) or 0.0) - _points(c["safety_recall"]), 2)
        if safety_change < 0:
            reasons.append(
                f"Safety recall drops {-safety_change:.1f} points ({_points(c['safety_recall']):.1f}% to "
                f"{_points(d.get('safety_recall')) or 0:.1f}%); it may not drop at all."
            )
    return {"ok": not reasons, "reasons": reasons, "top3_change": top3_change, "safety_change": safety_change}


def evaluation_record(scope: dict, draft: dict, current: dict | None) -> dict:
    """What is stored in dataset_versions.eval and shown on the Datasets page."""
    return {
        "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scope": scope,
        "draft": draft,
        "current": current,
        "gate": gate(draft, current),
    }
