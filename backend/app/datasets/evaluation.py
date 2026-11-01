"""The eval harness (data/eval/evalkit) on one dataset version, and the publish gate.

By default a draft is evaluated on the test split of the categories its upload changes (a full run, every case of
every category, takes long on a laptop and is optional). The live version is evaluated on the same scope in the same
job, so the comparison is like for like.

Gate: publishing is blocked when top-3 accuracy drops by more than 3 points or safety recall drops at all. Both are
measured on the cases the two versions have in common (matched by a key that is the same in every version: fault keys
and the question / answer text, never database ids), so the percentages are comparable. A danger case of the live
version that the draft no longer has (its safety trigger is gone) also blocks. A super_admin can override with a
written reason (app.datasets.api).
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


def case_key(knowledge, case) -> tuple[str, str]:
    """(key that is the same in every dataset version, readable label). Generated safety cases carry rule and answer
    ids in their own id, which are new in every version: they are keyed by the rule's fault, risk and the trigger
    (the phrase, or the question and answer text). Every other case id is already built from fault keys and text."""
    if case.type != "safety" or not (case.expected_alert or {}).get("rule_id"):
        return case.id, (case.text or case.id)[:160]
    rule = next((r for r in knowledge.rules if r.id == case.expected_alert["rule_id"]), None)
    fault = knowledge.faults.get(rule.fault_id).key if rule and rule.fault_id in knowledge.faults else "?"
    risk = case.expected_alert.get("risk", "")
    if case.text:
        trigger = f"says \u201c{case.text}\u201d"
    else:
        answers = {o.id: (q.text, o.label) for q in knowledge.questions.values() for o in q.options}
        trigger = "; ".join(
            f"{answers.get(o, ('?', '?'))[0]} \u2192 {answers.get(o, ('?', '?'))[1]}" for _, o in case.answers
        )
    return f"safety|{fault}|{risk}|{trigger}", f"{fault} ({risk} risk): {trigger}"[:240]


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
    """Evaluate one version on `scope`. Returns {"version_id", "cases", "overall", "by_category", "skipped",
    "results"}; results: stable case key -> {type, category, label, hit1, hit3, alert_ok} (for the comparison)."""
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
    per_case: dict[str, dict] = {}
    for i, case in enumerate(cases, 1):
        r = run_case(engine, case)
        results.append(r)
        key, label = case_key(knowledge, case)
        n = 2
        while key in per_case:  # the same trigger twice (rare): keep both
            key, n = f"{key}#{n}", n + 1
        per_case[key] = {"type": case.type, "category": case.category, "label": label,
                         **{k: r[k] for k in ("hit1", "hit3", "alert_ok") if k in r}}  # fmt: skip
        if i % PROGRESS_EVERY == 0 or i == len(cases):
            progress(i, len(cases))
    overall = stats(results)
    return {
        "version_id": version.id,
        "cases": len(cases),
        "overall": overall,
        "by_category": group_by(results, lambda r: r["category"]),
        "skipped": skipped,  # written cases naming a fault this version does not have
        "results": per_case,
    }


def _rate(hits: int, n: int) -> float | None:
    return round(hits / n, 4) if n else None


def _common_stats(results: dict[str, dict], keys: set[str]) -> dict:
    rows = [results[k] for k in keys]
    ranked = [r for r in rows if "hit3" in r]
    danger = [r for r in rows if "alert_ok" in r]
    missed = sum(not r["alert_ok"] for r in danger)
    return {"n": len(rows), "ranked_n": len(ranked), "top1": _rate(sum(r["hit1"] for r in ranked), len(ranked)),
            "top3": _rate(sum(r["hit3"] for r in ranked), len(ranked)), "safety_n": len(danger),
            "safety_missed": missed, "safety_recall": _rate(len(danger) - missed, len(danger))}  # fmt: skip


def compare(draft: dict, current: dict) -> dict:
    """The two versions on the cases they have in common, the cases only one has, and every safety case whose
    outcome differs (fired / missed / absent)."""
    d, c = draft["results"], current["results"]
    common = set(d) & set(c)

    def brief(results, keys):
        return [{"key": k, "type": results[k]["type"], "category": results[k]["category"], "label": results[k]["label"]}
                for k in sorted(keys)]  # fmt: skip

    def outcome(results, k):
        if k not in results:
            return "absent"
        return "fired" if results[k]["alert_ok"] else "missed"

    safety_keys = {k for k in set(d) | set(c) if "alert_ok" in (d.get(k) or c.get(k))}
    changed = [
        {"key": k, "category": (d.get(k) or c.get(k))["category"], "label": (d.get(k) or c.get(k))["label"],
         "live": outcome(c, k), "draft": outcome(d, k)}
        for k in sorted(safety_keys)
        if outcome(c, k) != outcome(d, k)
    ]  # fmt: skip
    return {
        "common": len(common),
        "live": _common_stats(c, common),
        "draft": _common_stats(d, common),
        "only_live": brief(c, set(c) - common),
        "only_draft": brief(d, set(d) - common),
        "safety_changed": changed,
    }


def _points(rate: float | None) -> float | None:
    return None if rate is None else round(rate * 100, 2)


def missed_text(stats: dict) -> str:
    """'2 of 176 danger cases missed (98.86%)'."""
    if not stats.get("safety_n"):
        return "no danger cases"
    return (
        f"{stats['safety_missed']} of {stats['safety_n']} danger cases missed ({_points(stats['safety_recall']):.2f}%)"
    )


def gate(draft: dict, current: dict | None) -> dict:
    """{"ok", "reasons", "top3_change", "safety_change"} (changes in points, draft minus current). With per-case
    results (every eval since the comparison was added) both are measured on the common cases."""
    if current is None:
        return {"ok": True, "reasons": [], "note": "No published version to compare with.", "top3_change": None,
                "safety_change": None}  # fmt: skip
    if "results" in draft and "results" in current:
        return _gate_on_common(compare(draft, current))
    return _gate_on_totals(draft["overall"], current["overall"])


def _gate_on_common(cmp: dict) -> dict:
    d, c = cmp["draft"], cmp["live"]
    reasons = []
    top3_change = safety_change = None
    if c["top3"] is not None:
        top3_change = round((_points(d["top3"]) or 0.0) - _points(c["top3"]), 2)
        if -top3_change > TOP3_MAX_DROP_POINTS:
            reasons.append(
                f"Top-3 accuracy drops {-top3_change:.2f} points ({_points(c['top3']):.2f}% to "
                f"{_points(d['top3']):.2f}%) on the {cmp['common']} cases both versions have; the limit is "
                f"{TOP3_MAX_DROP_POINTS:.0f} points."
            )
    if c["safety_n"]:
        safety_change = round((_points(d["safety_recall"]) or 0.0) - _points(c["safety_recall"]), 2)
        if d["safety_missed"] > c["safety_missed"]:
            reasons.append(
                f"Safety recall drops: {missed_text(d)} in the draft, {missed_text(c)} live (same cases); "
                "it may not drop at all."
            )
    gone = [x for x in cmp["only_live"] if x["type"] == "safety"]
    if gone:
        cats = sorted({x["category"] for x in gone})
        reasons.append(
            f"{len(gone)} danger case(s) of the live version are missing in the draft ({', '.join(cats)}): their "
            "safety trigger is gone. See the list below."
        )
    return {"ok": not reasons, "reasons": reasons, "top3_change": top3_change, "safety_change": safety_change,
            "common": cmp["common"]}  # fmt: skip


def _gate_on_totals(d: dict, c: dict) -> dict:
    """Evals stored before the per-case comparison: the totals of each version."""
    reasons = []
    top3_change = safety_change = None
    if c.get("top3") is not None:
        top3_change = round((_points(d.get("top3")) or 0.0) - _points(c["top3"]), 2)
        if -top3_change > TOP3_MAX_DROP_POINTS:
            reasons.append(
                f"Top-3 accuracy drops {-top3_change:.2f} points ({_points(c['top3']):.2f}% to "
                f"{_points(d.get('top3')) or 0:.2f}%); the limit is {TOP3_MAX_DROP_POINTS:.0f} points."
            )
    if c.get("safety_recall") is not None:
        safety_change = round((_points(d.get("safety_recall")) or 0.0) - _points(c["safety_recall"]), 2)
        if safety_change < 0:
            reasons.append(
                f"Safety recall drops {-safety_change:.2f} points ({_points(c['safety_recall']):.2f}% to "
                f"{_points(d.get('safety_recall')) or 0:.2f}%); it may not drop at all."
            )
    return {"ok": not reasons, "reasons": reasons, "top3_change": top3_change, "safety_change": safety_change}


def evaluation_record(scope: dict, draft: dict, current: dict | None) -> dict:
    """What is stored in dataset_versions.eval and shown on the Datasets page. Per-case results are reduced to the
    comparison (lists of the cases that differ), so the record stays small."""
    cmp = compare(draft, current) if current is not None else None
    return {
        "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scope": scope,
        "draft": {k: v for k, v in draft.items() if k != "results"},
        "current": None if current is None else {k: v for k, v in current.items() if k != "results"},
        "comparison": cmp,
        "gate": gate(draft, current),
    }
