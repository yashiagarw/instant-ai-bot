"""Reports: JSON (everything, case by case) and Markdown (for people), and the comparison of two runs."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from evalkit.metrics import PHASE1

METRICS = [
    ("top1", "Top-1", True),
    ("top3", "Top-3", True),
    ("avg_questions", "Avg Qs", False),
    ("safety_recall", "Safety recall", True),
    ("flow_safety_recall", "Flow safety", True),
    ("coverage_correct", "Coverage OK", True),
]
CHANGE_FIELDS = ("hit1", "hit3", "alert_ok", "false_alarm", "coverage_ok", "flow_rule_fired")


def timestamp(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%SZ")


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "-", text).strip("-")[:60] or "run"


def _fmt(value, percent: bool) -> str:
    if value is None:
        return "–"
    return f"{100 * value:.1f}%" if percent else f"{value:.2f}"


def _table(rows: dict[str, dict], first: str) -> list[str]:
    head = f"| {first} | n | " + " | ".join(label for _, label, _ in METRICS) + " |"
    out = [head, "|" + "---|" * (len(METRICS) + 2)]
    for name, s in rows.items():
        cells = [
            _fmt(s[key], pct) + (f" ({s[n_key]})" if (n_key := _n_key(key)) and s[n_key] else "")
            for key, _, pct in METRICS
        ]
        out.append(f"| {name} | {s['n']} | " + " | ".join(cells) + " |")
    return out


def _n_key(metric: str) -> str | None:
    return {
        "top1": "ranked_n",
        "safety_recall": "safety_n",
        "flow_safety_recall": "flow_safety_n",
        "coverage_correct": "coverage_n",
    }.get(metric)


def _search_label(m: dict) -> str:
    """What free-text matching used: hybrid search (keyword index + full-text + vectors + typos) or the keyword
    index alone (optionally with its old embedding bonus, `--embeddings`)."""
    if m.get("search") == "hybrid":
        return f"search hybrid (keyword index + full-text + vectors from {m.get('vector_model', '?')} + typos)"
    return "search keyword index" + (" + embedding bonus" if m.get("embeddings") else " only")


def _extraction_label(m: dict) -> str:
    """LLM extraction on free-text cases (run --extraction llm): provider, calls, outcomes, tokens and cost."""
    u = m.get("llm_usage") or {}
    outcomes = ", ".join(f"{k} {v}" for k, v in sorted(u.get("outcomes", {}).items())) or "none"
    return (
        f"- Extraction: {m['extraction']} · LLM_PROVIDER={m.get('llm_provider')} · model {m.get('llm_model') or '-'} · "
        f"{u.get('calls', 0)} calls ({outcomes}) · {u.get('input_tokens', 0)} in / {u.get('output_tokens', 0)} out "
        f"tokens · estimated ${u.get('cost_usd_estimate', 0)}"
    )


def markdown(report: dict, misses_per_type: int = 15) -> str:
    m, s = report["meta"], report["summary"]
    lines = [
        f"# Engine evaluation: {m['engine_label']}",
        "",
        f"- Run: {m['created_at']} · engine {m.get('diagnosis_engine', 'v1')} version {m['engine_version']} "
        f"(code {m['engine_hash']}) · "
        f"git {m['git_commit']}{' (uncommitted changes)' if m.get('git_dirty') else ''}",
        f"- Knowledge: dataset version {m['dataset_version_id']} · {_search_label(m)} · "
        f"{m['cases']} cases ({', '.join(f'{k} {v}' for k, v in m['cases_by_source'].items())})",
        *([_extraction_label(m)] if m.get("extraction") else []),
        "- Synthetic cases (Hindi, typos, unlisted cars, some safety texts) were written to fill gaps; replace them "
        "with mechanic-confirmed cases when available.",
        "",
        "Top-1 / Top-3: expected fault ranked first / in the first three (n = cases with an expected fault). "
        "Avg Qs: questions asked per conversation. Safety recall: expected alerts that fired. Flow safety: in "
        "simulated conversations, the true fault's triggerable rule fired. Coverage OK: coverage level as expected.",
        "",
        "## Overall",
        "",
        *_table(
            {"All cases": s["overall"], "Phase 1 categories": s["phase1"], "Other categories": s["other_categories"]},
            "Scope",
        ),
        "",
        f"False alarms (high alert on a case that expects none): {_fmt(s['overall']['false_alarms'], True)} "
        f"of {s['overall']['false_alarm_n']} cases.",
        "",
        "Every table except the next one leaves out real cases.",
        "",
        "## Real cases (confirmed faults from real customers, never mixed with the rest)",
        "",
        *(
            [
                *_table({"Real cases": s["real"]["overall"]}, "Scope"),
                "",
                *_table(s["real"]["by_category"], "Category"),
            ]
            if s.get("real")
            else ["No real cases yet (data/eval/golden/real_cases)."]
        ),
        "",
        "## By case type",
        "",
        *_table(s["by_type"], "Type"),
        "",
        "## Free text by language",
        "",
        *_table(s["by_language"], "Language"),
        "",
        "## By source",
        "",
        *_table(s["by_source"], "Source"),
        "",
        "## Phase 1 categories",
        "",
        *_table({c: v for c, v in s["by_category"].items() if c in PHASE1}, "Category"),
        "",
        "## Other categories",
        "",
        *_table({c: v for c, v in s["by_category"].items() if c not in PHASE1}, "Category"),
        "",
        "## Misses (first per type)",
        "",
    ]
    by_type: dict[str, list[dict]] = {}
    for r in report["results"]:
        missed = r.get("hit3") is False or r.get("alert_ok") is False or r.get("coverage_ok") is False
        if missed:
            by_type.setdefault(r["type"], []).append(r)
    for t, rows in sorted(by_type.items()):
        lines.append(f"**{t}** ({len(rows)} cases miss)")
        lines.append("")
        for r in rows[:misses_per_type]:
            why = []
            if r.get("hit3") is False:
                why.append(f"expected {'/'.join(r['expected'])}, got {', '.join(r['got']) or 'nothing'}")
            if r.get("alert_ok") is False:
                why.append("expected safety alert did not fire")
            if r.get("coverage_ok") is False:
                why.append(f"coverage {r['coverage']}")
            lines.append(f"- `{r['id']}`: {'; '.join(why)}")
        lines.append("")
    return "\n".join(lines)


def write(report: dict, out_dir: Path, kind: str = "eval") -> tuple[Path, Path]:
    """Write <timestamp>_<kind>_<label>.json and .md; returns both paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = report["meta"]
    stem = f"{meta['stamp']}_{kind}_{slug(meta.get('engine_label') or meta.get('label', ''))}"
    jpath, mpath = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    jpath.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    mpath.write_text((markdown(report) if kind == "eval" else compare_markdown(report)) + "\n", encoding="utf-8")
    return jpath, mpath


# ---------------------------------------------------------------- compare two runs


def compare(base: dict, cand: dict) -> dict:
    """Metric deltas and every case whose outcome changed (hit, alert, coverage, questions asked)."""
    b = {r["id"]: r for r in base["results"]}
    c = {r["id"]: r for r in cand["results"]}
    changes = []
    for cid in sorted(b.keys() & c.keys()):
        rb, rc = b[cid], c[cid]
        diff = {f: (rb.get(f), rc.get(f)) for f in CHANGE_FIELDS if rb.get(f) != rc.get(f)}
        if rb["got"][:1] != rc["got"][:1]:
            diff["top"] = (rb["got"][:1], rc["got"][:1])
        if rb["questions"] != rc["questions"]:
            diff["questions"] = (rb["questions"], rc["questions"])
        if diff:
            changes.append(
                {"id": cid, "type": rc["type"], "category": rc["category"], "verdict": _verdict(diff), "diff": diff}
            )

    def deltas(sb: dict, sc: dict) -> dict:
        return {k: (sb.get(k), sc.get(k)) for k, _, _ in METRICS if sb.get(k) != sc.get(k)}

    sb, sc = base["summary"], cand["summary"]
    return {
        "meta": {
            "stamp": timestamp(),
            "label": f"{base['meta']['engine_label']}-vs-{cand['meta']['engine_label']}",
            "base": base["meta"],
            "candidate": cand["meta"],
        },
        "overall": deltas(sb["overall"], sc["overall"]),
        "real": deltas((sb.get("real") or {}).get("overall", {}), (sc.get("real") or {}).get("overall", {})),
        "by_type": {
            t: d
            for t in sorted(sb["by_type"].keys() | sc["by_type"].keys())
            if (d := deltas(sb["by_type"].get(t, {}), sc["by_type"].get(t, {})))
        },
        "by_category": {
            t: d
            for t in sorted(sb["by_category"].keys() | sc["by_category"].keys())
            if (d := deltas(sb["by_category"].get(t, {}), sc["by_category"].get(t, {})))
        },
        "only_in_base": sorted(b.keys() - c.keys()),
        "only_in_candidate": sorted(c.keys() - b.keys()),
        "changes": changes,
    }


def _verdict(diff: dict) -> str:
    better = worse = 0
    for f in ("hit1", "hit3", "alert_ok", "coverage_ok", "flow_rule_fired"):
        if f in diff and None not in diff[f]:
            better += diff[f][1] > diff[f][0]
            worse += diff[f][1] < diff[f][0]
    if "false_alarm" in diff and None not in diff["false_alarm"]:
        worse += diff["false_alarm"][1] > diff["false_alarm"][0]
        better += diff["false_alarm"][1] < diff["false_alarm"][0]
    return "better" if better and not worse else "worse" if worse and not better else "mixed" if better else "changed"


def compare_markdown(cmp: dict, limit: int = 100) -> str:
    mb, mc = cmp["meta"]["base"], cmp["meta"]["candidate"]
    lines = [
        f"# Engine comparison: {mb['engine_label']} → {mc['engine_label']}",
        "",
        *(
            f"- {role}: {m['engine_label']} (version {m['engine_version']}, code {m['engine_hash']}, "
            f"engine {m.get('diagnosis_engine', 'v1')}, search {m.get('search', 'keyword')}, run {m['created_at']})"
            for role, m in (("Base", mb), ("Candidate", mc))
        ),
        "",
        "## Metric changes",
        "",
    ]
    if not (cmp["overall"] or cmp.get("real") or cmp["by_type"] or cmp["by_category"]):
        lines.append("No metric changed.")
    for scope, rows in (
        ("Overall (without real cases)", {"all": cmp["overall"]} if cmp["overall"] else {}),
        ("Real cases", {"real": cmp["real"]} if cmp.get("real") else {}),
        ("By type", cmp["by_type"]),
        ("By category", cmp["by_category"]),
    ):
        if not rows:
            continue
        lines += [f"**{scope}**", "", "| | metric | base | candidate |", "|---|---|---|---|"]
        for name, d in rows.items():
            for key, (vb, vc) in d.items():
                pct = dict((k, p) for k, _, p in METRICS)[key]
                lines.append(f"| {name} | {key} | {_fmt(vb, pct)} | {_fmt(vc, pct)} |")
        lines.append("")
    counts: dict[str, int] = {}
    for ch in cmp["changes"]:
        counts[ch["verdict"]] = counts.get(ch["verdict"], 0) + 1
    lines += [
        "## Cases that changed",
        "",
        f"{len(cmp['changes'])} cases changed: "
        + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none")
        + ".",
    ]
    if cmp["only_in_base"] or cmp["only_in_candidate"]:
        lines.append(
            f"Cases only in base: {len(cmp['only_in_base'])}; only in candidate: {len(cmp['only_in_candidate'])}."
        )
    lines.append("")
    for verdict in ("worse", "mixed", "better", "changed"):
        rows = [ch for ch in cmp["changes"] if ch["verdict"] == verdict]
        if not rows:
            continue
        lines += [f"**{verdict}** ({len(rows)})", ""]
        for ch in rows[:limit]:
            parts = [f"{k}: {v[0]} → {v[1]}" for k, v in ch["diff"].items()]
            lines.append(f"- `{ch['id']}` ({ch['category']}): " + "; ".join(parts))
        if len(rows) > limit:
            lines.append(f"- … {len(rows) - limit} more in the JSON report")
        lines.append("")
    return "\n".join(lines)
