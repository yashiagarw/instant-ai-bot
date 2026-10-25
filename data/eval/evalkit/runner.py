"""Run cases through an engine and record what happened, case by case."""

from __future__ import annotations

from dataclasses import fields

from engine import Answer, Engine, Request, Vehicle
from engine.simulate import has_triggered_rule, oracle_answer
from evalkit.cases import Case

MAX_STEPS = 20  # safety net; the engine itself stops after 8 questions
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _vehicle(spec: dict | None) -> Vehicle | None:
    if not spec:
        return None
    known = {f.name for f in fields(Vehicle)}
    return Vehicle(**{k: v for k, v in spec.items() if k in known})


def _fault_ids(knowledge, keys: list[str]) -> set[int]:
    """Canonical fault ids for keys, including merged duplicates (an alias key counts as its canonical fault)."""
    by_key = {f.key: f.id for f in knowledge.faults.values()}
    by_key |= {alias: f.id for f in knowledge.faults.values() for alias in f.alias_keys}
    return {knowledge.canonical(by_key[k]) for k in keys if k in by_key}


def _converse(engine: Engine, case: Case, fault, extract=None) -> tuple[object, set[str], set[int]]:
    """A conversation with a customer who knows `fault`. Returns the final result and every alert seen
    (fault keys and rule ids), because an alert may show mid-flow and the questions continue. `extract(engine,
    request) -> symptom ids` runs once on the customer's text (the live app's LLM extraction step)."""
    vehicle = _vehicle(case.vehicle)
    answers = [Answer(q, o) for q, o in case.answers]
    base = {"vehicle": vehicle, "group": case.group, "category": case.category_pick, "text": case.text}
    symptoms = extract(engine, Request(**base)) if extract is not None and case.text else []
    if symptoms:  # only engines from 2.1 / 1.2 take symptom ids
        base["symptoms"] = symptoms

    def ask():
        return engine.diagnose(Request(**base, answers=list(answers)))

    result = ask()
    keys: set[str] = set()
    rules: set[int] = set()
    asked: set = set()
    for _ in range(MAX_STEPS):
        keys |= {k for a in result.safety_alerts for k in a.fault_keys}
        rules |= {a.rule_id for a in result.safety_alerts}
        q = result.next_question
        if not case.simulate or fault is None or result.done or q is None or q.id in asked:
            break
        asked.add(q.id)
        answers.append(oracle_answer(q, engine.k, fault))
        result = ask()
    keys |= {k for a in result.safety_alerts for k in a.fault_keys}
    rules |= {a.rule_id for a in result.safety_alerts}
    return result, keys, rules


def _alert_matches(alert, expected: dict, knowledge) -> bool:
    if "rule_id" in expected:
        if alert.rule_id == expected["rule_id"]:
            return True
        # Alerts with identical advice are merged into one; a merged alert still names the rule's fault.
        rule = next((r for r in knowledge.rules if r.id == expected["rule_id"]), None)
        fault = knowledge.faults.get(rule.fault_id) if rule and rule.fault_id else None
        return bool(fault and fault.key in alert.fault_keys and alert.risk == rule.risk)
    return RISK_ORDER.get(alert.risk, -1) >= RISK_ORDER[expected.get("risk", "low")]


def run_case(engine: Engine, case: Case, extract=None) -> dict:
    k = engine.k
    expected_ids = _fault_ids(k, case.expected)
    # The simulated customer has the first listed fault; the others also count as right answers.
    first = _fault_ids(k, case.expected[:1])
    fault = k.faults.get(next(iter(first))) if first else None
    result, seen_keys, _ = _converse(engine, case, fault, extract)
    ranked = [k.canonical(r.fault_id) for r in result.ranked]
    out: dict = {
        "id": case.id,
        "type": case.type,
        "source": case.source,
        "lang": case.lang,
        "category": case.category,
        "input": {
            k: v
            for k, v in (
                ("text", case.text),
                ("group", case.group),
                ("category", case.category_pick),
                ("vehicle", case.vehicle),
                ("answers", case.answers),
            )
            if v
        },
        "expected": case.expected,
        "got": [r.fault_key for r in result.ranked[:3]],
        "questions": result.questions_asked,
        "done": result.done,
        "mode": result.mode,
        "coverage": result.coverage,
        "alerts": [{"rule_id": a.rule_id, "risk": a.risk, "source": a.source} for a in result.safety_alerts],
    }
    if expected_ids:
        out["hit1"] = bool(ranked[:1]) and ranked[0] in expected_ids
        out["hit3"] = bool(expected_ids & set(ranked[:3]))
    if case.expected_alert:
        if case.expected_alert.get("none"):
            out["false_alarm"] = any(a.risk == "high" for a in result.safety_alerts)
        else:
            out["alert_ok"] = any(_alert_matches(a, case.expected_alert, k) for a in result.safety_alerts)
    if case.expected_coverage:
        out["coverage_ok"] = result.coverage in case.expected_coverage
    # In simulated flows: if the true fault has a rule that can fire, did it fire at any point?
    if case.simulate and fault is not None and has_triggered_rule(engine, fault):
        out["flow_rule"] = True
        out["flow_rule_fired"] = any(k.canonical(fid) == k.canonical(fault.id) for fid in _ids_for(k, seen_keys))
    return out


def _ids_for(knowledge, keys: set[str]) -> list[int]:
    by_key = {f.key: f.id for f in knowledge.faults.values()}
    return [by_key[key] for key in keys if key in by_key]


def run_all(engine: Engine, cases: list[Case], extract=None) -> list[dict]:
    return [run_case(engine, c, extract) for c in cases]
