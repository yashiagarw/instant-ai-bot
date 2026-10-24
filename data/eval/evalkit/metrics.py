"""Aggregate case results: per category, per case type, per language, per source, Phase 1 and overall."""

from __future__ import annotations

from collections import defaultdict

PHASE1 = ("battery", "self_start", "not_starting", "cooling", "ac", "clutch", "brakes", "tyre")


def _rate(hits: int, n: int) -> float | None:
    return round(hits / n, 4) if n else None


def stats(results: list[dict]) -> dict:
    """n, top1/top3 (cases with an expected fault), avg questions (conversations), safety recall (cases with an
    expected alert), false alarms (cases expecting none), flow safety recall (simulated flows whose true fault has
    a rule that can fire) and coverage correctness (cases with an expected coverage level)."""
    ranked = [r for r in results if "hit1" in r]
    flows = [r for r in results if r["type"] != "safety"]
    safety = [r for r in results if "alert_ok" in r]
    quiet = [r for r in results if "false_alarm" in r]
    flow_rule = [r for r in results if r.get("flow_rule")]
    coverage = [r for r in results if "coverage_ok" in r]
    return {
        "n": len(results),
        "ranked_n": len(ranked),
        "top1": _rate(sum(r["hit1"] for r in ranked), len(ranked)),
        "top3": _rate(sum(r["hit3"] for r in ranked), len(ranked)),
        "avg_questions": round(sum(r["questions"] for r in flows) / len(flows), 2) if flows else None,
        "safety_n": len(safety),
        "safety_recall": _rate(sum(r["alert_ok"] for r in safety), len(safety)),
        "false_alarm_n": len(quiet),
        "false_alarms": _rate(sum(r["false_alarm"] for r in quiet), len(quiet)),
        "flow_safety_n": len(flow_rule),
        "flow_safety_recall": _rate(sum(r["flow_rule_fired"] for r in flow_rule), len(flow_rule)),
        "coverage_n": len(coverage),
        "coverage_correct": _rate(sum(r["coverage_ok"] for r in coverage), len(coverage)),
    }


def group_by(results: list[dict], key) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        value = key(r)
        if value is not None:
            groups[value].append(r)
    return {k: stats(v) for k, v in sorted(groups.items())}


def summarise(results: list[dict]) -> dict:
    return {
        "overall": stats(results),
        "phase1": stats([r for r in results if r["category"] in PHASE1]),
        "other_categories": stats([r for r in results if r["category"] not in PHASE1]),
        "by_type": group_by(results, lambda r: r["type"]),
        "by_language": group_by(results, lambda r: r.get("lang") if r["type"] in ("free_text", "overlap") else None),
        "by_source": group_by(results, lambda r: r["source"]),
        "by_category": group_by(results, lambda r: r["category"]),
    }
